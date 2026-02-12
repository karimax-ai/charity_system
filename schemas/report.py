# app/schemas/report.py
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, date
from enum import Enum


class ReportType(str, Enum):
    """نوع گزارش"""
    SALES = "sales"  # فروش
    DONATIONS = "donations"  # کمک‌ها
    NEEDS = "needs"  # نیازها
    PRODUCTS = "products"  # محصولات
    CHARITIES = "charities"  # خیریه‌ها
    USERS = "users"  # کاربران
    FINANCIAL = "financial"  # مالی
    INVENTORY = "inventory"  # موجودی
    COUPONS = "coupons"  # تخفیف‌ها


class ReportFormat(str, Enum):
    """فرمت خروجی"""
    JSON = "json"
    CSV = "csv"
    EXCEL = "excel"
    PDF = "pdf"


class ReportPeriod(str, Enum):
    """دوره زمانی"""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    CUSTOM = "custom"


class DateRange(BaseModel):
    """بازه زمانی"""
    start_date: datetime
    end_date: datetime


class ReportFilter(BaseModel):
    """فیلترهای گزارش"""
    date_range: Optional[DateRange] = None
    period: Optional[ReportPeriod] = None
    charity_id: Optional[int] = None
    need_id: Optional[int] = None
    vendor_id: Optional[int] = None
    category: Optional[str] = None
    status: Optional[List[str]] = None
    province: Optional[str] = None
    city: Optional[str] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    search_text: Optional[str] = None


class ReportRequest(BaseModel):
    """درخواست گزارش"""
    report_type: ReportType
    format: ReportFormat = ReportFormat.JSON
    filters: ReportFilter
    title: Optional[str] = None
    description: Optional[str] = None
    include_charts: bool = False
    group_by: Optional[str] = None  # day, week, month, year, charity, category
    sort_by: str = "date"
    sort_order: str = "desc"
    limit: Optional[int] = None


# ---------- Sales Report ----------
class SalesSummary(BaseModel):
    """خلاصه فروش"""
    total_orders: int
    total_revenue: float
    average_order_value: float
    total_items_sold: int
    total_charity_amount: float
    charity_percentage: float
    unique_customers: int
    completed_orders: int
    cancelled_orders: int


class SalesByPeriod(BaseModel):
    """فروش بر اساس دوره"""
    period: str
    order_count: int
    revenue: float
    items_sold: int
    charity_amount: float


class SalesByProduct(BaseModel):
    """فروش بر اساس محصول"""
    product_id: int
    product_name: str
    category: Optional[str]
    vendor_id: int
    vendor_name: Optional[str]
    quantity_sold: int
    revenue: float
    charity_amount: float
    avg_price: float


class SalesByCharity(BaseModel):
    """فروش بر اساس خیریه"""
    charity_id: int
    charity_name: str
    order_count: int
    revenue: float
    charity_amount: float
    charity_percentage: float


class SalesReport(BaseModel):
    """گزارش فروش کامل"""
    summary: SalesSummary
    daily_stats: List[SalesByPeriod]
    monthly_stats: List[SalesByPeriod]
    by_product: List[SalesByProduct]
    by_charity: List[SalesByCharity]
    by_category: Dict[str, Any]
    by_region: Dict[str, Any]
    generated_at: datetime


# ---------- Donations Report ----------
class DonationsSummary(BaseModel):
    """خلاصه کمک‌ها"""
    total_donations: int
    total_amount: float
    average_donation: float
    largest_donation: float
    smallest_donation: float
    unique_donors: int
    completed_donations: int
    pending_donations: int


class DonationsByPeriod(BaseModel):
    """کمک‌ها بر اساس دوره"""
    period: str
    donation_count: int
    total_amount: float
    average_amount: float


class DonationsByCharity(BaseModel):
    """کمک‌ها بر اساس خیریه"""
    charity_id: int
    charity_name: str
    donation_count: int
    total_amount: float
    average_amount: float


class DonationsByNeed(BaseModel):
    """کمک‌ها بر اساس نیاز"""
    need_id: int
    need_title: str
    charity_name: str
    donation_count: int
    total_amount: float
    progress: float  # درصد تکمیل


class DonationsReport(BaseModel):
    """گزارش کمک‌ها"""
    summary: DonationsSummary
    daily_stats: List[DonationsByPeriod]
    monthly_stats: List[DonationsByPeriod]
    by_charity: List[DonationsByCharity]
    by_need: List[DonationsByNeed]
    by_payment_method: Dict[str, Any]
    generated_at: datetime


# ---------- Needs Report ----------
class NeedsSummary(BaseModel):
    """خلاصه نیازها"""
    total_needs: int
    active_needs: int
    completed_needs: int
    pending_needs: int
    total_target: float
    total_collected: float
    overall_progress: float
    urgent_needs: int
    emergency_needs: int


class NeedsByCategory(BaseModel):
    """نیازها بر اساس دسته‌بندی"""
    category: str
    count: int
    target_amount: float
    collected_amount: float
    progress: float


class NeedsByCharity(BaseModel):
    """نیازها بر اساس خیریه"""
    charity_id: int
    charity_name: str
    total_needs: int
    active_needs: int
    completed_needs: int
    total_target: float
    total_collected: float
    success_rate: float


class NeedsReport(BaseModel):
    """گزارش نیازها"""
    summary: NeedsSummary
    by_category: List[NeedsByCategory]
    by_charity: List[NeedsByCharity]
    by_status: Dict[str, int]
    by_urgency: Dict[str, int]
    monthly_trend: List[Dict[str, Any]]
    generated_at: datetime


# ---------- Products Report ----------
class ProductsSummary(BaseModel):
    """خلاصه محصولات"""
    total_products: int
    active_products: int
    draft_products: int
    sold_out_products: int
    total_inventory_value: float
    avg_price: float
    total_charity_potential: float


class ProductsByVendor(BaseModel):
    """محصولات بر اساس فروشنده"""
    vendor_id: int
    vendor_name: str
    products_count: int
    active_products: int
    total_value: float
    charity_potential: float


class ProductsPerformance(BaseModel):
    """عملکرد محصولات"""
    product_id: int
    product_name: str
    category: str
    vendor_name: str
    price: float
    stock_quantity: int
    sales_count: int
    revenue: float
    charity_generated: float
    conversion_rate: float


class ProductsReport(BaseModel):
    """گزارش محصولات"""
    summary: ProductsSummary
    by_vendor: List[ProductsByVendor]
    by_category: Dict[str, Any]
    top_selling: List[ProductsPerformance]
    low_stock: List[Dict[str, Any]]
    charity_impact: List[Dict[str, Any]]
    generated_at: datetime


# ---------- Financial Report ----------
class FinancialSummary(BaseModel):
    """خلاصه مالی"""
    total_revenue: float
    total_charity: float
    total_tax: float
    total_shipping: float
    total_discount: float
    net_revenue: float
    charity_percentage: float
    order_count: int


class IncomeStatement(BaseModel):
    """صورت سود و زیان"""
    period: str
    revenue: float
    cost_of_goods: float
    gross_profit: float
    operating_expenses: float
    net_profit: float
    charity_contributions: float
    tax_amount: float


class CharityFinancials(BaseModel):
    """مالی خیریه"""
    charity_id: int
    charity_name: str
    total_received: float
    from_donations: float
    from_products: float
    order_count: int
    donor_count: int


class FinancialReport(BaseModel):
    """گزارش مالی"""
    summary: FinancialSummary
    income_statement: List[IncomeStatement]
    by_charity: List[CharityFinancials]
    monthly_revenue: List[Dict[str, Any]]
    by_payment_method: Dict[str, float]
    generated_at: datetime


# ---------- Export ----------
class ExportTask(BaseModel):
    """وظیفه خروجی"""
    task_id: str
    report_type: ReportType
    format: ReportFormat
    status: str  # pending, processing, completed, failed
    created_at: datetime
    completed_at: Optional[datetime]
    file_url: Optional[str]
    error: Optional[str]


class ExportResponse(BaseModel):
    """پاسخ خروجی"""
    success: bool
    task_id: Optional[str]
    message: str
    file_url: Optional[str]
    download_url: Optional[str]