# app/api/v1/endpoints/need_ad.py
import math

from fastapi import APIRouter, Depends, HTTPException, Query, status, Body, UploadFile, Form, File
from requests import request
from sqlalchemy import func, select, case
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any
from datetime import datetime

from core.database import get_db
from core.permissions import get_current_user, require_roles
from models import NeedAd
from models.user import User
from models.charity import Charity
from services.need_service import NeedService
from schemas.need import (
    NeedAdCreate, NeedAdUpdate, NeedAdStatusUpdate, NeedAdRead, NeedAdDetail,
    NeedAdFilter, WizardPreview, NeedCategory, NeedStatus,
    Step1BasicInfo, Step2FinancialInfo, Step3LocationInfo,
    Step4Details, Step5Attachments
)

router = APIRouter()


# --------------------------
# 1️⃣ Wizard ثبت نیاز (مرحله به مرحله)
# --------------------------

@router.post("/wizard/preview", response_model=WizardPreview)
async def preview_need_wizard(
        step1: Step1BasicInfo = Body(...),
        step2: Step2FinancialInfo = Body(...),
        step3: Step3LocationInfo = Body(...),
        step4: Step4Details = Body(...),
        step5: Step5Attachments = Body(...),
        charity_id: int = Body(...),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """پیش‌نمایش نهایی قبل از ثبت نیاز"""
    # بررسی وجود خیریه
    charity = await db.get(Charity, charity_id)
    if not charity:
        raise HTTPException(status_code=404, detail="Charity not found")

    # بررسی مجوز کاربر برای این خیریه
    user_roles = [r.key for r in current_user.roles]
    if "ADMIN" not in user_roles and \
            "CHARITY_MANAGER" not in user_roles and \
            charity.manager_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this charity")

    return WizardPreview(
        basic_info=step1,
        financial_info=step2,
        location_info=step3,
        details=step4,
        attachments=step5,
        charity_id=charity_id
    )


@router.post("/wizard/submit", response_model=NeedAdDetail)
async def submit_need_wizard(
        step1: Step1BasicInfo = Body(...),
        step2: Step2FinancialInfo = Body(...),
        step3: Step3LocationInfo = Body(...),
        step4: Step4Details = Body(...),
        step5: Step5Attachments = Body(...),
        charity_id: int = Body(...),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """ثبت نهایی نیاز از طریق Wizard"""
    service = NeedService(db)

    # ترکیب داده‌های Wizard
    need_data = NeedAdCreate(
        title=step1.title,
        short_description=step1.short_description,
        description=step4.description,
        category=step1.category,
        target_amount=step2.target_amount,
        currency=step2.currency,
        city=step3.city,
        province=step3.province,
        privacy_level=step4.privacy_level,
        is_urgent=step1.is_urgent,
        is_emergency=step1.is_emergency,
        emergency_type=step1.emergency_type,
        latitude=step3.latitude,
        longitude=step3.longitude,
        deadline=step2.deadline,
        start_date=step4.start_date,
        end_date=step4.end_date,
        attachments=step5.attachments,
        charity_id=charity_id
    )

    need = await service.create_need(need_data, current_user, charity_id)
    return await service.get_need(need.id, current_user)


# --------------------------
# 2️⃣ CRUD اصلی نیازها
# --------------------------

@router.post("/", response_model=NeedAdDetail)
async def create_need(
        need_data: NeedAdCreate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """ایجاد نیاز جدید (روش مستقیم)"""
    service = NeedService(db)
    need = await service.create_need(need_data, current_user, need_data.charity_id)
    return await service.get_need(need.id, current_user)


@router.get("/", response_model=Dict[str, Any])
async def list_needs(
        category: Optional[NeedCategory] = Query(None),
        city: Optional[str] = Query(None),
        province: Optional[str] = Query(None),
        charity_id: Optional[int] = Query(None),
        is_urgent: Optional[bool] = Query(None),
        is_emergency: Optional[bool] = Query(None),
        min_amount: Optional[float] = Query(None),
        max_amount: Optional[float] = Query(None),
        verified_only: bool = Query(False),
        search_text: Optional[str] = Query(None),
        sort_by: str = Query("created_at", description="Field to sort by"),
        sort_order: str = Query("desc", description="Sort order: asc or desc"),
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """لیست نیازها با فیلتر و صفحه‌بندی"""
    filters = NeedAdFilter(
        category=category,
        city=city,
        province=province,
        charity_id=charity_id,
        is_urgent=is_urgent,
        is_emergency=is_emergency,
        min_amount=min_amount,
        max_amount=max_amount,
        verified_only=verified_only,
        search_text=search_text,
        sort_by=sort_by,
        sort_order=sort_order
    )

    service = NeedService(db)
    return await service.list_needs(filters, current_user, page, limit)


@router.get("/{need_id}", response_model=NeedAdDetail)
async def get_need(
        need_id: int,
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """دریافت جزئیات یک نیاز"""
    service = NeedService(db)
    return await service.get_need(need_id, current_user)


@router.put("/{need_id}", response_model=NeedAdDetail)
async def update_need(
        need_id: int,
        need_data: NeedAdUpdate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """ویرایش نیاز"""
    service = NeedService(db)
    need = await service.update_need(need_id, need_data, current_user)
    return await service.get_need(need.id, current_user)


@router.delete("/{need_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_need(
        need_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """حذف نیاز (فقط در حالت DRAFT یا توسط ادمین)"""
    service = NeedService(db)
    need = await service._get_need_with_permission(need_id, current_user)

    # فقط در حالت DRAFT یا توسط ادمین می‌توان حذف کرد
    user_roles = [r.key for r in current_user.roles]
    if need.status != "draft" and "ADMIN" not in user_roles:
        raise HTTPException(
            status_code=400,
            detail="Can only delete needs in draft status"
        )

    await db.delete(need)
    await db.commit()
    return None


# --------------------------
# 3️⃣ مدیریت وضعیت نیازها
# --------------------------

@router.patch("/{need_id}/status", response_model=NeedAdDetail)
async def update_need_status(
        need_id: int,
        status_data: NeedAdStatusUpdate,
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER")),
        db: AsyncSession = Depends(get_db)
):
    """تغییر وضعیت نیاز (فقط مدیر/ادمین)"""
    service = NeedService(db)
    need = await service.update_need_status(need_id, status_data, current_user)
    return await service.get_need(need.id, current_user)


@router.post("/{need_id}/submit-for-approval", response_model=NeedAdDetail)
async def submit_for_approval(
        need_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """ارسال نیاز برای تأیید"""
    service = NeedService(db)
    need = await service._get_need_with_permission(need_id, current_user)

    if need.status != "draft":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot submit need in {need.status} status"
        )

    need.status = "pending"
    db.add(need)
    await db.commit()
    await db.refresh(need)

    # TODO: ارسال نوتیفیکیشن به مدیران خیریه

    return await service.get_need(need.id, current_user)


# --------------------------
# 4️⃣ سیستم تأییدیه‌ها
# --------------------------

@router.post("/{need_id}/verifications")
async def add_verification(
        need_id: int,
        charity_id: int = Body(...),
        comment: Optional[str] = Body(None),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """اضافه کردن تأییدیه به نیاز"""
    service = NeedService(db)
    verification = await service.add_verification(need_id, charity_id, current_user, comment)

    return {
        "id": verification.id,
        "need_id": verification.need_id,
        "charity_id": verification.charity_id,
        "status": verification.status,
        "comment": verification.comment,
        "created_at": verification.created_at
    }


@router.get("/{need_id}/verifications")
async def list_need_verifications(
        need_id: int,
        status: Optional[str] = Query(None),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """لیست تأییدیه‌های یک نیاز"""
    service = NeedService(db)
    need = await service._get_need(need_id)

    # بررسی دسترسی
    if not service._check_view_permission(need, current_user):
        raise HTTPException(status_code=403, detail="Not authorized")

    verifications = []
    for v in need.verifications:
        if status and v.status != status:
            continue

        verification_data = {
            "id": v.id,
            "charity_id": v.charity_id,
            "charity_name": v.charity.name if v.charity else None,
            "status": v.status,
            "comment": v.comment,
            "verified_at": v.verified_at,
            "created_at": v.created_at
        }
        verifications.append(verification_data)

    return {"verifications": verifications}


@router.patch("/verifications/{verification_id}")
async def update_verification_status(
        verification_id: int,
        status: str = Body(..., embed=True),
        comment: Optional[str] = Body(None),
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER")),
        db: AsyncSession = Depends(get_db)
):
    """تغییر وضعیت تأییدیه"""
    service = NeedService(db)
    verification = await service.update_verification_status(
        verification_id, status, current_user, comment
    )

    return {
        "id": verification.id,
        "need_id": verification.need_id,
        "charity_id": verification.charity_id,
        "status": verification.status,
        "comment": verification.comment,
        "verified_at": verification.verified_at,
        "created_at": verification.created_at
    }


# --------------------------
# 5️⃣ سیستم نظرات
# --------------------------

@router.post("/{need_id}/comments")
async def add_comment(
        need_id: int,
        content: str = Body(..., embed=True, min_length=1, max_length=1000),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """اضافه کردن نظر به نیاز"""
    from models.need_comment import NeedComment

    service = NeedService(db)
    need = await service._get_need(need_id)

    # بررسی دسترسی
    if not service._check_view_permission(need, current_user):
        raise HTTPException(status_code=403, detail="Not authorized")

    # ایجاد نظر
    comment = NeedComment(
        need_id=need_id,
        user_id=current_user.id,
        content=content
    )

    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    return {
        "id": comment.id,
        "user_id": comment.user_id,
        "username": current_user.username,
        "content": comment.content,
        "created_at": comment.created_at
    }


@router.get("/{need_id}/comments")
async def list_need_comments(
        need_id: int,
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """لیست نظرات یک نیاز"""
    from sqlalchemy import select
    from models.need_comment import NeedComment

    service = NeedService(db)
    need = await service._get_need(need_id)

    # بررسی دسترسی
    if not service._check_view_permission(need, current_user):
        raise HTTPException(status_code=403, detail="Not authorized")

    # کوئری اصلی
    query = select(NeedComment).where(NeedComment.need_id == need_id)

    # شمارش کل
    total_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(total_query)

    # صفحه‌بندی
    offset = (page - 1) * limit
    query = query.order_by(NeedComment.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    comments = result.scalars().all()

    # تبدیل به فرمت خروجی
    comments_list = []
    for comment in comments:
        comment_data = {
            "id": comment.id,
            "user_id": comment.user_id,
            "content": comment.content,
            "created_at": comment.created_at
        }

        # اضافه کردن نام کاربر
        if comment.user:
            comment_data["username"] = comment.user.username
            comment_data["avatar_url"] = comment.user.avatar_url

        comments_list.append(comment_data)

    return {
        "items": comments_list,
        "total": total or 0,
        "page": page,
        "limit": limit,
        "total_pages": math.ceil(total / limit) if total and total > 0 else 0
    }


# --------------------------
# 6️⃣ مدیریت پیوست‌ها
# --------------------------

@router.post("/{need_id}/attachments")
async def add_attachment(
        need_id: int,
        attachment_data: Dict[str, Any] = Body(...),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """اضافه کردن فایل پیوست به نیاز"""
    service = NeedService(db)
    need = await service._get_need_with_permission(need_id, current_user)

    # فقط در حالت‌های خاص اجازه اضافه کردن فایل داریم
    if need.status not in ["draft", "pending", "rejected"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot add attachments to need in {need.status} status"
        )

    # اضافه کردن فایل به لیست attachments
    current_attachments = need.attachments or []
    attachment_data.update({
        "uploaded_by": current_user.id,
        "uploaded_at": datetime.utcnow().isoformat()
    })
    current_attachments.append(attachment_data)
    need.attachments = current_attachments

    db.add(need)
    await db.commit()
    await db.refresh(need)

    return {"attachments": need.attachments}


@router.delete("/{need_id}/attachments/{attachment_index}")
async def delete_attachment(
        need_id: int,
        attachment_index: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """حذف فایل پیوست از نیاز"""
    service = NeedService(db)
    need = await service._get_need_with_permission(need_id, current_user)

    # فقط در حالت‌های خاص اجازه حذف فایل داریم
    if need.status not in ["draft", "pending", "rejected"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete attachments from need in {need.status} status"
        )

    # بررسی index
    if not need.attachments or attachment_index >= len(need.attachments):
        raise HTTPException(status_code=404, detail="Attachment not found")

    # حذف فایل
    need.attachments.pop(attachment_index)

    db.add(need)
    await db.commit()

    return {"message": "Attachment deleted successfully"}


# --------------------------
# 7️⃣ نیازهای من (بر اساس کاربر)
# --------------------------

@router.get("/user/needs", response_model=Dict[str, Any])
async def get_user_needs(
        status: Optional[NeedStatus] = Query(None),
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """دریافت نیازهای ایجاد شده توسط کاربر"""
    from sqlalchemy import select

    # ساخت کوئری
    query = select(NeedAd).where(NeedAd.created_by_id == current_user.id)

    if status:
        query = query.where(NeedAd.status == status)

    # شمارش کل
    total_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(total_query)

    # صفحه‌بندی
    offset = (page - 1) * limit
    query = query.order_by(NeedAd.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    needs = result.scalars().all()

    # تبدیل به فرمت خروجی
    service = NeedService(db)
    need_list = []
    for need in needs:
        need_data = await service.get_need(need.id, current_user)
        need_list.append(need_data)

    return {
        "items": need_list,
        "total": total or 0,
        "page": page,
        "limit": limit,
        "total_pages": math.ceil(total / limit) if total and total > 0 else 0
    }


@router.get("/user/needy-needs", response_model=Dict[str, Any])
async def get_needy_needs(
        status: Optional[NeedStatus] = Query(None),
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """دریافت نیازهای مربوط به یک نیازمند"""
    from sqlalchemy import select

    # فقط کاربران NEEDY
    user_roles = [r.key for r in current_user.roles]
    if "NEEDY" not in user_roles:
        raise HTTPException(status_code=403, detail="Only needy users can access this endpoint")

    # ساخت کوئری
    query = select(NeedAd).where(NeedAd.needy_user_id == current_user.id)

    if status:
        query = query.where(NeedAd.status == status)

    # شمارش کل
    total_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(total_query)

    # صفحه‌بندی
    offset = (page - 1) * limit
    query = query.order_by(NeedAd.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    needs = result.scalars().all()

    # تبدیل به فرمت خروجی
    service = NeedService(db)
    need_list = []
    for need in needs:
        need_data = await service.get_need(need.id, current_user)
        need_list.append(need_data)

    return {
        "items": need_list,
        "total": total or 0,
        "page": page,
        "limit": limit,
        "total_pages": math.ceil(total / limit) if total and total > 0 else 0
    }


# --------------------------
# 8️⃣ آمار و گزارش‌ها
# --------------------------

@router.get("/{need_id}/stats")
async def get_need_stats(
        need_id: int,
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """دریافت آمار یک نیاز"""
    from sqlalchemy import select, func
    from models.donation import Donation

    service = NeedService(db)
    need = await service._get_need(need_id)

    # بررسی دسترسی
    if not service._check_view_permission(need, current_user):
        raise HTTPException(status_code=403, detail="Not authorized")

    # محاسبه آمار کمک‌ها
    donations_query = select(
        func.count(Donation.id).label("total_donations"),
        func.sum(Donation.amount).label("total_donated"),
        func.avg(Donation.amount).label("average_donation")
    ).where(
        Donation.need_id == need_id,
        Donation.status == "completed"
    )

    result = await db.execute(donations_query)
    stats = result.first()

    # محاسبه روزهای باقی‌مانده
    days_remaining = None
    if need.deadline:
        days_remaining = max(0, (need.deadline - datetime.utcnow()).days)

    # محاسبه درصد پیشرفت
    progress = (need.collected_amount / need.target_amount * 100) if need.target_amount > 0 else 0

    return {
        "need_id": need_id,
        "title": need.title,
        "target_amount": need.target_amount,
        "collected_amount": need.collected_amount or 0,
        "progress_percentage": round(progress, 2),
        "days_remaining": days_remaining,
        "total_donations": stats.total_donations or 0,
        "total_donated": float(stats.total_donated or 0),
        "average_donation": float(stats.average_donation or 0),
        "verification_count": len([v for v in need.verifications if v.status == "approved"]),
        "comment_count": len(need.comments),
        "created_at": need.created_at,
        "last_donation_at": None,  # TODO: محاسبه شود
        "urgency_level": "high" if need.is_urgent or need.is_emergency else "normal"
    }


# --------------------------
# 9️⃣ جستجوی پیشرفته
# --------------------------

@router.get("/search/suggestions")
async def search_suggestions(
        q: str = Query(..., min_length=1),
        limit: int = Query(10, ge=1, le=50),
        db: AsyncSession = Depends(get_db)
):
    """پیشنهادات جستجو"""
    from sqlalchemy import select, distinct

    # جستجو در عنوان
    title_query = select(
        NeedAd.title.label("text"),
        func.literal("title").label("type")
    ).where(
        NeedAd.title.ilike(f"%{q}%"),
        NeedAd.status.in_(["approved", "active", "completed"])
    ).limit(limit)

    # جستجو در شهر
    city_query = select(
        NeedAd.city.label("text"),
        func.literal("city").label("type")
    ).where(
        NeedAd.city.ilike(f"%{q}%"),
        NeedAd.status.in_(["approved", "active", "completed"])
    ).distinct().limit(limit)

    # جستجو در دسته‌بندی
    category_query = select(
        NeedAd.category.label("text"),
        func.literal("category").label("type")
    ).where(
        NeedAd.category.ilike(f"%{q}%"),
        NeedAd.status.in_(["approved", "active", "completed"])
    ).distinct().limit(limit)

    # اجرای کوئری‌ها
    result1 = await db.execute(title_query)
    result2 = await db.execute(city_query)
    result3 = await db.execute(category_query)

    suggestions = []
    suggestions.extend([dict(row) for row in result1.all()])
    suggestions.extend([dict(row) for row in result2.all()])
    suggestions.extend([dict(row) for row in result3.all()])

    return {"suggestions": suggestions[:limit]}

@router.post("/{need_id}/attachments")
async def add_need_attachment(
    need_id: int,
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    from services.need_service import NeedService
    service = NeedService(db)
    return await service.add_attachment_to_need(need_id, file, current_user, description)


@router.get("/stats", response_model=Dict[str, Any])
async def get_needs_stats(
        db: AsyncSession = Depends(get_db),
        current_user: Optional[User] = Depends(get_current_user)
):
    """
    آمار کلی آگهی‌ها (تعداد کل، فوری، تکمیل شده، در حال کمک، تأییدیه‌ها)
    استفاده در صفحه اصلی و داشبوردها
    """
    service = NeedService(db)

    # آمار کلی
    total_query = select(func.count()).select_from(NeedAd)
    total = await db.scalar(total_query)

    # آگهی‌های فعال (approved, active)
    active_query = select(func.count()).select_from(NeedAd).where(
        NeedAd.status.in_(["approved", "active"])
    )
    active = await db.scalar(active_query)

    # آگهی‌های تکمیل شده
    completed_query = select(func.count()).select_from(NeedAd).where(
        NeedAd.status == "completed"
    )
    completed = await db.scalar(completed_query)

    # آگهی‌های فوری
    urgent_query = select(func.count()).select_from(NeedAd).where(
        NeedAd.is_urgent == True
    )
    urgent = await db.scalar(urgent_query)

    # آگهی‌های اضطراری (بحران)
    emergency_query = select(func.count()).select_from(NeedAd).where(
        NeedAd.is_emergency == True
    )
    emergency = await db.scalar(emergency_query)

    # مجموع مبلغ کمک‌های جمع‌آوری شده
    total_collected_query = select(func.coalesce(func.sum(NeedAd.collected_amount), 0)).where(
        NeedAd.status.in_(["active", "completed"])
    )
    total_collected = await db.scalar(total_collected_query)

    # مجموع مبلغ هدف
    total_target_query = select(func.coalesce(func.sum(NeedAd.target_amount), 0)).where(
        NeedAd.status.in_(["approved", "active"])
    )
    total_target = await db.scalar(total_target_query)

    # آگهی‌های دارای تأییدیه
    from models.need_verification import NeedVerification
    verified_needs_subquery = select(NeedVerification.need_id).where(
        NeedVerification.status == "approved"
    ).distinct()
    verified_query = select(func.count()).select_from(
        select(NeedAd.id).where(
            NeedAd.id.in_(verified_needs_subquery),
            NeedAd.status.in_(["approved", "active"])
        ).subquery()
    )
    verified = await db.scalar(verified_query)

    # میانگین پیشرفت
    avg_progress_query = select(
        func.avg(
            func.coalesce(NeedAd.collected_amount, 0) /
            func.nullif(NeedAd.target_amount, 0) * 100
        )
    ).where(NeedAd.status.in_(["approved", "active"]))
    avg_progress = await db.scalar(avg_progress_query) or 0

    return {
        "total_needs": total or 0,
        "active_needs": active or 0,
        "completed_needs": completed or 0,
        "urgent_needs": urgent or 0,
        "emergency_needs": emergency or 0,
        "verified_needs": verified or 0,
        "total_collected_amount": float(total_collected or 0),
        "total_target_amount": float(total_target or 0),
        "average_progress": round(float(avg_progress), 2),
        "success_rate": round((completed or 0) / (total or 1) * 100, 2),
        "verified_rate": round((verified or 0) / (active or 1) * 100, 2)
    }


@router.get("/stats/by-category")
async def get_needs_stats_by_category(
        db: AsyncSession = Depends(get_db)
):
    """آمار آگهی‌ها به تفکیک دسته‌بندی"""

    from sqlalchemy import func, case

    # کوئری گروه‌بندی بر اساس دسته‌بندی
    query = select(
        NeedAd.category,
        func.count().label('count'),
        func.sum(NeedAd.target_amount).label('total_target'),
        func.sum(NeedAd.collected_amount).label('total_collected'),
        func.avg(
            case(
                (NeedAd.target_amount > 0,
                 NeedAd.collected_amount / NeedAd.target_amount * 100),
                else_=0
            )
        ).label('avg_progress')
    ).where(
        NeedAd.status.in_(["approved", "active", "completed"])
    ).group_by(NeedAd.category)

    result = await db.execute(query)
    rows = result.all()

    stats = {}
    for row in rows:
        category = row.category or 'other'
        stats[category] = {
            "count": row.count,
            "total_target": float(row.total_target or 0),
            "total_collected": float(row.total_collected or 0),
            "average_progress": round(float(row.avg_progress or 0), 2)
        }

    return stats


@router.get("/stats/by-province")
async def get_needs_stats_by_province(
        db: AsyncSession = Depends(get_db),
        limit: int = Query(10, ge=1, le=50)
):
    """آمار آگهی‌ها به تفکیک استان"""

    query = select(
        NeedAd.province,
        func.count().label('count'),
        func.sum(NeedAd.target_amount).label('total_target'),
        func.sum(NeedAd.collected_amount).label('total_collected')
    ).where(
        NeedAd.province.isnot(None),
        NeedAd.status.in_(["approved", "active"])
    ).group_by(NeedAd.province).order_by(
        func.count().desc()
    ).limit(limit)

    result = await db.execute(query)
    rows = result.all()

    stats = []
    for row in rows:
        if row.province:
            stats.append({
                "province": row.province,
                "needs_count": row.count,
                "total_target": float(row.total_target or 0),
                "total_collected": float(row.total_collected or 0)
            })

    return {"items": stats, "total": len(stats)}


@router.get("/stats/over-time")
async def get_needs_stats_over_time(
        db: AsyncSession = Depends(get_db),
        period: str = Query("month", regex="^(day|week|month|year)$"),
        limit: int = Query(12, ge=1, le=36)
):
    """آمار روند زمانی آگهی‌ها"""

    from sqlalchemy import func, extract

    if period == "day":
        group_by = func.date(NeedAd.created_at)
        order_by = func.date(NeedAd.created_at)
    elif period == "week":
        group_by = func.concat(
            extract('year', NeedAd.created_at), '-',
            extract('week', NeedAd.created_at)
        )
        order_by = func.min(NeedAd.created_at)
    elif period == "month":
        group_by = func.concat(
            extract('year', NeedAd.created_at), '-',
            extract('month', NeedAd.created_at)
        )
        order_by = func.min(NeedAd.created_at)
    else:  # year
        group_by = extract('year', NeedAd.created_at)
        order_by = extract('year', NeedAd.created_at)

    query = select(
        group_by.label('period'),
        func.count().label('total_created'),
        func.sum(case((NeedAd.status == "completed", 1), else_=0)).label('completed_count'),
        func.sum(NeedAd.target_amount).label('total_target'),
        func.sum(NeedAd.collected_amount).label('total_collected')
    ).group_by(group_by).order_by(order_by.desc()).limit(limit)

    result = await db.execute(query)
    rows = result.all()

    timeline = []
    for row in reversed(rows):
        timeline.append({
            "period": str(row.period),
            "needs_created": row.total_created,
            "needs_completed": row.completed_count or 0,
            "target_amount": float(row.total_target or 0),
            "collected_amount": float(row.total_collected or 0)
        })

    return {"items": timeline, "period": period}


# ==================== بخش جدید: لیست استان‌های دارای آگهی ====================

@router.get("/provinces")
async def get_provinces_list(
        db: AsyncSession = Depends(get_db),
        search: Optional[str] = Query(None, min_length=1)
):
    """
    لیست استان‌های دارای آگهی فعال
    برای فیلتر جستجو و نقشه
    """

    query = select(
        NeedAd.province,
        func.count().label('needs_count'),
        func.sum(NeedAd.collected_amount).label('total_collected'),
        func.count(case((NeedAd.is_emergency == True, 1))).label('emergency_count')
    ).where(
        NeedAd.province.isnot(None),
        NeedAd.province != '',
        NeedAd.status.in_(["approved", "active"])
    )

    if search:
        query = query.where(NeedAd.province.ilike(f"%{search}%"))

    query = query.group_by(NeedAd.province).order_by(func.count().desc())

    result = await db.execute(query)
    rows = result.all()

    provinces = []
    for row in rows:
        provinces.append({
            "name": row.province,
            "needs_count": row.needs_count,
            "total_collected": float(row.total_collected or 0),
            "emergency_count": row.emergency_count or 0
        })

    return {"provinces": provinces, "total": len(provinces)}


@router.get("/cities")
async def get_cities_list(
        db: AsyncSession = Depends(get_db),
        province: Optional[str] = Query(None)
):
    """لیست شهرهای دارای آگهی فعال بر اساس استان"""

    query = select(
        NeedAd.city,
        NeedAd.province,
        func.count().label('needs_count')
    ).where(
        NeedAd.city.isnot(None),
        NeedAd.city != '',
        NeedAd.status.in_(["approved", "active"])
    )

    if province:
        query = query.where(NeedAd.province == province)

    query = query.group_by(NeedAd.city, NeedAd.province).order_by(func.count().desc())

    result = await db.execute(query)
    rows = result.all()

    cities = []
    for row in rows:
        cities.append({
            "name": row.city,
            "province": row.province,
            "needs_count": row.needs_count
        })

    return {"cities": cities, "total": len(cities)}


@router.get("/provinces/with-coordinates")
async def get_provinces_with_coordinates(
        db: AsyncSession = Depends(get_db)
):
    """
    دریافت اطلاعات استان‌ها با مختصات جغرافیایی برای نقشه
    """

    query = select(
        NeedAd.province,
        func.count().label('needs_count'),
        func.avg(NeedAd.latitude).label('avg_latitude'),
        func.avg(NeedAd.longitude).label('avg_longitude'),
        func.sum(NeedAd.collected_amount).label('total_collected')
    ).where(
        NeedAd.province.isnot(None),
        NeedAd.latitude.isnot(None),
        NeedAd.longitude.isnot(None),
        NeedAd.status.in_(["approved", "active"])
    ).group_by(NeedAd.province)

    result = await db.execute(query)
    rows = result.all()

    provinces = []
    for row in rows:
        provinces.append({
            "name": row.province,
            "needs_count": row.needs_count,
            "latitude": float(row.avg_latitude or 0),
            "longitude": float(row.avg_longitude or 0),
            "total_collected": float(row.total_collected or 0)
        })

    return {"provinces": provinces}


# ==================== بخش جدید: اشتراک‌گذاری اجتماعی ====================

@router.post("/{need_id}/share")
async def share_need(
        need_id: int,
        platform: str = Body(..., embed=True, regex="^(telegram|whatsapp|twitter|facebook|linkedin|email|copylink)$"),
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """ثبت اشتراک‌گذاری نیاز در شبکه اجتماعی"""
    from services.need_service import NeedService
    from models import NeedAd
    from models.audit_log import AuditLog

    need = await db.get(NeedAd, need_id)
    if not need:
        raise HTTPException(status_code=404, detail="Need not found")

    service = NeedService(db)
    share_stats = await service.increment_social_share(need_id, platform, current_user.id if current_user else None, db=db)

    # ثبت لاگ اشتراک‌گذاری
    log = AuditLog(
        action="need_shared",
        user_id=current_user.id if current_user else None,
        need_id=need_id,
        metadata={"platform": platform},
        ip_address=None  # اگر بخواهید، می‌توانید IP کاربر را از request بگیرید
    )
    db.add(log)
    await db.commit()

    return {
        "success": True,
        "need_id": need_id,
        "platform": platform,
        "total_shares": share_stats["share_count"],
        "message": f"با موفقیت در {platform} به اشتراک گذاشته شد"
    }


@router.get("/{need_id}/share-stats")
async def get_share_stats(
        need_id: int,
        db: AsyncSession = Depends(get_db)
):
    """دریافت آمار اشتراک‌گذاری یک نیاز"""
    from services.need_service import NeedService
    from models import NeedAd

    need = await db.get(NeedAd, need_id)
    if not need:
        raise HTTPException(status_code=404, detail="Need not found")

    service = NeedService(db)
    stats = await service.get_social_shares(need_id, db=db)

    return {
        "need_id": need_id,
        "shares": stats  # {"telegram": 10, "facebook": 5, ...}
    }


# ==================== بخش جدید: نشان اعتماد و امتیاز ====================

@router.get("/{need_id}/trust-score")
async def get_need_trust_score(
        need_id: int,
        db: AsyncSession = Depends(get_db)
):
    """دریافت امتیاز اعتماد و نشان آگهی"""

    service = NeedService(db)
    trust_score = await service._calculate_trust_score(need_id)
    verified_by_list = await service._get_verified_by_list(need_id)

    # تعیین سطح نشان
    if trust_score >= 80:
        badge_level = "platinum"
        verified_badge = True
    elif trust_score >= 60:
        badge_level = "gold"
        verified_badge = True
    elif trust_score >= 40:
        badge_level = "silver"
        verified_badge = True
    elif trust_score >= 20:
        badge_level = "bronze"
        verified_badge = True
    else:
        badge_level = None
        verified_badge = False

    return {
        "need_id": need_id,
        "trust_score": trust_score,
        "verified_badge": verified_badge,
        "badge_level": badge_level,
        "verified_by_count": len(verified_by_list),
        "verified_by_list": verified_by_list[:5]  # فقط ۵ تا آخرین
    }


@router.post("/{need_id}/recalculate-trust")
async def recalculate_trust_score(
        need_id: int,
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER")),
        db: AsyncSession = Depends(get_db)
):
    """بازمحاسبه امتیاز اعتماد (فقط مدیر)"""

    service = NeedService(db)
    need = await service._get_need(need_id)

    trust_score = await service._calculate_trust_score(need_id)
    need.trust_score = trust_score

    # به‌روزرسانی نشان
    if trust_score >= 80:
        need.verified_badge = True
        need.badge_level = "platinum"
    elif trust_score >= 60:
        need.verified_badge = True
        need.badge_level = "gold"
    elif trust_score >= 40:
        need.verified_badge = True
        need.badge_level = "silver"
    elif trust_score >= 20:
        need.verified_badge = True
        need.badge_level = "bronze"
    else:
        need.verified_badge = False
        need.badge_level = None

    # به‌روزرسانی لیست تأییدکنندگان
    need.verified_by_list = await service._get_verified_by_list(need_id)

    db.add(need)
    await db.commit()

    return {
        "need_id": need_id,
        "trust_score": trust_score,
        "verified_badge": need.verified_badge,
        "badge_level": need.badge_level,
        "verified_by_count": len(need.verified_by_list)
    }


# ==================== بخش جدید: کمپین زمان‌دار ====================

@router.post("/{need_id}/campaign")
async def add_campaign_to_need(
        need_id: int,
        campaign_data: Dict[str, Any] = Body(...),
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER")),
        db: AsyncSession = Depends(get_db)
):
    """اضافه کردن کمپین زمان‌دار به نیاز"""

    service = NeedService(db)
    need = await service.add_campaign_settings(need_id, campaign_data, current_user)

    return {
        "need_id": need_id,
        "campaign_settings": need.campaign_settings,
        "message": "کمپین با موفقیت ایجاد شد"
    }


@router.patch("/{need_id}/campaign")
async def update_campaign_progress(
        need_id: int,
        campaign_update: Dict[str, Any] = Body(...),
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER")),
        db: AsyncSession = Depends(get_db)
):
    """به‌روزرسانی پیشرفت کمپین"""

    need = await db.get(NeedAd, need_id)
    if not need:
        raise HTTPException(status_code=404, detail="Need not found")

    if not need.campaign_settings or not need.campaign_settings.get("is_campaign"):
        raise HTTPException(status_code=400, detail="This need is not a campaign")

    # به‌روزرسانی
    need.campaign_settings.update(campaign_update)

    db.add(need)
    await db.commit()
    await db.refresh(need)

    return need.campaign_settings


# ==================== بخش جدید: پیشرفت بصری ====================

@router.get("/{need_id}/visual-progress")
async def get_visual_progress(
        need_id: int,
        db: AsyncSession = Depends(get_db)
):
    """دریافت داده‌های پیشرفت بصری برای Progress Bar دایره‌ای"""

    service = NeedService(db)
    progress_data = await service.get_visual_progress_data(need_id)

    return progress_data


# ==================== بخش جدید: لینک محصول به نیاز ====================

@router.post("/{need_id}/link-product/{product_id}")
async def link_product_to_need_endpoint(
        need_id: int,
        product_id: int,
        donation_amount: Optional[float] = Body(None),
        charity_percentage: Optional[float] = Body(None),
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER", "VENDOR")),
        db: AsyncSession = Depends(get_db)
):
    """لینک کردن محصول فروشگاهی به نیاز خاص"""

    service = NeedService(db)
    need = await service.link_product_to_need(
        need_id, product_id, current_user,
        donation_amount, charity_percentage
    )

    return {
        "need_id": need_id,
        "product_id": product_id,
        "linked_products": need.linked_product_ids,
        "message": "محصول با موفقیت به نیاز لینک شد"
    }


@router.get("/{need_id}/linked-products")
async def get_linked_products(
        need_id: int,
        db: AsyncSession = Depends(get_db),
        current_user: Optional[User] = Depends(get_current_user)
):
    """دریافت لیست محصولات لینک شده به نیاز"""

    need = await db.get(NeedAd, need_id)
    if not need:
        raise HTTPException(status_code=404, detail="Need not found")

    service = NeedService(db)
    if not service._check_view_permission(need, current_user):
        raise HTTPException(status_code=403, detail="Not authorized")

    from models.product import Product
    from models.association_tables import product_need_association

    # دریافت محصولات لینک شده با جزئیات
    query = select(
        Product,
        product_need_association.c.donation_amount,
        product_need_association.c.charity_percentage,
        product_need_association.c.created_at.label('linked_at')
    ).join(
        product_need_association,
        Product.id == product_need_association.c.product_id
    ).where(
        product_need_association.c.need_id == need_id
    )

    result = await db.execute(query)
    rows = result.all()

    products = []
    for product, donation_amount, charity_percentage, linked_at in rows:
        products.append({
            "id": product.id,
            "name": product.name,
            "price": product.price,
            "shop_id": product.shop_id,
            "shop_name": product.shop.name if product.shop else None,
            "charity_percentage": charity_percentage or product.charity_percentage,
            "donation_amount": donation_amount,
            "linked_at": linked_at.isoformat() if linked_at else None,
            "image_url": product.image_url
        })

    return {"products": products, "total": len(products)}


# ==================== بخش جدید: پیشرفت دستی ====================

@router.patch("/{need_id}/progress")
async def update_need_progress_manual(
        need_id: int,
        collected_amount: float = Body(..., embed=True, ge=0),
        notes: Optional[str] = Body(None),
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER")),
        db: AsyncSession = Depends(get_db)
):
    """به‌روزرسانی دستی پیشرفت پرداخت توسط مدیر"""

    service = NeedService(db)
    need = await service.update_need_progress(need_id, collected_amount, current_user, notes)

    return {
        "need_id": need_id,
        "collected_amount": need.collected_amount,
        "target_amount": need.target_amount,
        "progress_percentage": round((need.collected_amount or 0) / need.target_amount * 100,
                                     2) if need.target_amount > 0 else 0,
        "status": need.status,
        "message": "پیشرفت با موفقیت به‌روزرسانی شد"
    }


@router.get("/{need_id}/progress-history")
async def get_progress_history(
        need_id: int,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER"))
):
    """دریافت تاریخچه به‌روزرسانی پیشرفت"""

    need = await db.get(NeedAd, need_id)
    if not need:
        raise HTTPException(status_code=404, detail="Need not found")

    history = getattr(need, 'progress_history', [])

    # مرتب‌سازی نزولی بر اساس تاریخ
    history = sorted(
        history,
        key=lambda x: x.get('updated_at', ''),
        reverse=True
    )

    return {"history": history, "total": len(history)}


# ==================== بخش جدید: Wizard ثبت نیاز ====================

@router.post("/wizard/full", response_model=NeedAdDetail)
async def create_need_with_wizard(
        wizard_data: Dict[str, Any] = Body(...),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """ایجاد نیاز با استفاده از Wizard 5 مرحله‌ای"""

    service = NeedService(db)
    need = await service.create_need_with_wizard(wizard_data, current_user)

    return await service.get_need(need.id, current_user)


