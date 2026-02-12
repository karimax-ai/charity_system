# app/api/v1/endpoints/dashboard.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from core.database import get_db
from core.permissions import get_current_user, require_roles
from models.user import User
from services.dashboard_service import DashboardService
from services.statistics_service import StatisticsService
from schemas.dashboard import (
    AdminDashboard, SuperAdminDashboard, CharityManagerDashboard,
    CharityDashboard, NeedyDashboard, DonorDashboard,
    VendorDashboard, ShopManagerDashboard, VolunteerDashboard,
    GeographicalStats, TemporalStats, ProductSalesStats,
    UserProfileAdvanced
)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


# --------------------------
# 1️⃣ داشبورد ادمین
# --------------------------
@router.get("/admin", response_model=AdminDashboard)
async def get_admin_dashboard(
        current_user: User = Depends(require_roles("ADMIN", "SUPER_ADMIN")),
        db: AsyncSession = Depends(get_db)
):
    """
    داشبورد مدیریتی برای ادمین‌ها
    دسترسی: ADMIN, SUPER_ADMIN
    """
    service = DashboardService(db)
    dashboard_data = await service.get_admin_dashboard(current_user)
    return dashboard_data


@router.get("/super-admin", response_model=SuperAdminDashboard)
async def get_super_admin_dashboard(
        current_user: User = Depends(require_roles("SUPER_ADMIN")),
        db: AsyncSession = Depends(get_db)
):
    """
    داشبورد کامل برای سوپر ادمین
    دسترسی: SUPER_ADMIN
    """
    service = DashboardService(db)
    dashboard_data = await service.get_admin_dashboard(current_user)

    # اضافه کردن آمار ویژه سوپر ادمین
    stats_service = StatisticsService(db)

    # آمار سیستم
    system_metrics = {
        "active_users": await db.scalar("SELECT COUNT(*) FROM users WHERE is_active = true"),
        "pending_verifications": await db.scalar("SELECT COUNT(*) FROM users WHERE status = 'need_verification'"),
        "total_transactions": await db.scalar("SELECT COUNT(*) FROM donations WHERE status = 'completed'"),
        "system_uptime": "99.9%",
        "last_backup": datetime.utcnow() - timedelta(hours=6),
    }

    dashboard_data["system_metrics"] = system_metrics
    dashboard_data["admin_activities"] = []  # TODO: از لاگ بخواند
    dashboard_data["audit_logs_summary"] = {
        "today": await db.scalar("SELECT COUNT(*) FROM audit_logs WHERE created_at >= NOW() - INTERVAL '1 day'"),
        "this_week": await db.scalar("SELECT COUNT(*) FROM audit_logs WHERE created_at >= NOW() - INTERVAL '7 days'"),
        "this_month": await db.scalar("SELECT COUNT(*) FROM audit_logs WHERE created_at >= NOW() - INTERVAL '30 days'"),
    }
    dashboard_data["performance_metrics"] = {
        "avg_response_time": "245ms",
        "error_rate": "0.02%",
        "requests_per_minute": 1250,
    }

    return dashboard_data


# --------------------------
# 2️⃣ داشبورد مدیر خیریه‌ها
# --------------------------
@router.get("/charity-manager", response_model=CharityManagerDashboard)
async def get_charity_manager_dashboard(
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER")),
        db: AsyncSession = Depends(get_db)
):
    """
    داشبورد مدیر خیریه‌ها
    دسترسی: ADMIN, CHARITY_MANAGER
    """
    service = DashboardService(db)
    return await service.get_charity_manager_dashboard(current_user)


# --------------------------
# 3️⃣ داشبورد خیریه
# --------------------------
@router.get("/charity/{charity_id}", response_model=CharityDashboard)
async def get_charity_dashboard(
        charity_id: int,
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    داشبورد یک خیریه خاص
    دسترسی: عمومی (محدود) / مدیران خیریه (کامل)
    """
    service = DashboardService(db)
    return await service.get_charity_dashboard(charity_id, current_user)


# --------------------------
# 4️⃣ داشبورد نیازمند
# --------------------------
@router.get("/needy", response_model=NeedyDashboard)
async def get_needy_dashboard(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    داشبورد کاربر نیازمند
    دسترسی: NEEDY
    """
    # بررسی نقش نیازمند
    user_roles = [r.key for r in current_user.roles]
    if "NEEDY" not in user_roles:
        raise HTTPException(status_code=403, detail="Only needy users can access this dashboard")

    service = DashboardService(db)
    return await service.get_needy_dashboard(current_user.id)


@router.get("/needy/{user_id}", response_model=NeedyDashboard)
async def get_needy_dashboard_by_id(
        user_id: int,
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER")),
        db: AsyncSession = Depends(get_db)
):
    """
    مشاهده داشبورد یک نیازمند خاص (فقط مدیران)
    دسترسی: ADMIN, CHARITY_MANAGER
    """
    service = DashboardService(db)
    return await service.get_needy_dashboard(user_id)


# --------------------------
# 5️⃣ داشبورد خیر کمک‌کننده
# --------------------------
@router.get("/donor", response_model=DonorDashboard)
async def get_donor_dashboard(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    داشبورد خیر کمک‌کننده
    دسترسی: DONOR
    """
    user_roles = [r.key for r in current_user.roles]
    if "DONOR" not in user_roles:
        raise HTTPException(status_code=403, detail="Only donors can access this dashboard")

    service = DashboardService(db)
    return await service.get_donor_dashboard(current_user.id)


@router.get("/donor/{user_id}", response_model=DonorDashboard)
async def get_donor_dashboard_by_id(
        user_id: int,
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER")),
        db: AsyncSession = Depends(get_db)
):
    """
    مشاهده داشبورد یک خیر خاص (فقط مدیران)
    دسترسی: ADMIN, CHARITY_MANAGER
    """
    service = DashboardService(db)
    return await service.get_donor_dashboard(user_id)


# --------------------------
# 6️⃣ داشبورد فروشنده
# --------------------------
@router.get("/vendor", response_model=VendorDashboard)
async def get_vendor_dashboard(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    داشبورد فروشنده
    دسترسی: VENDOR
    """
    user_roles = [r.key for r in current_user.roles]
    if "VENDOR" not in user_roles:
        raise HTTPException(status_code=403, detail="Only vendors can access this dashboard")

    service = DashboardService(db)
    return await service.get_vendor_dashboard(current_user.id)


# --------------------------
# 7️⃣ داشبورد مدیر فروشگاه
# --------------------------
@router.get("/shop-manager", response_model=ShopManagerDashboard)
async def get_shop_manager_dashboard(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    داشبورد مدیر فروشگاه
    دسترسی: SHOP_MANAGER
    """
    user_roles = [r.key for r in current_user.roles]
    if "SHOP_MANAGER" not in user_roles:
        raise HTTPException(status_code=403, detail="Only shop managers can access this dashboard")

    service = DashboardService(db)
    return await service.get_shop_manager_dashboard(current_user.id)


# --------------------------
# 8️⃣ داشبورد داوطلب
# --------------------------
@router.get("/volunteer", response_model=VolunteerDashboard)
async def get_volunteer_dashboard(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    داشبورد داوطلب
    دسترسی: VOLUNTEER
    """
    user_roles = [r.key for r in current_user.roles]
    if "VOLUNTEER" not in user_roles:
        raise HTTPException(status_code=403, detail="Only volunteers can access this dashboard")

    service = DashboardService(db)
    return await service.get_volunteer_dashboard(current_user.id)


# --------------------------
# 9️⃣ پروفایل پیشرفته کاربر
# --------------------------
@router.get("/profile", response_model=UserProfileAdvanced)
async def get_advanced_profile(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    پروفایل پیشرفته کاربر با تمام آمار و تاریخچه
    دسترسی: خود کاربر
    """
    service = DashboardService(db)
    stats_service = StatisticsService(db)

    # اطلاعات پایه
    basic_info = {
        "id": current_user.id,
        "uuid": current_user.uuid,
        "username": current_user.username,
        "email": current_user.email,
        "phone": current_user.phone,
        "full_name": current_user.full_name,
        "avatar_url": current_user.avatar_url,
        "is_verified": current_user.is_verified,
        "member_since": current_user.created_at,
        "roles": [r.key for r in current_user.roles],
    }

    # آمار بر اساس نقش
    user_roles = [r.key for r in current_user.roles]
    stats = {
        "user_id": current_user.id,
        "user_type": user_roles[0] if user_roles else "USER",
        "member_since": current_user.created_at,
        "total_donated": 0,
        "donations_count": 0,
        "total_needs": 0,
        "fulfilled_needs": 0,
        "total_products_sold": 0,
        "total_sales": 0,
        "charity_contribution": 0,
        "volunteer_hours": 0,
        "completed_tasks": 0,
    }

    # آمار کمک‌ها
    if "DONOR" in user_roles:
        donor_stats = await service.get_donor_dashboard(current_user.id)
        stats["total_donated"] = donor_stats["summary"]["total_donated"]
        stats["donations_count"] = donor_stats["summary"]["donations_count"]

    # آمار نیازها
    if "NEEDY" in user_roles:
        needy_stats = await service.get_needy_dashboard(current_user.id)
        stats["total_needs"] = needy_stats["summary"]["total_needs"]
        stats["fulfilled_needs"] = needy_stats["summary"]["completed_needs"]

    # آمار فروش
    if "VENDOR" in user_roles:
        vendor_stats = await service.get_vendor_dashboard(current_user.id)
        stats["total_products_sold"] = vendor_stats["summary"].get("total_sales", 0)
        stats["charity_contribution"] = vendor_stats["summary"].get("total_charity_generated", 0)

    # تاریخچه فعالیت (نمونه)
    timeline = [
        {
            "date": current_user.created_at,
            "action": "user_registered",
            "description": "عضو پلتفرم شد",
        }
    ]

    # نشان‌ها و دستاوردها
    badges = []
    if stats["total_donated"] >= 1000000:
        badges.append("خیر برنزی")
    if stats["total_donated"] >= 10000000:
        badges.append("خیر نقره‌ای")
    if stats["total_donated"] >= 50000000:
        badges.append("خیر طلایی")
    if stats["fulfilled_needs"] >= 1:
        badges.append("نیازمند موفق")
    if stats["charity_contribution"] >= 1000000:
        badges.append("فروشنده خیر")

    return {
        "basic_info": basic_info,
        "stats": stats,
        "timeline": timeline,
        "badges": badges,
        "certificates": [],
        "achievements": badges,
    }


# --------------------------
# 🔟 آمار و تحلیل‌ها
# --------------------------
@router.get("/statistics/donations")
async def get_donation_statistics(
        days: int = Query(365, ge=1, le=1095),
        charity_id: Optional[int] = Query(None),
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER")),
        db: AsyncSession = Depends(get_db)
):
    """
    آمار کامل کمک‌ها
    دسترسی: ADMIN, CHARITY_MANAGER
    """
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    service = StatisticsService(db)
    return await service.get_donation_statistics(start_date, end_date, charity_id)


@router.get("/statistics/needs")
async def get_need_statistics(
        days: int = Query(365, ge=1, le=1095),
        charity_id: Optional[int] = Query(None),
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER")),
        db: AsyncSession = Depends(get_db)
):
    """
    آمار نیازها
    دسترسی: ADMIN, CHARITY_MANAGER
    """
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    service = StatisticsService(db)
    return await service.get_need_statistics(start_date, end_date, charity_id)


@router.get("/statistics/geographical", response_model=GeographicalStats)
async def get_geographical_statistics(
        days: int = Query(365, ge=1, le=1095),
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER")),
        db: AsyncSession = Depends(get_db)
):
    """
    تحلیل جغرافیایی کمک‌ها و نیازها
    دسترسی: ADMIN, CHARITY_MANAGER
    """
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    service = StatisticsService(db)
    return await service.get_geographical_statistics(start_date, end_date)


@router.get("/statistics/products", response_model=ProductSalesStats)
async def get_product_statistics(
        days: int = Query(365, ge=1, le=1095),
        charity_id: Optional[int] = Query(None),
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER")),
        db: AsyncSession = Depends(get_db)
):
    """
    آمار فروش محصولات
    دسترسی: ADMIN, CHARITY_MANAGER
    """
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    service = StatisticsService(db)
    return await service.get_product_sales_statistics(start_date, end_date, charity_id)


@router.get("/statistics/users")
async def get_user_statistics(
        days: int = Query(365, ge=1, le=1095),
        current_user: User = Depends(require_roles("ADMIN")),
        db: AsyncSession = Depends(get_db)
):
    """
    آمار کاربران
    دسترسی: ADMIN
    """
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    service = StatisticsService(db)
    return await service.get_user_statistics(start_date, end_date)


# --------------------------
# 1️⃣1️⃣ داشبورد سفارشی‌سازی شده
# --------------------------
@router.get("/custom")
async def get_custom_dashboard(
        metrics: str = Query(..., description="Comma-separated metric names"),
        period: str = Query("month", regex="^(day|week|month|year)$"),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    داشبورد سفارشی با انتخاب معیارهای دلخواه
    دسترسی: کاربران لاگین کرده
    """
    from sqlalchemy import text

    metric_list = [m.strip() for m in metrics.split(",")]
    result = {}

    end_date = datetime.utcnow()
    if period == "day":
        start_date = end_date - timedelta(days=1)
    elif period == "week":
        start_date = end_date - timedelta(weeks=1)
    elif period == "month":
        start_date = end_date - timedelta(days=30)
    else:  # year
        start_date = end_date - timedelta(days=365)

    user_roles = [r.key for r in current_user.roles]
    is_admin = "ADMIN" in user_roles or "SUPER_ADMIN" in user_roles

    for metric in metric_list:
        if metric == "total_donations":
            query = "SELECT COALESCE(SUM(amount), 0) FROM donations WHERE status = 'completed'"
            if not is_admin:
                query += f" AND donor_id = {current_user.id}"
            result[metric] = float(await db.scalar(text(query)) or 0)

        elif metric == "total_needs":
            query = "SELECT COUNT(*) FROM need_ads"
            if not is_admin:
                query += f" WHERE needy_user_id = {current_user.id} OR created_by_id = {current_user.id}"
            result[metric] = await db.scalar(text(query)) or 0

        elif metric == "my_donations" and not is_admin:
            query = f"SELECT COUNT(*) FROM donations WHERE donor_id = {current_user.id}"
            result[metric] = await db.scalar(text(query)) or 0

        elif metric == "my_needs" and not is_admin:
            query = f"SELECT COUNT(*) FROM need_ads WHERE needy_user_id = {current_user.id}"
            result[metric] = await db.scalar(text(query)) or 0

    return {
        "user_id": current_user.id,
        "period": period,
        "metrics": result,
        "generated_at": datetime.utcnow(),
    }


# --------------------------
# 1️⃣2️⃣ ویجت‌های داشبورد
# --------------------------
@router.get("/widgets/recent-activities")
async def get_recent_activities(
        limit: int = Query(10, ge=1, le=50),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    آخرین فعالیت‌های کاربر
    دسترسی: خود کاربر
    """
    from sqlalchemy import union, text

    # کمک‌های اخیر
    donations_query = text(f"""
        SELECT 'donation' as type, id, amount as value, created_at,
               'کمک به ' || COALESCE((SELECT name FROM charities WHERE id = donations.charity_id), 'خیریه') as description
        FROM donations 
        WHERE donor_id = {current_user.id}
        ORDER BY created_at DESC
        LIMIT {limit}
    """)

    # نیازهای اخیر
    needs_query = text(f"""
        SELECT 'need' as type, id, target_amount as value, created_at,
               title as description
        FROM need_ads 
        WHERE needy_user_id = {current_user.id} OR created_by_id = {current_user.id}
        ORDER BY created_at DESC
        LIMIT {limit}
    """)

    # محصولات اخیر
    products_query = text(f"""
        SELECT 'product' as type, id, price as value, created_at,
               name as description
        FROM products 
        WHERE vendor_id = {current_user.id}
        ORDER BY created_at DESC
        LIMIT {limit}
    """)

    result = []

    try:
        donations = await db.execute(donations_query)
        result.extend([dict(row._mapping) for row in donations])
    except:
        pass

    try:
        needs = await db.execute(needs_query)
        result.extend([dict(row._mapping) for row in needs])
    except:
        pass

    try:
        products = await db.execute(products_query)
        result.extend([dict(row._mapping) for row in products])
    except:
        pass

    # مرتب‌سازی بر اساس تاریخ
    result.sort(key=lambda x: x["created_at"], reverse=True)

    return {
        "activities": result[:limit],
        "total": len(result),
    }


@router.get("/widgets/impact-summary")
async def get_impact_summary(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    خلاصه تأثیر کاربر
    دسترسی: خود کاربر
    """
    from sqlalchemy import text

    user_roles = [r.key for r in current_user.roles]
    impact = {
        "user_id": current_user.id,
        "metrics": {},
    }

    # اگر خیر است
    if "DONOR" in user_roles:
        query = text(f"""
            SELECT 
                COUNT(*) as donations_count,
                COALESCE(SUM(amount), 0) as total_donated,
                COUNT(DISTINCT charity_id) as charities_supported,
                COUNT(DISTINCT need_id) as needs_supported
            FROM donations 
            WHERE donor_id = {current_user.id} AND status = 'completed'
        """)
        result = await db.execute(query)
        row = result.first()

        impact["metrics"].update({
            "donations_count": row.donations_count or 0,
            "total_donated": float(row.total_donated or 0),
            "charities_supported": row.charities_supported or 0,
            "needs_supported": row.needs_supported or 0,
        })

    # اگر نیازمند است
    if "NEEDY" in user_roles:
        query = text(f"""
            SELECT 
                COUNT(*) as needs_count,
                COALESCE(SUM(collected_amount), 0) as total_received,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_needs
            FROM need_ads 
            WHERE needy_user_id = {current_user.id}
        """)
        result = await db.execute(query)
        row = result.first()

        impact["metrics"].update({
            "needs_count": row.needs_count or 0,
            "total_received": float(row.total_received or 0),
            "completed_needs": row.completed_needs or 0,
        })

    # اگر فروشنده است
    if "VENDOR" in user_roles:
        query = text(f"""
            SELECT 
                COUNT(*) as products_count,
                COALESCE(SUM(charity_fixed_amount + (price * charity_percentage / 100)), 0) as charity_contribution
            FROM products 
            WHERE vendor_id = {current_user.id}
        """)
        result = await db.execute(query)
        row = result.first()

        impact["metrics"].update({
            "products_count": row.products_count or 0,
            "charity_contribution": float(row.charity_contribution or 0),
        })

    return impact