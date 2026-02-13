# app/services/campaign_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc
from fastapi import HTTPException, BackgroundTasks
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import math
import uuid
import secrets

from models.campaign import (
    Campaign, CampaignDonation, CampaignShare, CampaignComment,
    CampaignStatus, CampaignType
)
from models.user import User
from models.need_ad import NeedAd
from models.charity import Charity
from models.donation import Donation
from services.notification_service import NotificationService
from schemas.campaign import (
    CampaignCreate, CampaignUpdate, CampaignDonate,
    CampaignShareCreate, CampaignCommentCreate, CampaignFilter
)


class CampaignService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.notification_service = NotificationService(db)

    # ---------- ایجاد کمپین ----------
    async def create_campaign(
        self,
        campaign_data: CampaignCreate,
        owner: User,
        background_tasks: BackgroundTasks
    ) -> Campaign:
        """ایجاد کمپین جدید"""

        # بررسی خیریه
        charity = await self.db.get(Charity, campaign_data.charity_id)
        if not charity or not charity.active:
            raise HTTPException(status_code=404, detail="Charity not found or inactive")

        # بررسی نیاز (اگر انتخاب شده)
        if campaign_data.need_id:
            need = await self.db.get(NeedAd, campaign_data.need_id)
            if not need or need.charity_id != charity.id:
                raise HTTPException(status_code=404, detail="Need not found or not related to this charity")

        # تنظیم تاریخ شروع
        start_date = campaign_data.start_date or datetime.utcnow()

        # تنظیم تاریخ پایان
        end_date = campaign_data.end_date
        if campaign_data.duration_days:
            end_date = start_date + timedelta(days=campaign_data.duration_days)

        # ایجاد slug یکتا
        base_slug = campaign_data.title.lower().replace(' ', '-')
        slug = base_slug
        counter = 1
        while True:
            existing = await self.db.execute(
                select(Campaign).where(Campaign.slug == slug)
            )
            if not existing.scalar_one_or_none():
                break
            slug = f"{base_slug}-{counter}"
            counter += 1

        # ایجاد کد اشتراک یکتا
        share_code = self._generate_share_code()

        # ایجاد کمپین
        campaign = Campaign(
            owner_id=owner.id,
            need_id=campaign_data.need_id,
            charity_id=campaign_data.charity_id,
            title=campaign_data.title,
            slug=slug,
            description=campaign_data.description,
            short_description=campaign_data.short_description,
            target_amount=campaign_data.target_amount,
            currency=campaign_data.currency,
            start_date=start_date,
            end_date=end_date,
            duration_days=campaign_data.duration_days,
            status=CampaignStatus.DRAFT,
            campaign_type=campaign_data.campaign_type,
            cover_image=campaign_data.cover_image,
            video_url=campaign_data.video_url,
            personal_message=campaign_data.personal_message,
            dedication_name=campaign_data.dedication_name,
            dedication_message=campaign_data.dedication_message,
            share_code=share_code,
            is_public=campaign_data.is_public,
            allow_comments=campaign_data.allow_comments,
            show_donors=campaign_data.show_donors,
            theme_color=campaign_data.theme_color
        )

        self.db.add(campaign)
        await self.db.commit()
        await self.db.refresh(campaign)

        # ایجاد لینک اشتراک
        campaign.share_url = f"/campaign/{campaign.slug}"
        self.db.add(campaign)
        await self.db.commit()

        return campaign

    # ---------- انتشار کمپین ----------
    async def publish_campaign(
        self,
        campaign_id: int,
        user: User
    ) -> Campaign:
        """انتشار کمپین (فعال کردن)"""

        campaign = await self._get_campaign_with_permission(campaign_id, user)

        if campaign.status != CampaignStatus.DRAFT:
            raise HTTPException(status_code=400, detail="Campaign is not in draft status")

        campaign.status = CampaignStatus.ACTIVE
        campaign.published_at = datetime.utcnow()

        self.db.add(campaign)
        await self.db.commit()
        await self.db.refresh(campaign)

        # ارسال نوتیفیکیشن
        await self._send_campaign_notifications(campaign, "published")

        return campaign

    # ---------- دریافت کمپین ----------
    async def get_campaign(
        self,
        campaign_id: int,
        user: Optional[User] = None
    ) -> Dict[str, Any]:
        """دریافت جزئیات کمپین"""

        campaign = await self.db.get(Campaign, campaign_id)
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        # افزایش بازدید
        campaign.view_count += 1
        self.db.add(campaign)
        await self.db.commit()

        # محاسبه درصد پیشرفت
        progress = (campaign.collected_amount / campaign.target_amount * 100) if campaign.target_amount > 0 else 0

        # روزهای باقی‌مانده
        days_remaining = None
        if campaign.end_date:
            days_remaining = max(0, (campaign.end_date - datetime.utcnow()).days)

        # دریافت کمک‌های اخیر
        recent_donations = await self.db.execute(
            select(CampaignDonation)
            .where(CampaignDonation.campaign_id == campaign.id)
            .order_by(CampaignDonation.donated_at.desc())
            .limit(10)
        )

        # دریافت برترین کمک‌کنندگان
        top_donors_query = select(
            CampaignDonation.donor_id,
            func.sum(CampaignDonation.amount).label('total')
        ).where(
            CampaignDonation.campaign_id == campaign.id
        ).group_by(
            CampaignDonation.donor_id
        ).order_by(
            desc('total')
        ).limit(10)

        top_donors = await self.db.execute(top_donors_query)

        # دریافت نظرات
        comments = await self.db.execute(
            select(CampaignComment)
            .where(
                and_(
                    CampaignComment.campaign_id == campaign.id,
                    CampaignComment.parent_id.is_(None)
                )
            )
            .order_by(CampaignComment.created_at.desc())
            .limit(20)
        )

        data = {
            "id": campaign.id,
            "uuid": campaign.uuid,
            "title": campaign.title,
            "slug": campaign.slug,
            "description": campaign.description,
            "short_description": campaign.short_description,
            "owner_id": campaign.owner_id,
            "owner_name": campaign.owner.display_name if campaign.owner else None,
            "need_id": campaign.need_id,
            "need_title": campaign.need.title if campaign.need else None,
            "charity_id": campaign.charity_id,
            "charity_name": campaign.charity.name if campaign.charity else None,
            "target_amount": campaign.target_amount,
            "currency": campaign.currency,
            "collected_amount": campaign.collected_amount,
            "donor_count": campaign.donor_count,
            "progress_percentage": round(progress, 2),
            "start_date": campaign.start_date,
            "end_date": campaign.end_date,
            "days_remaining": days_remaining,
            "status": campaign.status,
            "campaign_type": campaign.campaign_type,
            "share_code": campaign.share_code,
            "share_url": campaign.share_url,
            "share_count": campaign.share_count,
            "cover_image": campaign.cover_image,
            "video_url": campaign.video_url,
            "personal_message": campaign.personal_message,
            "dedication_name": campaign.dedication_name,
            "dedication_message": campaign.dedication_message,
            "is_featured": campaign.is_featured,
            "is_public": campaign.is_public,
            "allow_comments": campaign.allow_comments,
            "show_donors": campaign.show_donors,
            "view_count": campaign.view_count,
            "conversion_rate": campaign.conversion_rate,
            "team_members": campaign.team_members or [],
            "theme_color": campaign.theme_color,
            "created_at": campaign.created_at,
            "published_at": campaign.published_at,
            "recent_donations": [
                {
                    "id": d.id,
                    "amount": d.amount,
                    "donor_name": d.donor.display_name if d.donor and not d.is_anonymous else "ناشناس",
                    "message": d.message,
                    "donated_at": d.donated_at
                }
                for d in recent_donations.scalars().all()
            ],
            "top_donors": [
                {
                    "donor_id": row.donor_id,
                    "donor_name": (await self.db.get(User, row.donor_id)).display_name if row.donor_id else "ناشناس",
                    "total_amount": float(row.total)
                }
                for row in top_donors.all()
            ],
            "comments": [
                {
                    "id": c.id,
                    "user_id": c.user_id,
                    "user_name": c.user.display_name if c.user else "کاربر",
                    "user_avatar": c.user.avatar_url if c.user else None,
                    "content": c.content,
                    "created_at": c.created_at,
                    "likes": c.likes
                }
                for c in comments.scalars().all()
            ]
        }

        return data

    # ---------- دریافت کمپین با slug ----------
    async def get_campaign_by_slug(
        self,
        slug: str,
        user: Optional[User] = None
    ) -> Dict[str, Any]:
        """دریافت کمپین با slug"""

        result = await self.db.execute(
            select(Campaign).where(Campaign.slug == slug)
        )
        campaign = result.scalar_one_or_none()

        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        return await self.get_campaign(campaign.id, user)

    # ---------- لیست کمپین‌ها ----------
    async def list_campaigns(
        self,
        filters: CampaignFilter,
        user: Optional[User] = None,
        page: int = 1,
        limit: int = 20
    ) -> Dict[str, Any]:
        """لیست کمپین‌ها با فیلتر"""

        query = select(Campaign)

        conditions = []

        # فیلتر وضعیت - فقط کمپین‌های فعال برای عموم
        if not user or not user.is_admin:
            conditions.append(Campaign.status == CampaignStatus.ACTIVE)
            conditions.append(Campaign.is_public == True)
        elif filters.status:
            conditions.append(Campaign.status == filters.status)

        if filters.campaign_type:
            conditions.append(Campaign.campaign_type == filters.campaign_type)

        if filters.charity_id:
            conditions.append(Campaign.charity_id == filters.charity_id)

        if filters.need_id:
            conditions.append(Campaign.need_id == filters.need_id)

        if filters.owner_id:
            conditions.append(Campaign.owner_id == filters.owner_id)

        if filters.is_featured is not None:
            conditions.append(Campaign.is_featured == filters.is_featured)

        if filters.min_target:
            conditions.append(Campaign.target_amount >= filters.min_target)

        if filters.max_target:
            conditions.append(Campaign.target_amount <= filters.max_target)

        if filters.min_progress:
            conditions.append(
                (Campaign.collected_amount / Campaign.target_amount * 100) >= filters.min_progress
            )

        if filters.search_text:
            conditions.append(
                or_(
                    Campaign.title.ilike(f"%{filters.search_text}%"),
                    Campaign.description.ilike(f"%{filters.search_text}%"),
                    Campaign.short_description.ilike(f"%{filters.search_text}%")
                )
            )

        if conditions:
            query = query.where(and_(*conditions))

        # مرتب‌سازی
        if filters.sort_by == "progress":
            # درصد پیشرفت
            query = query.order_by(
                desc(Campaign.collected_amount / Campaign.target_amount)
            )
        elif filters.sort_by == "popular":
            # محبوبیت (تعداد کمک + بازدید)
            query = query.order_by(
                desc(Campaign.donor_count + Campaign.view_count * 0.1)
            )
        elif filters.sort_by == "ending_soon":
            # در حال اتمام
            query = query.order_by(Campaign.end_date.asc())
        else:
            sort_column = getattr(Campaign, filters.sort_by, Campaign.created_at)
            if filters.sort_order == "desc":
                query = query.order_by(sort_column.desc())
            else:
                query = query.order_by(sort_column.asc())

        # شمارش کل
        total_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(total_query)

        # صفحه‌بندی
        offset = (page - 1) * limit
        query = query.offset(offset).limit(limit)

        # اجرای کوئری
        result = await self.db.execute(query)
        campaigns = result.scalars().all()

        # تبدیل به فرمت خروجی
        items = []
        for campaign in campaigns:
            progress = (campaign.collected_amount / campaign.target_amount * 100) if campaign.target_amount > 0 else 0
            items.append({
                "id": campaign.id,
                "uuid": campaign.uuid,
                "title": campaign.title,
                "slug": campaign.slug,
                "short_description": campaign.short_description,
                "owner_id": campaign.owner_id,
                "owner_name": campaign.owner.display_name if campaign.owner else None,
                "charity_id": campaign.charity_id,
                "charity_name": campaign.charity.name if campaign.charity else None,
                "target_amount": campaign.target_amount,
                "collected_amount": campaign.collected_amount,
                "currency": campaign.currency,
                "progress_percentage": round(progress, 2),
                "donor_count": campaign.donor_count,
                "end_date": campaign.end_date,
                "days_remaining": max(0, (campaign.end_date - datetime.utcnow()).days) if campaign.end_date else None,
                "status": campaign.status,
                "campaign_type": campaign.campaign_type,
                "cover_image": campaign.cover_image,
                "is_featured": campaign.is_featured,
                "share_count": campaign.share_count,
                "view_count": campaign.view_count,
                "created_at": campaign.created_at,
                "published_at": campaign.published_at
            })

        return {
            "items": items,
            "total": total or 0,
            "page": page,
            "limit": limit,
            "total_pages": math.ceil(total / limit) if total and total > 0 else 0
        }

    # ---------- کمک به کمپین ----------
    async def donate_to_campaign(
        self,
        donate_data: CampaignDonate,
        donor: Optional[User],
        background_tasks: BackgroundTasks
    ) -> CampaignDonation:
        """کمک به کمپین"""

        campaign = await self.db.get(Campaign, donate_data.campaign_id)
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        if campaign.status != CampaignStatus.ACTIVE:
            raise HTTPException(status_code=400, detail="Campaign is not active")

        if campaign.end_date and campaign.end_date < datetime.utcnow():
            campaign.status = CampaignStatus.EXPIRED
            self.db.add(campaign)
            await self.db.commit()
            raise HTTPException(status_code=400, detail="Campaign has expired")

        # ایجاد کمک
        donation = CampaignDonation(
            campaign_id=campaign.id,
            donor_id=donor.id if donor else None,
            amount=donate_data.amount,
            currency=donate_data.currency,
            message=donate_data.message,
            is_anonymous=donate_data.is_anonymous
        )

        # اگر کد اشتراک دارد
        if donate_data.share_code:
            share = await self.db.execute(
                select(CampaignShare).where(
                    CampaignShare.share_code == donate_data.share_code
                )
            )
            share = share.scalar_one_or_none()
            if share:
                donation.share_id = share.id
                donation.shared_by = share.user_id

        self.db.add(donation)

        # به‌روزرسانی آمار کمپین
        campaign.collected_amount += donate_data.amount
        campaign.donor_count += 1
        campaign.conversion_rate = (campaign.donor_count / campaign.view_count * 100) if campaign.view_count > 0 else 0

        # به‌روزرسانی آمار اشتراک (اگر وجود دارد)
        if donation.share_id:
            share = await self.db.get(CampaignShare, donation.share_id)
            share.donation_count += 1
            share.donation_amount += donate_data.amount
            share.conversion_rate = (share.donation_count / share.click_count * 100) if share.click_count > 0 else 0
            self.db.add(share)

        self.db.add(campaign)
        await self.db.commit()
        await self.db.refresh(donation)

        # اگر به هدف رسید
        if campaign.collected_amount >= campaign.target_amount:
            campaign.status = CampaignStatus.COMPLETED
            campaign.completed_at = datetime.utcnow()
            self.db.add(campaign)
            await self.db.commit()

        # ارسال نوتیفیکیشن
        background_tasks.add_task(
            self._send_donation_notifications,
            campaign.id,
            donation.id
        )

        return donation

    # ---------- اشتراک‌گذاری کمپین ----------
    async def share_campaign(
        self,
        share_data: CampaignShareCreate,
        user: User
    ) -> CampaignShare:
        """اشتراک‌گذاری کمپین"""

        campaign = await self.db.get(Campaign, share_data.campaign_id)
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        # ایجاد کد اشتراک یکتا
        share_code = self._generate_share_code()

        share = CampaignShare(
            campaign_id=campaign.id,
            user_id=user.id,
            share_code=share_code,
            platform=share_data.platform,
            share_url=f"{campaign.share_url}?ref={share_code}"
        )

        self.db.add(share)

        # به‌روزرسانی آمار کمپین
        campaign.share_count += 1
        self.db.add(campaign)

        await self.db.commit()
        await self.db.refresh(share)

        return share

    # ---------- ثبت کلیک روی لینک اشتراک ----------
    async def track_share_click(
        self,
        share_code: str
    ) -> Dict[str, Any]:
        """ثبت کلیک روی لینک اشتراک"""

        result = await self.db.execute(
            select(CampaignShare).where(CampaignShare.share_code == share_code)
        )
        share = result.scalar_one_or_none()

        if share:
            share.click_count += 1
            share.last_clicked_at = datetime.utcnow()
            self.db.add(share)
            await self.db.commit()

            return {
                "campaign_id": share.campaign_id,
                "share_id": share.id,
                "click_count": share.click_count
            }

        return {}

    # ---------- اضافه کردن نظر ----------
    async def add_comment(
        self,
        comment_data: CampaignCommentCreate,
        user: User
    ) -> CampaignComment:
        """اضافه کردن نظر به کمپین"""

        campaign = await self.db.get(Campaign, comment_data.campaign_id)
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        if not campaign.allow_comments:
            raise HTTPException(status_code=400, detail="Comments are disabled for this campaign")

        comment = CampaignComment(
            campaign_id=campaign.id,
            user_id=user.id,
            content=comment_data.content,
            parent_id=comment_data.parent_id
        )

        self.db.add(comment)
        await self.db.commit()
        await self.db.refresh(comment)

        return comment

    # ---------- کمپین‌های من ----------
    async def get_my_campaigns(
        self,
        user: User,
        status: Optional[CampaignStatus] = None,
        page: int = 1,
        limit: int = 20
    ) -> Dict[str, Any]:
        """کمپین‌های من"""

        filters = CampaignFilter(owner_id=user.id, status=status)
        return await self.list_campaigns(filters, user, page, limit)

    # ---------- کمپین‌هایی که حمایت کردم ----------
    async def get_supported_campaigns(
        self,
        user: User,
        page: int = 1,
        limit: int = 20
    ) -> Dict[str, Any]:
        """کمپین‌هایی که کاربر حمایت کرده"""

        # دریافت کمپین‌هایی که کاربر به آنها کمک کرده
        subquery = select(CampaignDonation.campaign_id).where(
            CampaignDonation.donor_id == user.id
        ).distinct()

        query = select(Campaign).where(Campaign.id.in_(subquery))

        # شمارش کل
        total_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(total_query)

        # صفحه‌بندی
        offset = (page - 1) * limit
        query = query.order_by(Campaign.created_at.desc())
        query = query.offset(offset).limit(limit)

        result = await self.db.execute(query)
        campaigns = result.scalars().all()

        # تبدیل به فرمت خروجی
        items = []
        for campaign in campaigns:
            # دریافت مبلغ کمک شده توسط این کاربر
            donation_amount = await self.db.scalar(
                select(func.sum(CampaignDonation.amount))
                .where(
                    and_(
                        CampaignDonation.campaign_id == campaign.id,
                        CampaignDonation.donor_id == user.id
                    )
                )
            )

            progress = (campaign.collected_amount / campaign.target_amount * 100) if campaign.target_amount > 0 else 0
            items.append({
                "id": campaign.id,
                "title": campaign.title,
                "slug": campaign.slug,
                "charity_name": campaign.charity.name if campaign.charity else None,
                "target_amount": campaign.target_amount,
                "collected_amount": campaign.collected_amount,
                "progress_percentage": round(progress, 2),
                "donated_amount": float(donation_amount or 0),
                "status": campaign.status,
                "end_date": campaign.end_date,
                "cover_image": campaign.cover_image,
                "created_at": campaign.created_at
            })

        return {
            "items": items,
            "total": total or 0,
            "page": page,
            "limit": limit,
            "total_pages": math.ceil(total / limit) if total and total > 0 else 0
        }

    # ---------- آمار کمپین ----------
    async def get_campaign_stats(
        self,
        campaign_id: int,
        user: User
    ) -> Dict[str, Any]:
        """آمار دقیق کمپین"""

        campaign = await self._get_campaign_with_permission(campaign_id, user)

        # آمار کمک‌ها بر اساس روز
        daily_stats = await self.db.execute(
            select(
                func.date(CampaignDonation.donated_at).label('date'),
                func.count(CampaignDonation.id).label('count'),
                func.sum(CampaignDonation.amount).label('total')
            ).where(
                CampaignDonation.campaign_id == campaign_id
            ).group_by(
                func.date(CampaignDonation.donated_at)
            ).order_by('date')
        )

        # آمار اشتراک‌گذاری
        share_stats = await self.db.execute(
            select(
                CampaignShare.platform,
                func.count(CampaignShare.id).label('count'),
                func.sum(CampaignShare.click_count).label('clicks'),
                func.sum(CampaignShare.donation_count).label('donations'),
                func.sum(CampaignShare.donation_amount).label('amount')
            ).where(
                CampaignShare.campaign_id == campaign_id
            ).group_by(CampaignShare.platform)
        )

        return {
            "campaign_id": campaign_id,
            "campaign_title": campaign.title,
            "overall": {
                "views": campaign.view_count,
                "unique_visitors": campaign.unique_visitors,
                "donors": campaign.donor_count,
                "donations": len(campaign.donations),
                "collected": campaign.collected_amount,
                "target": campaign.target_amount,
                "progress": (campaign.collected_amount / campaign.target_amount * 100) if campaign.target_amount > 0 else 0,
                "shares": campaign.share_count,
                "conversion_rate": campaign.conversion_rate
            },
            "daily_breakdown": [
                {
                    "date": row.date,
                    "donations": row.count,
                    "amount": float(row.total or 0)
                }
                for row in daily_stats.all()
            ],
            "share_breakdown": [
                {
                    "platform": row.platform or "direct",
                    "shares": row.count,
                    "clicks": row.clicks or 0,
                    "donations": row.donations or 0,
                    "amount": float(row.amount or 0),
                    "click_rate": (row.clicks / row.count * 100) if row.count > 0 else 0,
                    "donation_rate": (row.donations / row.clicks * 100) if row.clicks > 0 else 0
                }
                for row in share_stats.all()
            ]
        }

    # ---------- Helper Methods ----------
    async def _get_campaign(self, campaign_id: int) -> Campaign:
        campaign = await self.db.get(Campaign, campaign_id)
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        return campaign

    async def _get_campaign_with_permission(
        self,
        campaign_id: int,
        user: User
    ) -> Campaign:
        campaign = await self._get_campaign(campaign_id)

        if campaign.owner_id != user.id and not user.is_admin:
            raise HTTPException(status_code=403, detail="Not authorized")

        return campaign

    async def _send_campaign_notifications(self, campaign: Campaign, action: str):
        """ارسال نوتیفیکیشن کمپین"""

        # به سازنده کمپین
        await self.notification_service.send_notification(
            user_id=campaign.owner_id,
            type="system",
            title="📢 کمپین شما منتشر شد",
            message=f"کمپین «{campaign.title}» با موفقیت منتشر شد. لینک اشتراک‌گذاری: {campaign.share_url}",
            data={
                "campaign_id": campaign.id,
                "campaign_slug": campaign.slug,
                "action": action
            }
        )

        # به خیریه
        if campaign.charity_id:
            charity = await self.db.get(Charity, campaign.charity_id)
            if charity and charity.manager_id:
                await self.notification_service.send_notification(
                    user_id=charity.manager_id,
                    type="system",
                    title="🎯 کمپین جدید برای خیریه شما",
                    message=f"یک کمپین جدید با عنوان «{campaign.title}» برای خیریه شما ایجاد شد.",
                    data={
                        "campaign_id": campaign.id,
                        "charity_id": campaign.charity_id
                    }
                )

    async def _send_donation_notifications(self, campaign_id: int, donation_id: int):
        """ارسال نوتیفیکیشن کمک به کمپین"""

        campaign = await self.db.get(Campaign, campaign_id)
        donation = await self.db.get(CampaignDonation, donation_id)

        # به سازنده کمپین
        await self.notification_service.send_notification(
            user_id=campaign.owner_id,
            type="system",
            title="🎉 کمک جدید به کمپین شما",
            message=f"یک کمک {donation.amount:,.0f} تومانی به کمپین «{campaign.title}» اضافه شد.",
            data={
                "campaign_id": campaign.id,
                "donation_id": donation.id,
                "amount": donation.amount
            }
        )

    def _generate_share_code(self) -> str:
        """تولید کد اشتراک یکتا"""
        return secrets.token_urlsafe(8)