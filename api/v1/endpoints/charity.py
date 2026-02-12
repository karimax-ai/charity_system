# app/api/v1/endpoints/charity.py
from fastapi import APIRouter, Depends, HTTPException, Query, status, Body
from sqlalchemy import and_, func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import math

from core.database import get_db
from core.permissions import get_current_user, require_roles
from models import Donation, NeedAd
from models.user import User
from models.charity import Charity
from services.charity_service import CharityService
from schemas.charity import (
    CharityCreate, CharityUpdate, CharityStatusUpdate, CharityVerification,
    CharityManagerUpdate, CharityRead, CharityDetail, CharityFilter,
    CharityStats, CharityFollower
)

router = APIRouter()


# --------------------------
# 1️⃣ CRUD اصلی خیریه‌ها
# --------------------------

@router.post("/", response_model=CharityDetail)
async def create_charity(
        charity_data: CharityCreate,
        current_user: User = Depends(require_roles("ADMIN")),
        db: AsyncSession = Depends(get_db)
):
    """ایجاد خیریه جدید (فقط ادمین)"""
    service = CharityService(db)
    charity = await service.create_charity(charity_data, current_user)
    return await service.get_charity(charity.id, current_user)


@router.get("/", response_model=Dict[str, Any])
async def list_charities(
        charity_type: Optional[str] = Query(None),
        status: Optional[str] = Query(None),
        verified: Optional[bool] = Query(None),
        active: Optional[bool] = Query(None),
        search_text: Optional[str] = Query(None),
        sort_by: str = Query("created_at"),
        sort_order: str = Query("desc"),
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """لیست خیریه‌ها با فیلتر و صفحه‌بندی"""
    filters = CharityFilter(
        charity_type=charity_type,
        status=status,
        verified=verified,
        active=active,
        search_text=search_text,
        sort_by=sort_by,
        sort_order=sort_order
    )

    service = CharityService(db)
    return await service.list_charities(filters, current_user, page, limit)


@router.get("/{charity_id}", response_model=CharityDetail)
async def get_charity(
        charity_id: int,
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """دریافت اطلاعات یک خیریه"""
    service = CharityService(db)
    return await service.get_charity(charity_id, current_user)


@router.put("/{charity_id}", response_model=CharityDetail)
async def update_charity(
        charity_id: int,
        charity_data: CharityUpdate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """ویرایش اطلاعات خیریه"""
    service = CharityService(db)
    charity = await service.update_charity(charity_id, charity_data, current_user)
    return await service.get_charity(charity.id, current_user)


@router.delete("/{charity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_charity(
        charity_id: int,
        current_user: User = Depends(require_roles("ADMIN")),
        db: AsyncSession = Depends(get_db)
):
    """حذف خیریه (فقط ادمین)"""
    from sqlalchemy import delete

    service = CharityService(db)
    charity = await service._get_charity(charity_id)

    # بررسی اینکه خیریه خالی باشد
    from sqlalchemy import select, func
    from models.need_ad import NeedAd
    from models.donation import Donation

    # بررسی وجود نیازهای فعال
    active_needs = await db.execute(
        select(func.count(NeedAd.id)).where(
            and_(
                NeedAd.charity_id == charity_id,
                NeedAd.status.in_(["active", "pending", "approved"])
            )
        )
    )

    if active_needs.scalar() > 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete charity with active needs"
        )

    # بررسی وجود کمک‌های پرداخت شده
    recent_donations = await db.execute(
        select(func.count(Donation.id)).where(
            and_(
                Donation.charity_id == charity_id,
                Donation.created_at >= datetime.utcnow() - timedelta(days=365)
            )
        )
    )

    if recent_donations.scalar() > 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete charity with donations in the last year"
        )

    # غیرفعال کردن به جای حذف
    charity.active = False
    charity.status = "inactive"

    db.add(charity)
    await db.commit()

    return None


# --------------------------
# 2️⃣ مدیریت وضعیت خیریه‌ها
# --------------------------

@router.patch("/{charity_id}/status", response_model=CharityDetail)
async def update_charity_status(
        charity_id: int,
        status_data: CharityStatusUpdate,
        current_user: User = Depends(require_roles("ADMIN")),
        db: AsyncSession = Depends(get_db)
):
    """تغییر وضعیت خیریه (فقط ادمین)"""
    service = CharityService(db)
    charity = await service.update_charity_status(charity_id, status_data, current_user)
    return await service.get_charity(charity.id, current_user)


@router.post("/{charity_id}/verify", response_model=CharityDetail)
async def verify_charity(
        charity_id: int,
        verification_data: CharityVerification,
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER")),
        db: AsyncSession = Depends(get_db)
):
    """تأیید یا رد خیریه"""
    service = CharityService(db)
    charity = await service.verify_charity(charity_id, verification_data, current_user)
    return await service.get_charity(charity.id, current_user)


@router.patch("/{charity_id}/manager", response_model=CharityDetail)
async def update_charity_manager(
        charity_id: int,
        manager_data: CharityManagerUpdate,
        current_user: User = Depends(require_roles("ADMIN")),
        db: AsyncSession = Depends(get_db)
):
    """تغییر مدیر خیریه (فقط ادمین)"""
    service = CharityService(db)
    charity = await service.update_charity_manager(charity_id, manager_data, current_user)
    return await service.get_charity(charity.id, current_user)


# --------------------------
# 3️⃣ آمار و گزارش‌ها
# --------------------------

@router.get("/{charity_id}/stats", response_model=Dict[str, Any])
async def get_charity_stats(
        charity_id: int,
        period_days: int = Query(30, ge=1, le=365),
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """دریافت آمار خیریه"""
    service = CharityService(db)
    return await service.get_charity_stats(charity_id, period_days, current_user)


@router.get("/{charity_id}/stats/detailed")
async def get_detailed_charity_stats(
        charity_id: int,
        start_date: Optional[datetime] = Query(None),
        end_date: Optional[datetime] = Query(None),
        group_by: str = Query("day", regex="^(day|week|month|year)$"),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """آمار دقیق با گروه‌بندی زمانی"""
    from sqlalchemy import select, func, extract, case
    from datetime import date

    service = CharityService(db)
    charity = await service._get_charity(charity_id)

    # بررسی دسترسی
    if not service._can_view_charity_details(charity, current_user):
        raise HTTPException(status_code=403, detail="Not authorized")

    # تنظیم تاریخ‌ها
    if not end_date:
        end_date = datetime.utcnow()
    if not start_date:
        start_date = end_date - timedelta(days=30)

    # تعیین تابع گروه‌بندی
    if group_by == "day":
        group_func = func.date
    elif group_by == "week":
        group_func = lambda col: func.concat(
            extract('year', col), '-',
            func.lpad(extract('week', col), 2, '0')
        )
    elif group_by == "month":
        group_func = lambda col: func.concat(
            extract('year', col), '-',
            func.lpad(extract('month', col), 2, '0')
        )
    else:  # year
        group_func = extract('year')

    # آمار کمک‌ها بر اساس زمان
    donations_query = select(
        group_func(Donation.created_at).label("period"),
        func.count(Donation.id).label("donation_count"),
        func.sum(Donation.amount).label("donation_amount"),
        func.avg(Donation.amount).label("average_donation")
    ).where(
        and_(
            Donation.charity_id == charity_id,
            Donation.status == "completed",
            Donation.created_at.between(start_date, end_date)
        )
    ).group_by("period").order_by("period")

    result = await db.execute(donations_query)
    donations_data = [
        {
            "period": str(row.period),
            "donation_count": row.donation_count,
            "donation_amount": float(row.donation_amount or 0),
            "average_donation": float(row.average_donation or 0)
        }
        for row in result.all()
    ]

    # آمار نیازها
    needs_query = select(
        group_func(NeedAd.created_at).label("period"),
        func.count(NeedAd.id).label("needs_count"),
        func.sum(case([(NeedAd.status == "completed", 1)], else_=0)).label("completed_count"),
        func.avg(NeedAd.target_amount).label("average_target")
    ).where(
        and_(
            NeedAd.charity_id == charity_id,
            NeedAd.created_at.between(start_date, end_date)
        )
    ).group_by("period").order_by("period")

    result = await db.execute(needs_query)
    needs_data = [
        {
            "period": str(row.period),
            "needs_count": row.needs_count,
            "completed_count": row.completed_count,
            "completion_rate": (
                (row.completed_count / row.needs_count * 100)
                if row.needs_count and row.needs_count > 0 else 0
            ),
            "average_target": float(row.average_target or 0)
        }
        for row in result.all()
    ]

    return {
        "charity_id": charity_id,
        "start_date": start_date,
        "end_date": end_date,
        "group_by": group_by,
        "donations_by_period": donations_data,
        "needs_by_period": needs_data
    }


# --------------------------
# 4️⃣ مدیریت دنبال‌کنندگان
# --------------------------

@router.post("/{charity_id}/follow")
async def follow_charity(
        charity_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """دنبال کردن یک خیریه"""
    from sqlalchemy import insert
    from models.association_tables import charity_followers

    service = CharityService(db)
    charity = await service._get_charity(charity_id)

    # بررسی اینکه کاربر قبلاً دنبال نکرده باشد
    existing = await db.execute(
        select(charity_followers).where(
            and_(
                charity_followers.c.charity_id == charity_id,
                charity_followers.c.user_id == current_user.id
            )
        )
    )

    if existing.first():
        raise HTTPException(status_code=400, detail="Already following this charity")

    # اضافه کردن به دنبال‌کنندگان
    await db.execute(
        insert(charity_followers).values(
            charity_id=charity_id,
            user_id=current_user.id
        )
    )
    await db.commit()

    return {"detail": "Charity followed successfully"}


@router.delete("/{charity_id}/unfollow")
async def unfollow_charity(
        charity_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """لغو دنبال کردن یک خیریه"""
    from sqlalchemy import delete
    from models.association_tables import charity_followers

    service = CharityService(db)
    charity = await service._get_charity(charity_id)

    # حذف از دنبال‌کنندگان
    await db.execute(
        delete(charity_followers).where(
            and_(
                charity_followers.c.charity_id == charity_id,
                charity_followers.c.user_id == current_user.id
            )
        )
    )
    await db.commit()

    return {"detail": "Charity unfollowed successfully"}


@router.get("/{charity_id}/followers", response_model=Dict[str, Any])
async def get_charity_followers(
        charity_id: int,
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """لیست دنبال‌کنندگان یک خیریه"""
    from sqlalchemy import select
    from models.association_tables import charity_followers

    service = CharityService(db)
    charity = await service._get_charity(charity_id)

    # بررسی دسترسی
    if not service._can_view_charity_details(charity, current_user):
        raise HTTPException(status_code=403, detail="Not authorized")

    # کوئری اصلی
    query = select(charity_followers).where(
        charity_followers.c.charity_id == charity_id
    )

    # شمارش کل
    total_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(total_query)

    # صفحه‌بندی
    offset = (page - 1) * limit
    query = query.order_by(charity_followers.c.created_at.desc())
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    followers = result.all()

    # گرفتن اطلاعات کاربران
    followers_list = []
    for follower in followers:
        user = await db.get(User, follower.user_id)
        if user:
            followers_list.append({
                "user_id": user.id,
                "user_name": user.username or user.email.split('@')[0],
                "user_email": user.email if service._can_view_manager_details(current_user) else None,
                "followed_at": follower.created_at,
                "avatar_url": user.avatar_url
            })

    return {
        "items": followers_list,
        "total": total or 0,
        "page": page,
        "limit": limit,
        "total_pages": math.ceil(total / limit) if total and total > 0 else 0
    }


@router.get("/user/following", response_model=Dict[str, Any])
async def get_user_following(
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """خیریه‌های دنبال شده توسط کاربر"""
    from sqlalchemy import select
    from models.association_tables import charity_followers

    # کوئری اصلی
    query = select(charity_followers).where(
        charity_followers.c.user_id == current_user.id
    )

    # شمارش کل
    total_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(total_query)

    # صفحه‌بندی
    offset = (page - 1) * limit
    query = query.order_by(charity_followers.c.created_at.desc())
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    following = result.all()

    # گرفتن اطلاعات خیریه‌ها
    service = CharityService(db)
    following_list = []
    for follow in following:
        charity = await db.get(Charity, follow.charity_id)
        if charity and charity.active:
            charity_data = await service.get_charity(charity.id, current_user)
            following_list.append({
                **charity_data,
                "followed_at": follow.created_at
            })

    return {
        "items": following_list,
        "total": total or 0,
        "page": page,
        "limit": limit,
        "total_pages": math.ceil(total / limit) if total and total > 0 else 0
    }


# --------------------------
# 5️⃣ نیازهای یک خیریه
# --------------------------

@router.get("/{charity_id}/needs", response_model=Dict[str, Any])
async def get_charity_needs(
        charity_id: int,
        status: Optional[str] = Query(None),
        category: Optional[str] = Query(None),
        is_urgent: Optional[bool] = Query(None),
        sort_by: str = Query("created_at"),
        sort_order: str = Query("desc"),
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """نیازهای یک خیریه خاص"""
    from sqlalchemy import select
    from models.need_ad import NeedAd
    from services.need_service import NeedService

    service = CharityService(db)
    charity = await service._get_charity(charity_id)

    # بررسی دسترسی
    if not service._can_view_charity_details(charity, current_user):
        raise HTTPException(status_code=403, detail="Not authorized")

    # ساخت کوئری
    query = select(NeedAd).where(NeedAd.charity_id == charity_id)

    # اعمال فیلترها
    if status:
        query = query.where(NeedAd.status == status)
    if category:
        query = query.where(NeedAd.category == category)
    if is_urgent is not None:
        query = query.where(NeedAd.is_urgent == is_urgent)

    # مرتب‌سازی
    sort_column = getattr(NeedAd, sort_by, NeedAd.created_at)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # شمارش کل
    total_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(total_query)

    # صفحه‌بندی
    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    needs = result.scalars().all()

    # تبدیل به فرمت خروجی
    need_service = NeedService(db)
    need_list = []
    for need in needs:
        need_data = await need_service.get_need(need.id, current_user)
        need_list.append(need_data)

    return {
        "charity_id": charity_id,
        "charity_name": charity.name,
        "items": need_list,
        "total": total or 0,
        "page": page,
        "limit": limit,
        "total_pages": math.ceil(total / limit) if total and total > 0 else 0
    }


# --------------------------
# 6️⃣ تأییدیه‌های داده شده
# --------------------------

@router.get("/{charity_id}/verifications/given")
async def get_charity_verifications_given(
        charity_id: int,
        status: Optional[str] = Query(None),
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """تأییدیه‌های داده شده توسط یک خیریه"""
    from sqlalchemy import select
    from models.need_verification import NeedVerification

    service = CharityService(db)
    charity = await service._get_charity(charity_id)

    # بررسی دسترسی
    if not service._can_view_charity_details(charity, current_user):
        raise HTTPException(status_code=403, detail="Not authorized")

    # ساخت کوئری
    query = select(NeedVerification).where(
        NeedVerification.charity_id == charity_id
    )

    if status:
        query = query.where(NeedVerification.status == status)

    # شمارش کل
    total_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(total_query)

    # صفحه‌بندی
    offset = (page - 1) * limit
    query = query.order_by(NeedVerification.created_at.desc())
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    verifications = result.scalars().all()

    # تبدیل به فرمت خروجی
    verifications_list = []
    for v in verifications:
        verification_data = {
            "id": v.id,
            "need_id": v.need_id,
            "need_title": v.need.title if v.need else None,
            "need_charity": v.need.charity.name if v.need and v.need.charity else None,
            "status": v.status,
            "comment": v.comment,
            "verified_at": v.verified_at,
            "created_at": v.created_at
        }
        verifications_list.append(verification_data)

    return {
        "charity_id": charity_id,
        "charity_name": charity.name,
        "items": verifications_list,
        "total": total or 0,
        "page": page,
        "limit": limit,
        "total_pages": math.ceil(total / limit) if total and total > 0 else 0
    }


# --------------------------
# 7️⃣ مدیر خیریه‌های من
# --------------------------

@router.get("/user/managed", response_model=Dict[str, Any])
async def get_managed_charities(
        status: Optional[str] = Query(None),
        verified: Optional[bool] = Query(None),
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """خیریه‌های مدیریت شده توسط کاربر"""
    from sqlalchemy import select

    # فقط مدیران یا ادمین‌ها
    user_roles = [r.key for r in current_user.roles]
    if "ADMIN" not in user_roles and "CHARITY_MANAGER" not in user_roles:
        # کاربر عادی فقط خیریه‌های خودش را می‌بیند
        query = select(Charity).where(Charity.manager_id == current_user.id)
    else:
        # مدیر یا ادمین همه خیریه‌ها را می‌بیند
        query = select(Charity)

    # اعمال فیلترها
    if status:
        query = query.where(Charity.status == status)
    if verified is not None:
        query = query.where(Charity.verified == verified)

    # شمارش کل
    total_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(total_query)

    # صفحه‌بندی
    offset = (page - 1) * limit
    query = query.order_by(Charity.created_at.desc())
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    charities = result.scalars().all()

    # تبدیل به فرمت خروجی
    service = CharityService(db)
    charity_list = []
    for charity in charities:
        charity_data = await service.get_charity(charity.id, current_user)
        charity_list.append(charity_data)

    return {
        "items": charity_list,
        "total": total or 0,
        "page": page,
        "limit": limit,
        "total_pages": math.ceil(total / limit) if total and total > 0 else 0
    }


# --------------------------
# 8️⃣ جستجوی خیریه‌ها
# --------------------------

@router.get("/search/autocomplete")
async def charity_autocomplete(
        q: str = Query(..., min_length=1),
        limit: int = Query(10, ge=1, le=50),
        db: AsyncSession = Depends(get_db)
):
    """جستجوی سریع خیریه‌ها"""
    from sqlalchemy import select

    query = select(Charity).where(
        and_(
            Charity.active == True,
            or_(
                Charity.name.ilike(f"%{q}%"),
                Charity.description.ilike(f"%{q}%")
            )
        )
    ).limit(limit)

    result = await db.execute(query)
    charities = result.scalars().all()

    suggestions = []
    for charity in charities:
        suggestions.append({
            "id": charity.id,
            "name": charity.name,
            "description": charity.description[:100] + "..." if len(charity.description) > 100 else charity.description,
            "charity_type": charity.charity_type,
            "verified": charity.verified,
            "logo_url": charity.logo_url
        })

    return {"suggestions": suggestions}


# --------------------------
# 9️⃣ خیریه‌های پرطرفدار
# --------------------------

@router.get("/popular")
async def get_popular_charities(
        period_days: int = Query(30, ge=1, le=365),
        limit: int = Query(10, ge=1, le=50),
        db: AsyncSession = Depends(get_db)
):
    """خیریه‌های پرطرفدار بر اساس معیارهای مختلف"""
    from sqlalchemy import select, func
    from models.donation import Donation
    from models.association_tables import charity_followers

    # تاریخ شروع
    since_date = datetime.utcnow() - timedelta(days=period_days)

    # محبوبیت بر اساس تعداد دنبال‌کنندگان
    followers_popularity = select(
        Charity.id,
        Charity.name,
        Charity.logo_url,
        func.count(charity_followers.c.user_id).label("followers_count"),
        func.literal("followers").label("popularity_type")
    ).join(
        charity_followers, Charity.id == charity_followers.c.charity_id, isouter=True
    ).where(
        and_(
            Charity.active == True,
            Charity.verified == True,
            charity_followers.c.created_at >= since_date
        )
    ).group_by(Charity.id).order_by(func.count(charity_followers.c.user_id).desc()).limit(limit)

    # محبوبیت بر اساس کمک‌های دریافتی
    donations_popularity = select(
        Charity.id,
        Charity.name,
        Charity.logo_url,
        func.coalesce(func.sum(Donation.amount), 0).label("donations_amount"),
        func.literal("donations").label("popularity_type")
    ).join(
        Donation, Charity.id == Donation.charity_id, isouter=True
    ).where(
        and_(
            Charity.active == True,
            Charity.verified == True,
            Donation.created_at >= since_date,
            Donation.status == "completed"
        )
    ).group_by(Charity.id).order_by(func.coalesce(func.sum(Donation.amount), 0).desc()).limit(limit)

    # محبوبیت بر اساس تعداد نیازهای تکمیل شده
    needs_popularity = select(
        Charity.id,
        Charity.name,
        Charity.logo_url,
        func.count(NeedAd.id).label("completed_needs_count"),
        func.literal("needs").label("popularity_type")
    ).join(
        NeedAd, Charity.id == NeedAd.charity_id
    ).where(
        and_(
            Charity.active == True,
            Charity.verified == True,
            NeedAd.status == "completed",
            NeedAd.updated_at >= since_date
        )
    ).group_by(Charity.id).order_by(func.count(NeedAd.id).desc()).limit(limit)

    # اجرای کوئری‌ها
    result1 = await db.execute(followers_popularity)
    result2 = await db.execute(donations_popularity)
    result3 = await db.execute(needs_popularity)

    # ترکیب نتایج
    popular_charities = {}

    for row in result1.all():
        popular_charities[row.id] = {
            "id": row.id,
            "name": row.name,
            "logo_url": row.logo_url,
            "followers_count": row.followers_count,
            "donations_amount": 0,
            "completed_needs_count": 0,
            "popularity_score": row.followers_count
        }

    for row in result2.all():
        if row.id in popular_charities:
            popular_charities[row.id]["donations_amount"] = float(row.donations_amount or 0)
            popular_charities[row.id]["popularity_score"] += float(row.donations_amount or 0)
        else:
            popular_charities[row.id] = {
                "id": row.id,
                "name": row.name,
                "logo_url": row.logo_url,
                "followers_count": 0,
                "donations_amount": float(row.donations_amount or 0),
                "completed_needs_count": 0,
                "popularity_score": float(row.donations_amount or 0)
            }

    for row in result3.all():
        if row.id in popular_charities:
            popular_charities[row.id]["completed_needs_count"] = row.completed_needs_count
            popular_charities[row.id]["popularity_score"] += row.completed_needs_count * 1000  # وزن برای نیازها
        else:
            popular_charities[row.id] = {
                "id": row.id,
                "name": row.name,
                "logo_url": row.logo_url,
                "followers_count": 0,
                "donations_amount": 0,
                "completed_needs_count": row.completed_needs_count,
                "popularity_score": row.completed_needs_count * 1000
            }

    # مرتب‌سازی بر اساس امتیاز
    sorted_charities = sorted(
        popular_charities.values(),
        key=lambda x: x["popularity_score"],
        reverse=True
    )[:limit]

    return {
        "period_days": period_days,
        "popular_charities": sorted_charities
    }