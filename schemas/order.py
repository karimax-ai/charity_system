# app/schemas/order.py
from pydantic import BaseModel, Field, validator, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import re


class OrderStatus(str, Enum):
    PENDING = "pending"  # در انتظار پرداخت
    CONFIRMED = "confirmed"  # تأیید شده
    PROCESSING = "processing"  # در حال آماده‌سازی
    SHIPPED = "shipped"  # ارسال شده
    DELIVERED = "delivered"  # تحویل داده شده
    CANCELLED = "cancelled"  # لغو شده
    REFUNDED = "refunded"  # بازپرداخت شده


class PaymentStatus(str, Enum):
    PENDING = "pending"  # در انتظار پرداخت
    PAID = "paid"  # پرداخت شده
    FAILED = "failed"  # پرداخت ناموفق
    REFUNDED = "refunded"  # بازپرداخت شده
    PARTIALLY_REFUNDED = "partially_refunded"  # بازپرداخت جزئی


class ShippingMethod(str, Enum):
    STANDARD = "standard"  # پست معمولی
    EXPRESS = "express"  # پست پیشتاز
    COURIER = "courier"  # پیک موتوری
    STORE_PICKUP = "store_pickup"  # تحویل در فروشگاه


class CartStatus(str, Enum):
    ACTIVE = "active"  # فعال
    ABANDONED = "abandoned"  # رها شده
    CONVERTED = "converted"  # تبدیل به سفارش
    EXPIRED = "expired"  # منقضی شده


# ---------- آیتم سبد خرید ----------
class CartItemCreate(BaseModel):
    """ایجاد آیتم در سبد خرید"""
    product_id: int
    quantity: int = Field(..., ge=1, le=100)
    donation_amount: Optional[float] = Field(None, ge=0)

    @validator('quantity')
    def validate_quantity(cls, v):
        if v < 1:
            raise ValueError("Quantity must be at least 1")
        return v


class CartItemUpdate(BaseModel):
    """ویرایش آیتم سبد خرید"""
    quantity: Optional[int] = Field(None, ge=1, le=100)
    donation_amount: Optional[float] = Field(None, ge=0)


class CartItemRead(BaseModel):
    """خواندن آیتم سبد خرید"""
    id: int
    product_id: int
    product_name: str
    product_price: float
    quantity: int
    subtotal: float
    charity_amount: float
    donation_amount: float = 0
    total: float
    image_url: Optional[str] = None

    class Config:
        orm_mode = True


# ---------- سبد خرید ----------
class CartCreate(BaseModel):
    """ایجاد سبد خرید"""
    items: List[CartItemCreate] = []
    charity_id: Optional[int] = None
    need_id: Optional[int] = None
    notes: Optional[str] = None


class CartUpdate(BaseModel):
    """ویرایش سبد خرید"""
    charity_id: Optional[int] = None
    need_id: Optional[int] = None
    notes: Optional[str] = None


class CartRead(BaseModel):
    """خواندن سبد خرید"""
    cart_id: str
    user_id: int
    items: List[CartItemRead]
    item_count: int
    subtotal: float
    total_charity: float  # مجموع مبلغ خیریه از محصولات
    total_donation: float = 0  # مجموع کمک‌های مستقیم
    shipping_cost: float = 0
    tax_amount: float = 0
    discount_amount: float = 0
    grand_total: float
    currency: str = "IRR"
    status: CartStatus
    charity_id: Optional[int] = None
    charity_name: Optional[str] = None
    need_id: Optional[int] = None
    need_title: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime

    class Config:
        orm_mode = True


# ---------- ایجاد سفارش ----------
class OrderCreate(BaseModel):
    """ایجاد سفارش جدید از سبد خرید"""
    cart_id: str
    shipping_method: ShippingMethod = ShippingMethod.STANDARD
    payment_method: str  # از درگاه پرداخت یا ...

    # اطلاعات مشتری (اگر متفاوت از کاربر واردکننده است)
    customer_name: Optional[str] = None
    customer_email: Optional[EmailStr] = None
    customer_phone: Optional[str] = None

    # آدرس ارسال
    shipping_address: str
    shipping_city: str
    shipping_province: str
    shipping_postal_code: Optional[str] = None
    shipping_notes: Optional[str] = None

    # صورتحساب (اگر متفاوت است)
    billing_same_as_shipping: bool = True
    billing_address: Optional[str] = None
    billing_city: Optional[str] = None
    billing_province: Optional[str] = None

    @validator('customer_phone')
    def validate_phone(cls, v):
        if v and not re.match(r'^\+?[1-9]\d{1,14}$', v):
            raise ValueError("Invalid phone number format")
        return v

    @validator('shipping_postal_code')
    def validate_postal_code(cls, v):
        if v and not re.match(r'^\d{10}$', v):
            raise ValueError("Postal code must be 10 digits")
        return v


# ---------- ویرایش سفارش ----------
class OrderUpdate(BaseModel):
    """ویرایش سفارش (ادمین/مدیر)"""
    status: Optional[OrderStatus] = None
    shipping_method: Optional[ShippingMethod] = None
    shipping_tracking_code: Optional[str] = None
    shipping_carrier: Optional[str] = None
    shipping_notes: Optional[str] = None
    internal_notes: Optional[str] = None


class OrderStatusUpdate(BaseModel):
    """تغییر وضعیت سفارش"""
    status: OrderStatus
    notes: Optional[str] = None


class PaymentStatusUpdate(BaseModel):
    """تغییر وضعیت پرداخت"""
    status: PaymentStatus
    transaction_id: Optional[str] = None
    notes: Optional[str] = None


# ---------- خواندن سفارش ----------
class OrderItemRead(BaseModel):
    """خواندن آیتم سفارش"""
    id: int
    product_id: int
    product_name: str
    product_sku: Optional[str] = None
    unit_price: float
    quantity: int
    subtotal: float
    charity_percentage: float
    charity_fixed_amount: float
    charity_total: float
    image_url: Optional[str] = None

    class Config:
        orm_mode = True


class OrderRead(BaseModel):
    """خواندن سفارش"""
    id: int
    uuid: str
    order_number: str
    status: OrderStatus
    payment_status: PaymentStatus

    # اطلاعات مالی
    subtotal: float
    shipping_cost: float
    tax_amount: float
    discount_amount: float
    charity_amount: float  # کل مبلغ اختصاص‌یافته به خیریه
    grand_total: float
    currency: str = "IRR"

    # اطلاعات مشتری
    customer_id: Optional[int] = None
    customer_name: str
    customer_email: str
    customer_phone: Optional[str] = None

    # اطلاعات ارسال
    shipping_method: ShippingMethod
    shipping_address: str
    shipping_city: str
    shipping_province: str
    shipping_postal_code: Optional[str] = None
    shipping_tracking_code: Optional[str] = None
    shipping_carrier: Optional[str] = None
    shipping_notes: Optional[str] = None

    # اطلاعات صورتحساب
    billing_address: Optional[str] = None
    billing_city: Optional[str] = None
    billing_province: Optional[str] = None

    # اطلاعات مرتبط
    charity_id: Optional[int] = None
    charity_name: Optional[str] = None
    need_id: Optional[int] = None
    need_title: Optional[str] = None

    # زمان‌ها
    created_at: datetime
    updated_at: datetime
    paid_at: Optional[datetime] = None
    shipped_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class OrderDetail(OrderRead):
    """جزئیات کامل سفارش"""
    items: List[OrderItemRead] = []
    payment_method: str
    transaction_id: Optional[str] = None
    payment_details: Dict[str, Any] = {}
    internal_notes: Optional[str] = None
    customer_notes: Optional[str] = None

    # تاریخچه وضعیت
    status_history: List[Dict[str, Any]] = []
    payment_history: List[Dict[str, Any]] = []

    class Config:
        orm_mode = True


# ---------- فیلتر و جستجو ----------
class OrderFilter(BaseModel):
    """فیلترهای جستجوی سفارشات"""
    customer_id: Optional[int] = None
    status: Optional[OrderStatus] = None
    payment_status: Optional[PaymentStatus] = None
    shipping_method: Optional[ShippingMethod] = None
    charity_id: Optional[int] = None
    need_id: Optional[int] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    search_text: Optional[str] = None  # شماره سفارش، نام مشتری، etc.
    sort_by: str = "created_at"
    sort_order: str = "desc"


# ---------- گزارش‌های سفارش ----------
class OrderStats(BaseModel):
    """آمار سفارشات"""
    period_start: datetime
    period_end: datetime

    # آمار کلی
    total_orders: int
    total_revenue: float
    average_order_value: float
    conversion_rate: float  # نرخ تبدیل سبد به سفارش

    # بر اساس وضعیت
    by_status: Dict[str, int]

    # بر اساس روش ارسال
    by_shipping_method: Dict[str, int]

    # بر اساس وضعیت پرداخت
    by_payment_status: Dict[str, int]

    # بر اساس خیریه
    by_charity: List[Dict[str, Any]]

    # روند زمانی
    daily_orders: List[Dict[str, Any]]

    class Config:
        orm_mode = True


# ---------- مدیریت موجودی ----------
class InventoryUpdate(BaseModel):
    """به‌روزرسانی موجودی محصول"""
    product_id: int
    adjustment: int  # مثبت برای افزایش، منفی برای کاهش
    reason: str  # سفارش، برگشت، تعدیل فیزیکی، etc.
    notes: Optional[str] = None

    @validator('adjustment')
    def validate_adjustment(cls, v):
        if v == 0:
            raise ValueError("Adjustment cannot be zero")
        return v


class InventoryHistory(BaseModel):
    """تاریخچه موجودی"""
    id: int
    product_id: int
    product_name: str
    previous_quantity: int
    new_quantity: int
    adjustment: int
    reason: str
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    created_at: datetime

    class Config:
        orm_mode = True


# ---------- برگشت کالا ----------
class ReturnRequestCreate(BaseModel):
    """درخواست برگشت کالا"""
    order_id: int
    items: List[Dict[str, Any]]  # لیست آیتم‌های برگشتی
    reason: str
    description: Optional[str] = None
    refund_amount: Optional[float] = None
    preferred_method: str = "refund"  # refund, exchange, credit


class ReturnRequestUpdate(BaseModel):
    """ویرایش درخواست برگشت"""
    status: Optional[str] = None  # pending, approved, rejected, processed
    admin_notes: Optional[str] = None
    refund_amount: Optional[float] = None
    refund_method: Optional[str] = None


# ---------- تخفیف و کوپن ----------
class CouponCreate(BaseModel):
    """ایجاد کد تخفیف"""
    code: str
    discount_type: str = "percentage"  # percentage, fixed
    discount_value: float
    min_order_amount: Optional[float] = None
    max_discount: Optional[float] = None
    usage_limit: Optional[int] = None
    valid_from: datetime
    valid_until: Optional[datetime] = None
    charity_id: Optional[int] = None  # اگر کوپن مخصوص خیریه است
    products: List[int] = []  # محصولات مجاز

    @validator('code')
    def validate_code(cls, v):
        if len(v) < 4:
            raise ValueError("Coupon code must be at least 4 characters")
        return v.upper()

    @validator('discount_value')
    def validate_discount(cls, v, values):
        if 'discount_type' in values and values['discount_type'] == "percentage":
            if v <= 0 or v > 100:
                raise ValueError("Percentage discount must be between 0 and 100")
        return v


class CouponValidate(BaseModel):
    """اعتبارسنجی کد تخفیف"""
    code: str
    cart_id: str
    customer_id: Optional[int] = None


# ---------- تنظیمات فروشگاه ----------
class ShopSettings(BaseModel):
    """تنظیمات فروشگاه"""
    currency: str = "IRR"
    tax_rate: float = 0.09  # 9% مالیات بر ارزش افزوده
    shipping_cost_standard: float = 30000
    shipping_cost_express: float = 60000
    shipping_cost_courier: float = 15000
    free_shipping_threshold: Optional[float] = 500000
    low_stock_threshold: int = 10
    cart_expiry_minutes: int = 1440  # 24 ساعت
    order_confirmation_email: bool = True
    order_shipped_email: bool = True
    order_delivered_email: bool = True
    return_policy_days: int = 7

    class Config:
        orm_mode = True