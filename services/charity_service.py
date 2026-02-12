# app/services/charity_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, asc
from fastapi import HTTPException, status
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import math
from models.charity import Charity
from models.user import User
from models.need_ad import NeedAd
from models.donation import Donation
from models.need_verification import NeedVerification
from models.product import Product
from schemas.charity import (
    CharityCreate, CharityUpdate, CharityStatusUpdate,
    CharityVerification, CharityManagerUpdate, CharityFilter
)


class CharityService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_charity(self, charity_data: CharityCreate, admin_user: User) -> Charity:
        """ایجاد خیریه جدید (فقط توسط ادمین)"""
        # بررسی مدیر
        manager = await self.db.get(User, charity_data.manager_id)
        if not manager:
            raise HTTPException(status_code=404, detail="Manager user not found")

        # بررسی تکراری نبودن نام و ایمیل
        name_exists = await self.db.execute(
            select(Charity).where(Charity.name == charity_data.name)
        )
        if name_exists.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Charity name already exists")

        email_exists = await self.db.execute(
            select(Charity).where(Charity.email == charity_data.email)
        )
        if email_exists.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Charity email already exists")

        # ایجاد خیریه
        charity = Charity(
            name=charity_data.name,
            description=charity_data.description,
            charity_type=charity_data.charity_type,
            email=charity_data.email,
            phone=charity_data.phone,
            address=charity_data.address,
            website=charity_data.website,
            registration_number=charity_data.registration_number,
            logo_url=charity_data.logo_url,
            manager_id=charity_data.manager_id,
            verified=False,
            active=True,
            status="pending_verification"
        )

        self.db.add(charity)
        await self.db.commit()
        await self.db.refresh(charity)
        return charity

    async def update_charity(self, charity_id: int, update_data: CharityUpdate, user: User) -> Charity:
        """ویرایش اطلاعات خیریه"""
        charity = await self._get_charity_with_permission(charity_id, user)

        # بررسی تکراری نبودن نام و ایمیل
        if update_data.name and update_data.name != charity.name:
            name_exists = await self.db.execute(
                select(Charity).where(
                    and_(
                        Charity.name == update_data.name,
                        Charity.id != charity_id
                    )
                )
            )
            if name_exists.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="Charity name already exists")

        if update_data.email and update_data.email != charity.email:
            email_exists = await self.db.execute(
                select(Charity).where(
                    and_(
                        Charity.email == update_data.email,
                        Charity.id != charity_id
                    )
                )
            )
            if email_exists.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="Charity email already exists")

        # به‌روزرسانی فیلدها
        for key, value in update_data.dict(exclude_unset=True).items():
            if value is not None:
                setattr(charity, key, value)

        self.db.add(charity)
        await self.db.commit()
        await self.db.refresh(charity)
        return charity

    async def update_charity_status(
            self, charity_id: int, status_data: CharityStatusUpdate, admin_user: User
    ) -> Charity:
        """تغییر وضعیت خیریه (فقط ادمین)"""
        charity = await self._get_charity(charity_id)

        # بررسی اینکه کاربر ادمین است
        user_roles = [r.key for r in admin_user.roles]
        if "ADMIN" not in user_roles:
            raise HTTPException(status_code=403, detail="Only admins can change charity status")

        charity.status = status_data.status

        # اگر غیرفعال شد، همه نیازهای فعال هم غیرفعال شوند
        if status_data.status == "inactive" or status_data.status == "suspended":
            # غیرفعال کردن نیازهای فعال
            needs = await self.db.execute(
                select(NeedAd).where(
                    and_(
                        NeedAd.charity_id == charity_id,
                        NeedAd.status.in_(["active", "pending", "approved"])
                    )
                )
            )
            for need in needs.scalars().all():
                need.status = "cancelled"
                self.db.add(need)

        # ذخیره دلیل تغییر وضعیت
        if status_data.reason:
            # در آینده می‌توان در audit log ذخیره کرد
            pass

        self.db.add(charity)
        await self.db.commit()
        await self.db.refresh(charity)
        return charity

    async def verify_charity(
            self, charity_id: int, verification_data: CharityVerification, admin_user: User
    ) -> Charity:
        """تأیید یا رد خیریه (فقط ادمین)"""
        charity = await self._get_charity(charity_id)

        # بررسی اینکه کاربر ادمین است
        user_roles = [r.key for r in admin_user.roles]
        if "ADMIN" not in user_roles and "CHARITY_MANAGER" not in user_roles:
            raise HTTPException(status_code=403, detail="Not authorized to verify charities")

        charity.verified = verification_data.verified
        charity.status = "active" if verification_data.verified else "pending_verification"

        # ذخیره یادداشت‌های تأیید
        if verification_data.verification_notes:
            # در آینده می‌توان در audit log ذخیره کرد
            pass

        self.db.add(charity)
        await self.db.commit()
        await self.db.refresh(charity)
        return charity

    async def update_charity_manager(
            self, charity_id: int, manager_data: CharityManagerUpdate, admin_user: User
    ) -> Charity:
        """تغییر مدیر خیریه (فقط ادمین)"""
        charity = await self._get_charity(charity_id)

        # بررسی اینکه کاربر ادمین است
        user_roles = [r.key for r in admin_user.roles]
        if "ADMIN" not in user_roles:
            raise HTTPException(status_code=403, detail="Only admins can change charity manager")

        # بررسی مدیر جدید
        new_manager = await self.db.get(User, manager_data.new_manager_id)
        if not new_manager:
            raise HTTPException(status_code=404, detail="New manager not found")

        # تغییر مدیر
        old_manager_id = charity.manager_id
        charity.manager_id = manager_data.new_manager_id

        # ذخیره تاریخچه تغییر مدیر
        # در آینده می‌توان در audit log ذخیره کرد

        self.db.add(charity)
        await self.db.commit()
        await self.db.refresh(charity)
        return charity

    async def get_charity(self, charity_id: int, user: Optional[User] = None) -> Dict[str, Any]:
        """دریافت اطلاعات خیریه"""
        charity = await self._get_charity(charity_id)

        # محاسبه آمار
        stats = await self._calculate_charity_stats(charity_id)

        # آماده‌سازی اطلاعات مدیر
        manager_info = {}
        if charity.manager:
            manager_info = {
                "manager_name": charity.manager.username or charity.manager.email,
                "manager_email": charity.manager.email if self._can_view_manager_details(user) else None,
                "manager_phone": charity.manager.phone if self._can_view_manager_details(user) else None
            }

        # اطلاعات پایه
        base_data = {
            "id": charity.id,
            "uuid": charity.uuid,
            "name": charity.name,
            "description": charity.description,
            "charity_type": charity.charity_type,
            "email": charity.email,
            "phone": charity.phone,
            "address": charity.address,
            "website": charity.website,
            "registration_number": charity.registration_number,
            "logo_url": charity.logo_url,
            "verified": charity.verified,
            "active": charity.active,
            "status": charity.status,
            "manager_id": charity.manager_id,
            "created_at": charity.created_at,
            "updated_at": charity.updated_at,
            **stats,
            **manager_info
        }

        # اگر کاربر مجاز است، اطلاعات بیشتر
        if self._can_view_charity_details(charity, user):
            # نیازهای اخیر
            recent_needs = await self.db.execute(
                select(NeedAd)
                .where(NeedAd.charity_id == charity_id)
                .order_by(NeedAd.created_at.desc())
                .limit(5)
            )

            base_data["recent_needs"] = [
                {
                    "id": need.id,
                    "title": need.title,
                    "status": need.status,
                    "target_amount": need.target_amount,
                    "collected_amount": need.collected_amount,
                    "created_at": need.created_at
                }
                for need in recent_needs.scalars().all()
            ]

            # تأییدیه‌های داده شده
            verifications_given = await self.db.execute(
                select(NeedVerification)
                .where(NeedVerification.charity_id == charity_id)
                .order_by(NeedVerification.created_at.desc())
                .limit(10)
            )

            base_data["verifications_given"] = [
                {
                    "need_id": v.need_id,
                    "need_title": v.need.title if v.need else None,
                    "status": v.status,
                    "comment": v.comment,
                    "created_at": v.created_at
                }
                for v in verifications_given.scalars().all()
            ]

        return base_data

    async def list_charities(
            self, filters: CharityFilter, user: Optional[User] = None, page: int = 1, limit: int = 20
    ) -> Dict[str, Any]:
        """لیست خیریه‌ها با فیلتر و صفحه‌بندی"""
        query = select(Charity).where(Charity.active == True)

        # اعمال فیلترها
        if filters.charity_type:
            query = query.where(Charity.charity_type == filters.charity_type)

        if filters.status:
            query = query.where(Charity.status == filters.status)

        if filters.verified is not None:
            query = query.where(Charity.verified == filters.verified)

        if filters.active is not None:
            query = query.where(Charity.active == filters.active)

        if filters.search_text:
            query = query.where(
                or_(
                    Charity.name.ilike(f"%{filters.search_text}%"),
                    Charity.description.ilike(f"%{filters.search_text}%"),
                    Charity.address.ilike(f"%{filters.search_text}%")
                )
            )

        # مرتب‌سازی
        sort_column = getattr(Charity, filters.sort_by, Charity.created_at)
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
        charities = result.scalars().all()

        # تبدیل به فرمت خروجی
        charity_list = []
        for charity in charities:
            # محاسبه آمار پایه
            stats = await self._calculate_charity_stats(charity.id)

            charity_list.append({
                "id": charity.id,
                "uuid": charity.uuid,
                "name": charity.name,
                "description": charity.description[:100] + "..." if len(
                    charity.description) > 100 else charity.description,
                "charity_type": charity.charity_type,
                "email": charity.email,
                "phone": charity.phone,
                "address": charity.address,
                "website": charity.website,
                "logo_url": charity.logo_url,
                "verified": charity.verified,
                "active": charity.active,
                "status": charity.status,
                "manager_id": charity.manager_id,
                "manager_name": charity.manager.username if charity.manager else None,
                "created_at": charity.created_at,
                **{k: v for k, v in stats.items() if k in [
                    'needs_count', 'active_needs_count', 'completed_needs_count',
                    'total_donations', 'total_donors', 'verification_score'
                ]}
            })

        return {
            "items": charity_list,
            "total": total or 0,
            "page": page,
            "limit": limit,
            "total_pages": math.ceil(total / limit) if total and total > 0 else 0
        }

    async def get_charity_stats(
            self, charity_id: int, period_days: int = 30, user: Optional[User] = None
    ) -> Dict[str, Any]:
        """دریافت آمار دقیق خیریه"""
        charity = await self._get_charity(charity_id)

        # بررسی دسترسی
        if not self._can_view_charity_details(charity, user):
            raise HTTPException(status_code=403, detail="Not authorized")

        # تاریخ شروع دوره
        period_start = datetime.utcnow() - timedelta(days=period_days)

        # آمار نیازها
        from sqlalchemy import case
        needs_stats = await self.db.execute(
            select(
                func.count(NeedAd.id).label("total_needs"),
                func.sum(case([(NeedAd.status == "active", 1)], else_=0)).label("active_needs"),
                func.sum(case([(NeedAd.status == "completed", 1)], else_=0)).label("completed_needs"),
                func.sum(case([(NeedAd.status == "pending", 1)], else_=0)).label("pending_needs"),
                func.sum(case([(NeedAd.status == "rejected", 1)], else_=0)).label("rejected_needs")
            ).where(
                and_(
                    NeedAd.charity_id == charity_id,
                    NeedAd.created_at >= period_start
                )
            )
        )
        needs_data = needs_stats.first()

        # آمار کمک‌ها
        donations_stats = await self.db.execute(
            select(
                func.count(Donation.id).label("total_donations"),
                func.sum(Donation.amount).label("total_amount"),
                func.avg(Donation.amount).label("average_donation"),
                func.max(Donation.amount).label("largest_donation"),
                func.min(Donation.amount).label("smallest_donation")
            ).where(
                and_(
                    Donation.charity_id == charity_id,
                    Donation.status == "completed",
                    Donation.created_at >= period_start
                )
            )
        )
        donations_data = donations_stats.first()

        # آمار کمک‌کنندگان
        donors_stats = await self.db.execute(
            select(
                func.count(func.distinct(Donation.donor_id)).label("total_donors"),
                func.sum(case([
                    (Donation.created_at >= datetime.utcnow() - timedelta(days=7), 1)
                ], else_=0)).label("new_donors")
            ).where(
                and_(
                    Donation.charity_id == charity_id,
                    Donation.status == "completed",
                    Donation.created_at >= period_start
                )
            )
        )
        donors_data = donors_stats.first()

        # آمار تأییدیه‌ها
        verifications_stats = await self.db.execute(
            select(
                func.count(NeedVerification.id).label("total_given"),
                func.sum(case([
                    (NeedVerification.status == "approved", 1)
                ], else_=0)).label("approved_given")
            ).where(
                and_(
                    NeedVerification.charity_id == charity_id,
                    NeedVerification.created_at >= period_start
                )
            )
        )
        verifications_data = verifications_stats.first()

        # آمار محصولات فروشگاه
        products_stats = await self.db.execute(
            select(
                func.count(Product.id).label("total_products"),
                func.sum(Product.charity_fixed_amount +
                         Product.price * (Product.charity_percentage / 100)).label("total_revenue")
            ).where(
                and_(
                    Product.charity_id == charity_id,
                    Product.status == "active"
                )
            )
        )
        products_data = products_stats.first()

        return {
            "charity_id": charity_id,
            "period_start": period_start,
            "period_end": datetime.utcnow(),
            "period_days": period_days,

            # آمار نیازها
            "total_needs": needs_data.total_needs or 0,
            "active_needs": needs_data.active_needs or 0,
            "completed_needs": needs_data.completed_needs or 0,
            "pending_needs": needs_data.pending_needs or 0,
            "rejected_needs": needs_data.rejected_needs or 0,

            # آمار مالی
            "total_donations_count": donations_data.total_donations or 0,
            "total_donations_amount": float(donations_data.total_amount or 0),
            "average_donation": float(donations_data.average_donation or 0),
            "largest_donation": float(donations_data.largest_donation or 0),
            "smallest_donation": float(donations_data.smallest_donation or 0),

            # آمار کمک‌کنندگان
            "total_donors": donors_data.total_donors or 0,
            "new_donors": donors_data.new_donors or 0,

            # تأییدیه‌ها
            "verifications_given": verifications_data.total_given or 0,
            "verifications_approved": verifications_data.approved_given or 0,
            "verification_approval_rate": (
                (verifications_data.approved_given / verifications_data.total_given * 100)
                if verifications_data.total_given and verifications_data.total_given > 0
                else 0
            ),

            # فروشگاه
            "shop_products_count": products_data.total_products or 0,
            "shop_revenue_for_charity": float(products_data.total_revenue or 0)
        }

    # ---------- Helper Methods ----------
    async def _get_charity(self, charity_id: int) -> Charity:
        """دریافت خیریه با بررسی وجود"""
        charity = await self.db.get(Charity, charity_id)
        if not charity:
            raise HTTPException(status_code=404, detail="Charity not found")
        return charity

    async def _get_charity_with_permission(self, charity_id: int, user: User) -> Charity:
        """دریافت خیریه با بررسی مجوز"""
        charity = await self._get_charity(charity_id)

        user_roles = [r.key for r in user.roles]

        # مدیر خیریه یا ادمین می‌توانند ویرایش کنند
        if charity.manager_id != user.id and "ADMIN" not in user_roles:
            raise HTTPException(status_code=403, detail="Not authorized to edit this charity")

        return charity

    async def _calculate_charity_stats(self, charity_id: int) -> Dict[str, Any]:
        """محاسبه آمار پایه خیریه"""
        from sqlalchemy.sql import case

        # شمارش نیازها
        needs_count = await self.db.execute(
            select(func.count(NeedAd.id))
            .where(NeedAd.charity_id == charity_id)
        )

        active_needs_count = await self.db.execute(
            select(func.count(NeedAd.id))
            .where(
                and_(
                    NeedAd.charity_id == charity_id,
                    NeedAd.status == "active"
                )
            )
        )

        completed_needs_count = await self.db.execute(
            select(func.count(NeedAd.id))
            .where(
                and_(
                    NeedAd.charity_id == charity_id,
                    NeedAd.status == "completed"
                )
            )
        )

        # مجموع کمک‌ها
        total_donations = await self.db.execute(
            select(func.coalesce(func.sum(Donation.amount), 0))
            .where(
                and_(
                    Donation.charity_id == charity_id,
                    Donation.status == "completed"
                )
            )
        )

        # تعداد کمک‌کنندگان منحصر به فرد
        total_donors = await self.db.execute(
            select(func.count(func.distinct(Donation.donor_id)))
            .where(
                and_(
                    Donation.charity_id == charity_id,
                    Donation.status == "completed"
                )
            )
        )

        # امتیاز تأییدیه (نسبت تأییدیه‌های APPROVED به کل)
        verification_stats = await self.db.execute(
            select(
                func.count(NeedVerification.id).label("total"),
                func.sum(case([(NeedVerification.status == "approved", 1)], else_=0)).label("approved")
            ).where(NeedVerification.charity_id == charity_id)
        )
        stats = verification_stats.first()

        verification_score = (
            (stats.approved / stats.total * 100) if stats and stats.total and stats.total > 0 else 0
        )

        return {
            "needs_count": needs_count.scalar() or 0,
            "active_needs_count": active_needs_count.scalar() or 0,
            "completed_needs_count": completed_needs_count.scalar() or 0,
            "total_donations": float(total_donations.scalar() or 0),
            "total_donors": total_donors.scalar() or 0,
            "verification_score": round(verification_score, 2)
        }

    def _can_view_charity_details(self, charity: Charity, user: Optional[User]) -> bool:
        """بررسی مجوز مشاهده جزئیات خیریه"""
        if not user:
            return True  # اطلاعات پایه عمومی هستند

        user_roles = [r.key for r in user.roles]

        # ادمین، مدیر خیریه، یا مدیر این خیریه همیشه دسترسی دارند
        if "ADMIN" in user_roles or "CHARITY_MANAGER" in user_roles:
            return True

        if charity.manager_id == user.id:
            return True

        return True  # اطلاعات خیریه عمومی است

    def _can_view_manager_details(self, user: Optional[User]) -> bool:
        """بررسی مجوز مشاهده اطلاعات مدیر"""
        if not user:
            return False

        user_roles = [r.key for r in user.roles]
        return "ADMIN" in user_roles or "CHARITY_MANAGER" in user_roles