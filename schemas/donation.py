# app/schemas/donation.py
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import re


class PaymentMethod(str, Enum):
    DIRECT_TRANSFER = "direct_transfer"  # واریز مستقیم
    COURT = "court"  # پرداخت به دادگاه
    DIGITAL_WALLET = "digital_wallet"  # ولت دیجیتال
    BANK_GATEWAY = "bank_gateway"  # درگاه بانکی
    PRODUCT_SALE = "product_sale"  # فروش محصول


class DonationStatus(str, Enum):
    PENDING = "pending"  # در انتظار پرداخت
    PROCESSING = "processing"  # در حال پردازش
    COMPLETED = "completed"  # تکمیل شده
    FAILED = "failed"  # ناموفق
    REFUNDED = "refunded"  # بازپرداخت شده
    CANCELLED = "cancelled"  # لغو شده


class PaymentStatus(str, Enum):
    PENDING = "pending"  # در انتظار
    PAID = "paid"  # پرداخت شده
    FAILED = "failed"  # ناموفق
    REFUNDED = "refunded"  # بازپرداخت شده


class GatewayType(str, Enum):
    ZARINPAL = "zarinpal"
    IDPAY = "idpay"
    MELLAT = "mellat"
    SADAD = "sadad"
    SAMAN = "saman"
    CUSTOM = "custom"


# ---------- ایجاد کمک ----------
class DonationCreate(BaseModel):
    """ایجاد کمک جدید"""
    amount: float = Field(..., gt=0)
    currency: str = "IRR"
    payment_method: PaymentMethod
    need_id: Optional[int] = None
    charity_id: Optional[int] = None
    product_id: Optional[int] = None

    # اطلاعات پرداخت
    gateway_type: Optional[GatewayType] = None
    return_url: Optional[str] = None  # برای بازگشت از درگاه

    # اطلاعات هدیه (اختیاری)
    dedication_name: Optional[str] = None
    dedication_message: Optional[str] = None
    anonymous: bool = False

    @validator('amount')
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError("Amount must be greater than 0")
        if v > 1000000000:  # 1 میلیارد
            raise ValueError("Amount is too large")
        return v

    @validator('return_url')
    def validate_return_url(cls, v):
        if v and not re.match(r'^https?://', v):
            raise ValueError("Return URL must be a valid HTTP/HTTPS URL")
        return v


# ---------- پرداخت درگاه ----------
class PaymentInitiate(BaseModel):
    """آغاز پرداخت از طریق درگاه"""
    donation_id: int
    gateway_type: GatewayType = GatewayType.ZARINPAL
    return_url: str

    @validator('return_url')
    def validate_return_url(cls, v):
        if not re.match(r'^https?://', v):
            raise ValueError("Return URL must be a valid HTTP/HTTPS URL")
        return v


class PaymentVerify(BaseModel):
    """تأیید پرداخت درگاه"""
    donation_id: int
    authority: str  # کد مرجع پرداخت
    status: str  # وضعیت بازگشتی از درگاه


# ---------- پرداخت مستقیم ----------
class DirectTransferCreate(BaseModel):
    """ثبت پرداخت مستقیم (واریز بانکی)"""
    donation_id: int
    bank_name: str
    account_number: str
    reference_number: str  # شماره پیگیری
    transfer_date: datetime
    receipt_image_url: Optional[str] = None  # عکس فیش واریزی

    @validator('reference_number')
    def validate_reference_number(cls, v):
        if len(v) < 5:
            raise ValueError("Reference number must be at least 5 characters")
        return v


class CourtPaymentCreate(BaseModel):
    """ثبت پرداخت از طریق دادگاه"""
    donation_id: int
    court_name: str
    case_number: str
    payment_date: datetime
    receipt_number: str
    documents: List[Dict[str, Any]] = []  # مدارک ضمیمه


# ---------- به‌روزرسانی کمک ----------
class DonationUpdate(BaseModel):
    """ویرایش اطلاعات کمک"""
    status: Optional[DonationStatus] = None
    transaction_id: Optional[str] = None
    tracking_code: Optional[str] = None
    receipt_number: Optional[str] = None
    notes: Optional[str] = None


class DonationStatusUpdate(BaseModel):
    """تغییر وضعیت کمک"""
    status: DonationStatus
    notes: Optional[str] = None


# ---------- خروجی کمک ----------
class DonationRead(BaseModel):
    """خواندن اطلاعات کمک"""
    id: int
    uuid: str
    amount: float
    currency: str
    payment_method: PaymentMethod
    status: DonationStatus
    payment_status: PaymentStatus

    # اطلاعات مرتبط
    donor_id: int
    donor_name: Optional[str] = None
    need_id: Optional[int] = None
    need_title: Optional[str] = None
    charity_id: Optional[int] = None
    charity_name: Optional[str] = None
    product_id: Optional[int] = None
    product_name: Optional[str] = None

    # اطلاعات پرداخت
    transaction_id: Optional[str] = None
    tracking_code: Optional[str] = None
    receipt_number: Optional[str] = None
    gateway_type: Optional[GatewayType] = None

    # اطلاعات هدیه
    dedication_name: Optional[str] = None
    dedication_message: Optional[str] = None
    anonymous: bool = False

    # زمان‌ها
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class DonationDetail(DonationRead):
    """جزئیات کامل کمک"""
    donor_email: Optional[str] = None
    donor_phone: Optional[str] = None
    donor_ip: Optional[str] = None

    # اطلاعات پرداخت
    payment_details: Dict[str, Any] = {}
    bank_transfer_details: Optional[Dict[str, Any]] = None
    court_payment_details: Optional[Dict[str, Any]] = None

    # لاگ‌ها
    status_history: List[Dict[str, Any]] = []
    audit_logs: List[Dict[str, Any]] = []

    class Config:
        orm_mode = True


# ---------- رسید مالیاتی ----------
class TaxReceipt(BaseModel):
    """رسید مالیاتی برای کمک"""
    receipt_number: str
    donation_id: int
    donor_id: int
    donor_name: str
    donor_national_id: Optional[str] = None
    amount: float
    currency: str
    payment_date: datetime
    charity_id: int
    charity_name: str
    charity_registration_number: Optional[str] = None
    tax_deductible: bool = True
    issued_at: datetime
    issued_by: str

    class Config:
        orm_mode = True


# ---------- فیلتر و جستجو ----------
class DonationFilter(BaseModel):
    """فیلترهای جستجوی کمک‌ها"""
    donor_id: Optional[int] = None
    need_id: Optional[int] = None
    charity_id: Optional[int] = None
    product_id: Optional[int] = None
    status: Optional[DonationStatus] = None
    payment_method: Optional[PaymentMethod] = None
    payment_status: Optional[PaymentStatus] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    search_text: Optional[str] = None
    sort_by: str = "created_at"
    sort_order: str = "desc"


# ---------- گزارش‌ها ----------
class DonationReport(BaseModel):
    """گزارش کمک‌ها"""
    period_start: datetime
    period_end: datetime

    # آمار کلی
    total_donations: int
    total_amount: float
    average_donation: float

    # بر اساس روش پرداخت
    by_payment_method: Dict[str, Dict[str, Any]]

    # بر اساس وضعیت
    by_status: Dict[str, int]

    # بر اساس خیریه
    by_charity: List[Dict[str, Any]]

    # بر اساس نیاز
    by_need: List[Dict[str, Any]]

    # روند زمانی
    daily_trend: List[Dict[str, Any]]

    class Config:
        orm_mode = True


# ---------- تعهد دوره‌ای ----------
class RecurringDonationCreate(BaseModel):
    """ایجاد تعهد کمک دوره‌ای"""
    amount: float = Field(..., gt=0)
    currency: str = "IRR"
    frequency: str = Field(..., pattern="^(daily|weekly|monthly|quarterly|yearly)$")
    start_date: datetime
    end_date: Optional[datetime] = None
    max_occurrences: Optional[int] = None
    need_id: Optional[int] = None
    charity_id: Optional[int] = None
    payment_method: PaymentMethod
    gateway_type: Optional[GatewayType] = None

    @validator('amount')
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError("Amount must be greater than 0")
        return v

    @validator('end_date')
    def validate_dates(cls, v, values):
        if v and 'start_date' in values and v <= values['start_date']:
            raise ValueError("End date must be after start date")
        return v


class RecurringDonationUpdate(BaseModel):
    """ویرایش تعهد دوره‌ای"""
    active: Optional[bool] = None
    amount: Optional[float] = None
    frequency: Optional[str] = None
    end_date: Optional[datetime] = None
    notes: Optional[str] = None


# ---------- درگاه پرداخت ----------
class GatewayConfig(BaseModel):
    """تنظیمات درگاه پرداخت"""
    gateway_type: GatewayType
    merchant_id: str
    api_key: Optional[str] = None
    sandbox: bool = True  # حالت تست
    callback_url: str
    enabled: bool = True
    settings: Dict[str, Any] = {}


class GatewayResponse(BaseModel):
    """پاسخ درگاه پرداخت"""
    success: bool
    authority: Optional[str] = None  # کد مرجع
    payment_url: Optional[str] = None  # آدرس پرداخت
    message: Optional[str] = None
    error_code: Optional[str] = None


# ---------- سبد خرید ----------
class CartItem(BaseModel):
    """آیتم سبد خرید"""
    product_id: int
    quantity: int = Field(..., ge=1)
    donation_amount: Optional[float] = None  # مبلغ کمک اضافی

    @validator('quantity')
    def validate_quantity(cls, v):
        if v < 1:
            raise ValueError("Quantity must be at least 1")
        if v > 100:
            raise ValueError("Quantity cannot exceed 100")
        return v


class CartCreate(BaseModel):
    """ایجاد سبد خرید"""
    items: List[CartItem]
    charity_id: Optional[int] = None  # اگر مستقیماً به خیریه کمک می‌کند
    need_id: Optional[int] = None  # اگر به نیاز خاصی کمک می‌کند
    notes: Optional[str] = None


class CartRead(BaseModel):
    """خواندن سبد خرید"""
    cart_id: str
    items: List[Dict[str, Any]]
    subtotal: float
    charity_amount: float  # مبلغ کل اختصاص‌یافته به خیریه
    total: float
    currency: str = "IRR"
    created_at: datetime
    expires_at: datetime

    class Config:
        orm_mode = True