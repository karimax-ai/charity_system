# app/services/need_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from fastapi import HTTPException, status, UploadFile
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Literal
import math

from models.need_ad import NeedAd
from models.charity import Charity
from models.need_social_share import NeedSocialShare
from models.user import User
from models.need_verification import NeedVerification, VerificationStatus
from core.permissions import get_current_user
from schemas.file import FileUpload
from services.need_emergency_service import NeedEmergencyService

# تعریف Enums برای استفاده در service
NeedStatus = Literal["draft", "pending", "approved", "rejected", "active", "completed", "cancelled"]
PrivacyLevel = Literal["public", "protected", "private"]


class NeedService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_need(self, need_data, user: User, charity_id: int) -> NeedAd:
        """ایجاد نیاز جدید"""
        from schemas.need import NeedAdCreate  # Import در اینجا

        # بررسی وجود خیریه
        charity = await self.db.get(Charity, charity_id)
        if not charity:
            raise HTTPException(status_code=404, detail="Charity not found")

        # بررسی مجوز کاربر برای این خیریه
        user_roles = [r.key for r in user.roles]
        if "ADMIN" not in user_roles and \
                "CHARITY_MANAGER" not in user_roles and \
                charity.manager_id != user.id:
            raise HTTPException(status_code=403, detail="Not authorized for this charity")

        # ایجاد نیاز
        need = NeedAd(
            title=need_data.title,
            short_description=need_data.short_description,
            description=need_data.description,
            category=need_data.category,
            target_amount=need_data.target_amount,
            currency=need_data.currency,
            city=need_data.city,
            province=need_data.province,
            privacy_level=need_data.privacy_level,
            is_urgent=need_data.is_urgent,
            is_emergency=need_data.is_emergency,
            emergency_type=need_data.emergency_type,
            latitude=need_data.latitude,
            longitude=need_data.longitude,
            deadline=need_data.deadline,
            start_date=need_data.start_date,
            end_date=need_data.end_date,
            attachments=need_data.attachments or [],
            charity_id=charity_id,
            needy_user_id=user.id if "NEEDY" in user_roles else None,
            created_by_id=user.id,
            status="draft"  # استفاده از string literal
        )

        # اگر کاربر نیازمند است، وضعیت PENDING
        if "NEEDY" in user_roles:
            need.status = "pending"

        self.db.add(need)
        await self.db.commit()
        await self.db.refresh(need)
        return need

    # services/need_service.py - اضافه کردن مدیریت فایل‌ها
    async def add_attachment_to_need(
            self,
            need_id: int,
            file: UploadFile,
            user: User,
            description: Optional[str] = None
    ):
        """اضافه کردن فایل به نیاز"""
        need = await self._get_need_with_permission(need_id, user)

        # ایجاد سرویس فایل
        from services.file_service import FileService
        file_service = FileService(self.db)

        upload_data = FileUpload(
            title=file.filename,
            description=description,
            access_level="sensitive",  # فایل‌های نیاز حساس هستند
            entity_type="need_ad",
            entity_id=need_id,
            tags=["need_attachment"]
        )

        file_attachment = await file_service.upload_file(
            file, upload_data, user, encrypt_sensitive=True
        )

        # اضافه کردن به لیست attachments نیاز
        current_attachments = need.attachments or []
        current_attachments.append({
            "file_id": file_attachment.id,
            "file_name": file_attachment.original_filename,
            "uploaded_by": user.id,
            "uploaded_at": file_attachment.uploaded_at.isoformat(),
            "description": description
        })

        need.attachments = current_attachments
        self.db.add(need)
        await self.db.commit()

        return file_attachment

    async def update_need(self, need_id: int, update_data, user: User) -> NeedAd:
        """ویرایش نیاز"""
        from schemas.need import NeedAdUpdate  # Import در اینجا

        need = await self._get_need_with_permission(need_id, user)

        # فقط در حالت‌های خاص اجازه ویرایش داریم
        if need.status not in ["draft", "pending", "rejected"]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot edit need in {need.status} status"
            )

        # به‌روزرسانی فیلدها
        for key, value in update_data.dict(exclude_unset=True).items():
            if value is not None:
                setattr(need, key, value)

        # اگر وضعیت REJECTED بود و ویرایش شد، به PENDING برگردان
        if need.status == "rejected":
            need.status = "pending"

        self.db.add(need)
        await self.db.commit()
        await self.db.refresh(need)
        return need

    async def update_need_status(
            self, need_id: int, status_data, user: User
    ) -> NeedAd:
        """تغییر وضعیت نیاز (توسط مدیر/ادمین)"""
        from schemas.need import NeedAdStatusUpdate  # Import در اینجا

        need = await self._get_need_with_permission(need_id, user, require_admin=True)

        # بررسی انتقال وضعیت مجاز
        allowed_transitions = {
            "draft": ["pending", "cancelled"],
            "pending": ["approved", "rejected"],
            "approved": ["active", "cancelled"],
            "active": ["completed", "cancelled"],
            "rejected": ["pending", "cancelled"],
        }

        if status_data.status not in allowed_transitions.get(need.status, []):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot change status from {need.status} to {status_data.status}"
            )

        need.status = status_data.status

        # اگر رد شد، دلیل را ذخیره کن
        if status_data.status == "rejected" and hasattr(status_data, 'reject_reason'):
            # در attachments دلیل رد را ذخیره می‌کنیم
            rejection_record = {
                "type": "rejection_reason",
                "reason": status_data.reject_reason,
                "rejected_by": user.id,
                "rejected_at": datetime.utcnow().isoformat()
            }
            current_attachments = need.attachments or []
            current_attachments.append(rejection_record)
            need.attachments = current_attachments

        self.db.add(need)
        await self.db.commit()
        await self.db.refresh(need)
        return need

    async def get_need(self, need_id: int, user: Optional[User] = None) -> Dict[str, Any]:
        """دریافت نیاز با کنترل دسترسی"""
        result = await self.db.execute(
            select(NeedAd).where(NeedAd.id == need_id)
        )
        need = result.scalar_one_or_none()

        if not need:
            raise HTTPException(status_code=404, detail="Need not found")

        # بررسی سطح دسترسی
        can_view_details = self._check_view_permission(need, user)

        # محاسبه پیشرفت
        progress = (need.collected_amount / need.target_amount * 100) if need.target_amount > 0 else 0

        # محاسبه روزهای باقی‌مانده
        days_remaining = None
        if need.deadline:
            days_remaining = max(0, (need.deadline - datetime.utcnow()).days)

        # گرفتن تأییدیه‌های APPROVED
        approved_verifications = []
        if hasattr(need, 'verifications'):
            for v in need.verifications:
                if hasattr(v, 'status') and v.status == "approved":
                    approved_verifications.append(v)

        base_data = {
            "id": need.id,
            "uuid": need.uuid,
            "title": need.title,
            "short_description": need.short_description,
            "category": need.category,
            "target_amount": need.target_amount,
            "collected_amount": need.collected_amount or 0,
            "currency": need.currency,
            "status": need.status,
            "privacy_level": need.privacy_level,
            "is_urgent": need.is_urgent or False,
            "is_emergency": need.is_emergency or False,
            "emergency_type": need.emergency_type,
            "city": need.city,
            "province": need.province,
            "charity_id": need.charity_id,
            "charity_name": need.charity.name if need.charity else None,
            "created_at": need.created_at,
            "progress_percentage": round(progress, 2),
            "days_remaining": days_remaining,
            "verification_count": len(approved_verifications)
        }

        # اگر مجاز به مشاهده جزئیات است
        if can_view_details:
            # آماده‌سازی لیست تأییدیه‌ها
            verifications_list = []
            if hasattr(need, 'verifications'):
                for v in need.verifications:
                    verification_data = {
                        "id": v.id,
                        "charity_id": v.charity_id,
                        "status": v.status,
                        "comment": v.comment,
                        "verified_at": v.verified_at,
                        "created_at": v.created_at
                    }
                    # اضافه کردن نام خیریه اگر وجود دارد
                    if hasattr(v, 'charity') and v.charity:
                        verification_data["charity_name"] = v.charity.name
                    verifications_list.append(verification_data)

            # آماده‌سازی لیست نظرات
            comments_list = []
            if hasattr(need, 'comments'):
                for c in need.comments:
                    comment_data = {
                        "id": c.id,
                        "user_id": c.user_id,
                        "content": c.content,
                        "created_at": c.created_at
                    }
                    # اضافه کردن نام کاربر اگر وجود دارد
                    if hasattr(c, 'user') and c.user:
                        comment_data["username"] = c.user.username
                    comments_list.append(comment_data)

            # اضافه کردن جزئیات کامل
            base_data.update({
                "description": need.description,
                "latitude": need.latitude,
                "longitude": need.longitude,
                "deadline": need.deadline,
                "start_date": need.start_date,
                "end_date": need.end_date,
                "attachments": need.attachments if self._check_attachment_permission(need, user) else [],
                "needy_user_id": need.needy_user_id,
                "created_by_id": need.created_by_id,
                "verifications": verifications_list,
                "comments": comments_list
            })

        return base_data

    async def list_needs(
            self, filters, user: Optional[User] = None, page: int = 1, limit: int = 20
    ) -> Dict[str, Any]:
        """لیست نیازها با فیلتر و صفحه‌بندی"""
        from schemas.need import NeedAdFilter  # Import در اینجا

        query = select(NeedAd).where(NeedAd.status.in_([
            "approved", "active", "completed"
        ]))

        # اعمال فیلترها
        if hasattr(filters, 'category') and filters.category:
            query = query.where(NeedAd.category == filters.category)
        if hasattr(filters, 'city') and filters.city:
            query = query.where(NeedAd.city.ilike(f"%{filters.city}%"))
        if hasattr(filters, 'province') and filters.province:
            query = query.where(NeedAd.province.ilike(f"%{filters.province}%"))
        if hasattr(filters, 'charity_id') and filters.charity_id:
            query = query.where(NeedAd.charity_id == filters.charity_id)
        if hasattr(filters, 'is_urgent') and filters.is_urgent is not None:
            query = query.where(NeedAd.is_urgent == filters.is_urgent)
        if hasattr(filters, 'is_emergency') and filters.is_emergency is not None:
            query = query.where(NeedAd.is_emergency == filters.is_emergency)
        if hasattr(filters, 'min_amount') and filters.min_amount:
            query = query.where(NeedAd.target_amount >= filters.min_amount)
        if hasattr(filters, 'max_amount') and filters.max_amount:
            query = query.where(NeedAd.target_amount <= filters.max_amount)
        if hasattr(filters, 'search_text') and filters.search_text:
            query = query.where(
                or_(
                    NeedAd.title.ilike(f"%{filters.search_text}%"),
                    NeedAd.short_description.ilike(f"%{filters.search_text}%"),
                    NeedAd.description.ilike(f"%{filters.search_text}%")
                )
            )
        if hasattr(filters, 'verified_only') and filters.verified_only:
            # نیازهایی که حداقل یک تأییدیه APPROVED دارند
            subquery = select(NeedVerification.need_id).where(
                NeedVerification.status == "approved"
            ).distinct()
            query = query.where(NeedAd.id.in_(subquery))

        # مرتب‌سازی
        sort_by = getattr(filters, 'sort_by', 'created_at')
        sort_order = getattr(filters, 'sort_order', 'desc')

        sort_column = getattr(NeedAd, sort_by, NeedAd.created_at)
        if sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # صفحه‌بندی
        total_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(total_query)

        offset = (page - 1) * limit
        query = query.offset(offset).limit(limit)

        # اجرای کوئری
        result = await self.db.execute(query)
        needs = result.scalars().all()

        # تبدیل به فرمت خروجی
        need_list = []
        for need in needs:
            # محاسبه پیشرفت
            progress = (need.collected_amount / need.target_amount * 100) if need.target_amount > 0 else 0

            # شمارش تأییدیه‌های APPROVED
            verification_count = 0
            if hasattr(need, 'verifications'):
                verification_count = len([v for v in need.verifications
                                          if hasattr(v, 'status') and v.status == "approved"])

            need_list.append({
                "id": need.id,
                "uuid": need.uuid,
                "title": need.title,
                "short_description": need.short_description,
                "category": need.category,
                "target_amount": need.target_amount,
                "collected_amount": need.collected_amount or 0,
                "currency": need.currency,
                "status": need.status,
                "is_urgent": need.is_urgent or False,
                "is_emergency": need.is_emergency or False,
                "city": need.city,
                "province": need.province,
                "charity_id": need.charity_id,
                "charity_name": need.charity.name if need.charity else None,
                "created_at": need.created_at,
                "progress_percentage": round(progress, 2),
                "verification_count": verification_count
            })

        return {
            "items": need_list,
            "total": total or 0,
            "page": page,
            "limit": limit,
            "total_pages": math.ceil(total / limit) if total and total > 0 else 0
        }

    async def add_verification(
            self, need_id: int, charity_id: int, user: User, comment: Optional[str] = None
    ) -> NeedVerification:
        """اضافه کردن تأییدیه به نیاز"""
        need = await self._get_need(need_id)

        # بررسی اینکه آیا خیریه مجاز به تأیید است
        charity = await self.db.get(Charity, charity_id)
        if not charity:
            raise HTTPException(status_code=404, detail="Charity not found")

        # بررسی اینکه کاربر مدیر این خیریه است یا ادمین
        user_roles = [r.key for r in user.roles]
        if charity.manager_id != user.id and "ADMIN" not in user_roles:
            raise HTTPException(status_code=403, detail="Not authorized to verify")

        # بررسی تأییدیه تکراری
        existing = await self.db.execute(
            select(NeedVerification).where(
                and_(
                    NeedVerification.need_id == need_id,
                    NeedVerification.charity_id == charity_id
                )
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Already verified by this charity")

        # ایجاد تأییدیه
        verification = NeedVerification(
            need_id=need_id,
            charity_id=charity_id,
            status="pending",  # استفاده از string literal
            comment=comment
        )

        self.db.add(verification)
        await self.db.commit()
        await self.db.refresh(verification)
        return verification

    async def update_verification_status(
            self, verification_id: int, status: str, user: User, comment: Optional[str] = None
    ) -> NeedVerification:
        verification = await self.db.get(NeedVerification, verification_id)
        if not verification:
            raise HTTPException(status_code=404, detail="Verification not found")

        # ... مجوزها (فعلی)

        verification.status = status
        verification.comment = comment
        if status == "approved":
            verification.verified_at = datetime.utcnow()

        # ──────────────────────────────── اضافه کردن این بلوک ────────────────────────────────
        need = verification.need

        # شمارش تأییدیه‌های approved
        approved_count = sum(1 for v in need.verifications if v.status == "approved")

        # اگر حداقل ۱ تأیید شد و هنوز pending است → منتشر کن
        if approved_count >= 1 and need.status == "pending":
            need.status = "approved"  # یا "active" بسته به منطق پروژه
            need.verified_at = datetime.utcnow()
            need.verified_by = user.id  # اختیاری

            # اختیاری: محاسبه اولیه trust_score
            need.trust_score = await self._calculate_trust_score(need.id)

            # نوتیفیکیشن به نیازمند (بعداً پیاده‌سازی شود)
            # await send_notification(need.needy_user, "نیاز شما تأیید و منتشر شد")

        # ───────────────────────────────────────────────────────────────────────────────────────

        await self.db.commit()
        await self.db.refresh(verification)
        await self.db.refresh(need)  # مهم!
        return verification

    # ---------- Helper Methods ----------
    async def _get_need(self, need_id: int) -> NeedAd:
        """دریافت نیاز با بررسی وجود"""
        result = await self.db.execute(
            select(NeedAd).where(NeedAd.id == need_id)
        )
        need = result.scalar_one_or_none()
        if not need:
            raise HTTPException(status_code=404, detail="Need not found")
        return need

    async def _get_need_with_permission(
            self, need_id: int, user: User, require_admin: bool = False
    ) -> NeedAd:
        """دریافت نیاز با بررسی مجوز"""
        need = await self._get_need(need_id)
        user_roles = [r.key for r in user.roles]

        if require_admin:
            if "ADMIN" not in user_roles and \
                    "CHARITY_MANAGER" not in user_roles and \
                    need.charity.manager_id != user.id:
                raise HTTPException(status_code=403, detail="Not authorized")
        else:
            # بررسی مالکیت یا دسترسی مدیر
            if need.created_by_id != user.id and \
                    need.charity.manager_id != user.id and \
                    "ADMIN" not in user_roles and \
                    "CHARITY_MANAGER" not in user_roles:
                raise HTTPException(status_code=403, detail="Not authorized")

        return need

    def _check_view_permission(self, need: NeedAd, user: Optional[User]) -> bool:
        """بررسی مجوز مشاهده جزئیات"""
        if not user:
            return need.privacy_level == "public"

        user_roles = [r.key for r in user.roles]

        # ادمین/مدیر همیشه دسترسی دارد
        if "ADMIN" in user_roles or "CHARITY_MANAGER" in user_roles:
            return True

        # مدیر خیریه مربوطه
        if need.charity and need.charity.manager_id == user.id:
            return True

        # کاربر ایجادکننده
        if need.created_by_id == user.id:
            return True

        # نیازمند مربوطه
        if need.needy_user_id == user.id:
            return True

        # بررسی سطح حریم خصوصی
        if need.privacy_level == "public":
            return True
        elif need.privacy_level == "protected":
            # کاربران ثبت‌نام‌شده
            return user.is_active
        else:  # private
            return False

    def _check_attachment_permission(self, need: NeedAd, user: Optional[User]) -> bool:
        """بررسی مجوز مشاهده فایل‌های ضمیمه"""
        if not user:
            return False

        user_roles = [r.key for r in user.roles]

        # فقط کاربران خاص مجازند
        allowed_roles = {"ADMIN", "CHARITY_MANAGER", "CHARITY", "DONOR"}
        if not any(role in allowed_roles for role in user_roles):
            return False

        # کاربر باید تأیید شده باشد
        return user.is_verified


# ========== متدهای جدید برای تکمیل ویژگی‌های داکیومنت ==========

async def create_need_with_wizard(self, wizard_data: Dict[str, Any], user: User) -> NeedAd:
    """ایجاد نیاز با استفاده از Wizard 5 مرحله‌ای"""
    # ترکیب داده‌های مراحل مختلف
    need_data = {
        **wizard_data["basic_info"],
        **wizard_data["financial_info"],
        **wizard_data["location_info"],
        **wizard_data["details"],
    }

    # اضافه کردن تنظیمات پیشرفت بصری
    need_data["progress_display_settings"] = {
        "show_percentage": wizard_data["details"].get("show_percentage", True),
        "show_collected": wizard_data["details"].get("show_collected", True),
        "show_remaining": wizard_data["details"].get("show_remaining", True),
        "progress_bar_style": wizard_data["details"].get("progress_bar_style", "circular"),
    }

    # ایجاد نیاز
    need = await self.create_need(need_data, user, wizard_data["charity_id"])

    # اگر بحران است
    if need_data.get("is_emergency") and wizard_data.get("emergency_info"):
        emergency_service = NeedEmergencyService(self.db)
        await emergency_service.create_emergency_need(
            need=need,
            emergency_data=wizard_data["emergency_info"],
            user=user
        )

    return need


async def update_need_progress(
        self,
        need_id: int,
        collected_amount: float,
        user: User,
        notes: Optional[str] = None
) -> NeedAd:
    """به‌روزرسانی دستی پیشرفت پرداخت توسط مدیر/ادمین"""

    need = await self._get_need_with_permission(need_id, user, require_admin=True)

    old_amount = need.collected_amount or 0
    need.collected_amount = collected_amount

    # اگر به هدف رسید
    if need.collected_amount >= need.target_amount:
        need.status = "completed"

    # ثبت تاریخچه به‌روزرسانی
    if not hasattr(need, 'progress_history'):
        need.progress_history = []

    need.progress_history.append({
        "updated_at": datetime.utcnow().isoformat(),
        "updated_by": user.id,
        "old_amount": old_amount,
        "new_amount": collected_amount,
        "notes": notes
    })

    self.db.add(need)
    await self.db.commit()
    await self.db.refresh(need)

    return need


async def link_product_to_need(
        self,
        need_id: int,
        product_id: int,
        user: User,
        donation_amount: Optional[float] = None,
        charity_percentage: Optional[float] = None
) -> NeedAd:
    """لینک کردن محصول فروشگاهی به نیاز خاص"""

    need = await self._get_need_with_permission(need_id, user, require_admin=True)

    # بررسی محصول
    from models.product import Product
    product = await self.db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # اضافه کردن به لیست محصولات لینک شده
    if not need.linked_product_ids:
        need.linked_product_ids = []

    if product_id not in need.linked_product_ids:
        need.linked_product_ids.append(product_id)

    # ذخیره در جدول association
    from models.association_tables import product_need_association
    stmt = product_need_association.insert().values(
        product_id=product_id,
        need_id=need_id,
        donation_amount=donation_amount,
        charity_percentage=charity_percentage or product.charity_percentage,
        created_at=datetime.utcnow()
    )
    await self.db.execute(stmt)

    self.db.add(need)
    await self.db.commit()
    await self.db.refresh(need)

    return need


async def get_need_with_verified_badges(self, need_id: int, user: Optional[User] = None) -> Dict[str, Any]:
    """دریافت نیاز با نشان‌های تأیید و امتیاز اعتماد"""

    need_data = await self.get_need(need_id, user)

    # محاسبه امتیاز اعتماد
    trust_score = await self._calculate_trust_score(need_id)
    need_data["trust_score"] = trust_score

    # تعیین سطح نشان اعتماد
    if trust_score >= 80:
        need_data["badge_level"] = "platinum"
        need_data["verified_badge"] = True
    elif trust_score >= 60:
        need_data["badge_level"] = "gold"
        need_data["verified_badge"] = True
    elif trust_score >= 40:
        need_data["badge_level"] = "silver"
        need_data["verified_badge"] = True
    elif trust_score >= 20:
        need_data["badge_level"] = "bronze"
        need_data["verified_badge"] = True
    else:
        need_data["badge_level"] = None
        need_data["verified_badge"] = False

    # دریافت لیست تأییدکنندگان با نشان
    need_data["verified_by_list"] = await self._get_verified_by_list(need_id)

    return need_data


async def get_visual_progress_data(self, need_id: int) -> Dict[str, Any]:
    """دریافت داده‌های پیشرفت بصری (برای Progress Bar دایره‌ای)"""

    need = await self._get_need(need_id)

    collected = need.collected_amount or 0
    target = need.target_amount
    percentage = (collected / target * 100) if target > 0 else 0
    remaining = max(0, target - collected)

    # تنظیمات نمایش
    settings = need.progress_display_settings or {
        "show_percentage": True,
        "show_collected": True,
        "show_remaining": True,
        "progress_bar_style": "circular",
        "progress_bar_color": "primary"
    }

    return {
        "need_id": need_id,
        "target_amount": target,
        "collected_amount": collected,
        "remaining_amount": remaining,
        "percentage": round(percentage, 2),
        "display_settings": settings,
        # برای Progress Bar دایره‌ای
        "circular_progress": {
            "percentage": round(percentage, 2),
            "stroke_width": 8,
            "size": 120,
            "color": self._get_progress_color(percentage)
        },
        # برای نمایش فارسی
        "formatted": {
            "collected": f"{collected:,.0f}",
            "target": f"{target:,.0f}",
            "remaining": f"{remaining:,.0f}",
            "percentage": f"{percentage:.1f}%"
        }
    }


async def add_campaign_settings(
        self,
        need_id: int,
        campaign_data: Dict[str, Any],
        user: User
) -> NeedAd:
    """اضافه کردن تنظیمات کمپین زمان‌دار به نیاز"""

    need = await self._get_need_with_permission(need_id, user, require_admin=True)

    need.campaign_settings = {
        "is_campaign": True,
        "campaign_start": campaign_data.get("campaign_start", datetime.utcnow()),
        "campaign_end": campaign_data.get("campaign_end"),
        "campaign_goal": campaign_data.get("campaign_goal", need.target_amount),
        "campaign_type": campaign_data.get("campaign_type", "normal"),
        "matching_donor": campaign_data.get("matching_donor"),
        "matching_ratio": campaign_data.get("matching_ratio", 0),
        "badge_text": campaign_data.get("badge_text", "🚀 کمپین ویژه"),
        "collected_in_campaign": 0,
        "donors_count": 0
    }

    self.db.add(need)
    await self.db.commit()
    await self.db.refresh(need)

    return need


async def increment_social_share(self, need_id: int, platform: str, user_id: int | None = None,
                                 db: AsyncSession | None = None):
    """ثبت یک اشتراک جدید برای نیاز"""
    if db is None:
        db = self.db

    share = NeedSocialShare(
        need_id=need_id,
        platform=platform,
        user_id=user_id
    )
    db.add(share)
    await db.commit()

    # شمارش کل اشتراک‌ها برای این نیاز و پلتفرم
    count_query = select(func.count()).where(
        NeedSocialShare.need_id == need_id,
        NeedSocialShare.platform == platform
    )
    total = await db.scalar(count_query)
    return {"platform": platform, "share_count": total}


async def get_social_shares(self, need_id: int, db: AsyncSession | None = None):
    """گرفتن آمار اشتراک به تفکیک پلتفرم"""
    if db is None:
        db = self.db

    query = select(
        NeedSocialShare.platform,
        func.count().label("count")
    ).where(
        NeedSocialShare.need_id == need_id
    ).group_by(NeedSocialShare.platform)

    result = await db.execute(query)
    rows = result.all()

    stats = {row.platform: row.count for row in rows}
    return stats


async def get_need_statistics(self, need_id: int) -> Dict[str, Any]:
    """دریافت آمار کامل یک نیاز"""

    need = await self._get_need(need_id)

    from models.donation import Donation
    from sqlalchemy import func

    # آمار کمک‌ها
    donations_query = select(
        func.count(Donation.id).label("total_donations"),
        func.coalesce(func.sum(Donation.amount), 0).label("total_amount"),
        func.avg(Donation.amount).label("average_amount"),
        func.max(Donation.amount).label("max_amount"),
        func.min(Donation.amount).label("min_amount"),
        func.count(func.distinct(Donation.donor_id)).label("unique_donors")
    ).where(
        and_(
            Donation.need_id == need_id,
            Donation.status == "completed"
        )
    )

    result = await self.db.execute(donations_query)
    stats = result.first()

    # آمار روزانه
    daily_query = select(
        func.date(Donation.created_at).label("date"),
        func.count(Donation.id).label("count"),
        func.sum(Donation.amount).label("amount")
    ).where(
        and_(
            Donation.need_id == need_id,
            Donation.status == "completed"
        )
    ).group_by(func.date(Donation.created_at))

    daily_result = await self.db.execute(daily_query)
    daily_stats = [
        {
            "date": row.date,
            "donations_count": row.count,
            "amount": float(row.amount or 0)
        }
        for row in daily_result.all()
    ]

    return {
        "need_id": need_id,
        "donations_summary": {
            "total_donations": stats.total_donations or 0,
            "total_amount": float(stats.total_amount or 0),
            "average_donation": float(stats.average_amount or 0),
            "largest_donation": float(stats.max_amount or 0),
            "smallest_donation": float(stats.min_amount or 0),
            "unique_donors": stats.unique_donors or 0
        },
        "daily_stats": daily_stats,
        "verification_count": len([v for v in need.verifications if v.status == "approved"]),
        "comment_count": len(need.comments) if hasattr(need, 'comments') else 0,
        "progress_history": getattr(need, 'progress_history', [])
    }


# ========== متدهای کمکی جدید ==========

async def _calculate_trust_score(self, need_id: int) -> float:
    """محاسبه امتیاز اعتماد برای نیاز"""

    need = await self._get_need(need_id)
    score = 0.0

    # 1. تأییدیه‌های خیریه (40 امتیاز)
    approved_verifications = len([v for v in need.verifications if v.status == "approved"])
    score += min(approved_verifications * 10, 40)  # هر تأییدیه 10 امتیاز

    # 2. درصد تکمیل (30 امتیاز)
    if need.target_amount > 0:
        progress = (need.collected_amount or 0) / need.target_amount
        score += progress * 30

    # 3. زمان باقی‌مانده (10 امتیاز)
    if need.deadline:
        days_left = (need.deadline - datetime.utcnow()).days
        if days_left > 30:
            score += 10
        elif days_left > 14:
            score += 7
        elif days_left > 7:
            score += 5
        elif days_left > 3:
            score += 3
        elif days_left > 0:
            score += 1

    # 4. خیریه تأیید شده (20 امتیاز)
    if need.charity and need.charity.verified:
        score += 20

    return round(score, 2)


async def _get_verified_by_list(self, need_id: int) -> List[Dict[str, Any]]:
    """دریافت لیست تأییدکنندگان با نشان"""

    need = await self._get_need(need_id)
    verified_list = []

    for v in need.verifications:
        if v.status == "approved":
            verified_list.append({
                "charity_id": v.charity_id,
                "charity_name": v.charity.name if v.charity else None,
                "charity_logo": v.charity.logo_url if v.charity else None,
                "verified_at": v.verified_at,
                "badge_url": f"/static/badges/verified-charity.png",
                "comment": v.comment
            })

    return verified_list


def _get_progress_color(self, percentage: float) -> str:
    """تعیین رنگ Progress Bar بر اساس درصد"""
    if percentage >= 80:
        return "#4CAF50"  # سبز
    elif percentage >= 50:
        return "#2196F3"  # آبی
    elif percentage >= 25:
        return "#FF9800"  # نارنجی
    else:
        return "#F44336"  # قرمز