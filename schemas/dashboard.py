# app/schemas/dashboard.py
from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from datetime import datetime
from enum import Enum


# --------------------------
# 1️⃣ آمار کلی برای ادمین
# --------------------------
class DashboardStats(BaseModel):
    total_products: int
    total_charity_generated: float
    total_users: int
    total_shops: int
    total_charities: int
    total_donations: float
    total_needs: int
    completed_needs: int
    pending_verifications: int

    class Config:
        orm_mode = True


class AdminDashboard(BaseModel):
    """داشبورد کامل ادمین"""
    summary: DashboardStats
    recent_donations: List[Dict[str, Any]]
    recent_needs: List[Dict[str, Any]]
    recent_users: List[Dict[str, Any]]
    pending_charities: List[Dict[str, Any]]
    pending_verifications: int
    system_health: Dict[str, Any]
    alerts: List[Dict[str, Any]]

    class Config:
        orm_mode = True


class SuperAdminDashboard(AdminDashboard):
    """داشبورد سوپر ادمین با آمار بیشتر"""
    system_metrics: Dict[str, Any]
    admin_activities: List[Dict[str, Any]]
    audit_logs_summary: Dict[str, int]
    performance_metrics: Dict[str, float]

    class Config:
        orm_mode = True


# --------------------------
# 2️⃣ محصول برای فروشنده / ادمین
# --------------------------
class ProductSummary(BaseModel):
    id: int
    name: str
    price: float
    currency: str
    charity_percentage: float
    charity_fixed_amount: float
    status: str
    stock_quantity: int
    shop_id: Optional[int]
    vendor_id: int
    sales_count: int = 0
    total_revenue: float = 0.0
    charity_generated: float = 0.0

    class Config:
        orm_mode = True


class VendorDashboard(BaseModel):
    vendor_id: int
    vendor_name: Optional[str]
    total_products: int
    total_sales: int
    total_revenue: float
    total_charity_generated: float
    products: Optional[List[ProductSummary]] = []
    recent_orders: List[Dict[str, Any]] = []
    monthly_stats: Dict[str, Any] = {}

    class Config:
        orm_mode = True


# --------------------------
# 3️⃣ داشبورد مدیر خیریه
# --------------------------
class CharityManagerItem(BaseModel):
    charity_id: int
    name: str
    total_ads: int
    total_products: int
    total_donations: float
    active_needs: int
    completed_needs: int
    verification_rate: float
    last_activity: Optional[datetime]

    class Config:
        orm_mode = True


class CharityManagerDashboard(BaseModel):
    charities: List[CharityManagerItem]
    total_charities: int
    total_donations_all: float
    total_needs_all: int
    pending_approvals: int

    class Config:
        orm_mode = True


# --------------------------
# 4️⃣ داشبورد خیریه
# --------------------------
class CharityDashboard(BaseModel):
    charity_id: int
    name: str
    logo_url: Optional[str]
    ads_count: int
    active_ads: int
    completed_ads: int
    products_count: int
    donations_total: float
    donations_count: int
    donors_count: int
    followers_count: int
    verification_score: float
    recent_donations: List[Dict[str, Any]]
    popular_needs: List[Dict[str, Any]]

    class Config:
        orm_mode = True


class CharityDetailedStats(BaseModel):
    """آمار پیشرفته خیریه"""
    charity_id: int
    period_start: datetime
    period_end: datetime

    # آمار روزانه
    daily_donations: List[Dict[str, Any]]
    daily_needs: List[Dict[str, Any]]

    # تحلیل
    donation_growth: float
    needs_completion_rate: float
    donor_retention_rate: float
    average_donation_trend: List[float]

    # پیش‌بینی
    projected_donations: float
    projected_needs: int

    class Config:
        orm_mode = True


# --------------------------
# 5️⃣ داشبورد نیازمند
# --------------------------
class NeedyAdItem(BaseModel):
    id: int
    title: str
    description: Optional[str]
    target_amount: float
    collected_amount: float
    progress: float
    status: str
    verified: bool
    created_at: datetime
    charity_name: Optional[str]
    days_remaining: Optional[int]

    class Config:
        orm_mode = True


class NeedyDashboard(BaseModel):
    user_id: int
    user_name: Optional[str]
    total_ads: int
    verified_ads: int
    pending_ads: int
    completed_ads: int
    rejected_ads: int
    total_requested: float
    total_received: float
    ads: List[NeedyAdItem]
    recent_activities: List[Dict[str, Any]]

    class Config:
        orm_mode = True


# --------------------------
# 6️⃣ داشبورد خیر کمک‌کننده
# --------------------------
class DonationItem(BaseModel):
    id: int
    amount: float
    product_id: Optional[int]
    product_name: Optional[str]
    charity_id: Optional[int]
    charity_name: Optional[str]
    need_id: Optional[int]
    need_title: Optional[str]
    created_at: datetime
    status: str
    receipt_number: Optional[str]

    class Config:
        orm_mode = True


class DonorDashboard(BaseModel):
    user_id: int
    user_name: Optional[str]
    total_donated: float
    total_donations_count: int
    average_donation: float
    largest_donation: float
    first_donation_date: Optional[datetime]
    last_donation_date: Optional[datetime]
    donations: List[DonationItem]
    favorite_charities: List[Dict[str, Any]]
    monthly_donations: Dict[str, float]
    impact_summary: Dict[str, Any]

    class Config:
        orm_mode = True


# --------------------------
# 7️⃣ داشبورد فروشگاه
# --------------------------
class ShopProductSummary(BaseModel):
    product_id: int
    name: str
    price: float
    sales_count: int
    revenue: float
    charity_generated: float

    class Config:
        orm_mode = True


class ShopManagerDashboard(BaseModel):
    shop_id: int
    shop_name: str
    total_products: int
    active_products: int
    total_vendors: int
    total_sales: int
    total_revenue: float
    total_charity_generated: float
    products: List[ShopProductSummary]
    top_vendors: List[Dict[str, Any]]
    daily_sales: List[Dict[str, Any]]
    recent_orders: List[Dict[str, Any]]

    class Config:
        orm_mode = True


# --------------------------
# 8️⃣ داشبورد داوطلب
# --------------------------
class VolunteerTask(BaseModel):
    task_id: int
    task_type: str
    description: str
    assigned_at: datetime
    completed_at: Optional[datetime]
    status: str
    need_id: Optional[int]
    need_title: Optional[str]
    charity_id: Optional[int]
    charity_name: Optional[str]

    class Config:
        orm_mode = True


class VolunteerDashboard(BaseModel):
    user_id: int
    user_name: str
    total_tasks: int
    completed_tasks: int
    pending_tasks: int
    tasks: List[VolunteerTask]
    impact_hours: int
    charities_helped: int
    needs_helped: int
    recent_activities: List[Dict[str, Any]]

    class Config:
        orm_mode = True


# --------------------------
# 9️⃣ آمار و تحلیل
# --------------------------
class GeographicalStats(BaseModel):
    """آمار جغرافیایی"""
    by_province: List[Dict[str, Any]]
    by_city: List[Dict[str, Any]]
    donation_map: List[Dict[str, Any]]
    need_map: List[Dict[str, Any]]

    class Config:
        orm_mode = True


class TemporalStats(BaseModel):
    """آمار زمانی"""
    by_hour: List[Dict[str, Any]]
    by_day: List[Dict[str, Any]]
    by_month: List[Dict[str, Any]]
    by_year: List[Dict[str, Any]]
    growth_rate: float
    peak_hours: List[int]
    seasonal_patterns: Dict[str, Any]

    class Config:
        orm_mode = True


class ProductSalesStats(BaseModel):
    """آمار فروش محصولات"""
    total_products_sold: int
    total_revenue: float
    total_charity_generated: float
    top_selling_products: List[Dict[str, Any]]
    top_charity_products: List[Dict[str, Any]]
    by_category: Dict[str, Any]

    class Config:
        orm_mode = True


# --------------------------
# 🔟 پروفایل پیشرفته
# --------------------------
class UserProfileStats(BaseModel):
    user_id: int
    user_type: str
    member_since: datetime

    # کمک‌ها (برای DONOR)
    total_donated: Optional[float] = 0
    donations_count: Optional[int] = 0

    # نیازها (برای NEEDY)
    total_needs: Optional[int] = 0
    fulfilled_needs: Optional[int] = 0

    # فروش (برای VENDOR)
    total_products_sold: Optional[int] = 0
    total_sales: Optional[float] = 0
    charity_contribution: Optional[float] = 0

    # فعالیت داوطلبانه
    volunteer_hours: Optional[int] = 0
    completed_tasks: Optional[int] = 0

    class Config:
        orm_mode = True


class UserProfileAdvanced(BaseModel):
    """پروفایل پیشرفته کاربر"""
    basic_info: Dict[str, Any]
    stats: UserProfileStats
    timeline: List[Dict[str, Any]]
    badges: List[str]
    certificates: List[Dict[str, Any]]
    achievements: List[str]

    class Config:
        orm_mode = True