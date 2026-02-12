# app/schemas/charity.py
from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class CharityStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING_VERIFICATION = "pending_verification"


class CharityType(str, Enum):
    NGO = "ngo"
    NON_PROFIT = "non_profit"
    RELIGIOUS = "religious"
    EDUCATIONAL = "educational"
    MEDICAL = "medical"
    COMMUNITY = "community"
    OTHER = "other"


# ---------- ایجاد خیریه ----------
class CharityCreate(BaseModel):
    """ایجاد خیریه جدید"""
    name: str = Field(..., min_length=2, max_length=200)
    description: str = Field(..., min_length=10)
    charity_type: CharityType = CharityType.NGO
    email: EmailStr
    phone: str = Field(..., pattern=r'^\+?[1-9]\d{1,14}$')
    address: str
    website: Optional[str] = None
    registration_number: Optional[str] = None
    logo_url: Optional[str] = None
    manager_id: int  # ID کاربر مدیر

    @validator('website')
    def validate_website(cls, v):
        if v and not v.startswith(('http://', 'https://')):
            v = 'https://' + v
        return v


# ---------- به‌روزرسانی خیریه ----------
class CharityUpdate(BaseModel):
    """ویرایش اطلاعات خیریه"""
    name: Optional[str] = Field(None, min_length=2, max_length=200)
    description: Optional[str] = Field(None, min_length=10)
    charity_type: Optional[CharityType] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, pattern=r'^\+?[1-9]\d{1,14}$')
    address: Optional[str] = None
    website: Optional[str] = None
    logo_url: Optional[str] = None
    active: Optional[bool] = None

    @validator('website')
    def validate_website(cls, v):
        if v and not v.startswith(('http://', 'https://')):
            v = 'https://' + v
        return v


class CharityStatusUpdate(BaseModel):
    """تغییر وضعیت خیریه"""
    status: CharityStatus
    reason: Optional[str] = None


# ---------- تأیید خیریه ----------
class CharityVerification(BaseModel):
    """تأیید یا رد خیریه"""
    verified: bool
    verification_notes: Optional[str] = None


# ---------- خروجی خیریه ----------
class CharityRead(BaseModel):
    """خواندن اطلاعات خیریه"""
    id: int
    uuid: str
    name: str
    description: str
    charity_type: CharityType
    email: EmailStr
    phone: str
    address: str
    website: Optional[str] = None
    registration_number: Optional[str] = None
    logo_url: Optional[str] = None
    verified: bool
    active: bool
    status: CharityStatus
    manager_id: int
    manager_name: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    # آمار
    needs_count: int = 0
    active_needs_count: int = 0
    completed_needs_count: int = 0
    total_donations: float = 0.0
    total_donors: int = 0
    verification_score: float = 0.0

    class Config:
        orm_mode = True


class CharityDetail(CharityRead):
    """جزئیات کامل خیریه"""
    manager_email: Optional[str] = None
    manager_phone: Optional[str] = None
    settings: Dict[str, Any] = {}
    verification_history: List[Dict[str, Any]] = []
    recent_needs: List[Dict[str, Any]] = []
    top_donors: List[Dict[str, Any]] = []

    class Config:
        orm_mode = True


# ---------- فیلتر و جستجو ----------
class CharityFilter(BaseModel):
    """فیلترهای جستجوی خیریه‌ها"""
    charity_type: Optional[CharityType] = None
    status: Optional[CharityStatus] = None
    verified: Optional[bool] = None
    active: Optional[bool] = None
    city: Optional[str] = None
    search_text: Optional[str] = None
    min_needs_count: Optional[int] = None
    max_needs_count: Optional[int] = None
    sort_by: str = "created_at"
    sort_order: str = "desc"


# ---------- مدیر خیریه ----------
class CharityManagerUpdate(BaseModel):
    """تغییر مدیر خیریه"""
    new_manager_id: int
    transfer_notes: Optional[str] = None


# ---------- آمار خیریه ----------
class CharityStats(BaseModel):
    """آمار و گزارش خیریه"""
    charity_id: int
    period_start: datetime
    period_end: datetime

    # آمار کلی
    total_needs: int
    active_needs: int
    completed_needs: int
    pending_needs: int
    rejected_needs: int

    # آمار مالی
    total_donations_amount: float
    average_donation: float
    largest_donation: float
    smallest_donation: float

    # آمار کمک‌کنندگان
    total_donors: int
    new_donors: int
    recurring_donors: int

    # تأییدیه‌ها
    total_verifications_given: int
    total_verifications_received: int
    verification_rating: float

    # فروشگاه
    shop_products_count: int
    shop_revenue_for_charity: float
    shop_orders_count: int

    class Config:
        orm_mode = True


# ---------- دنبال‌کنندگان ----------
class CharityFollower(BaseModel):
    """دنبال‌کننده خیریه"""
    user_id: int
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    followed_at: datetime

    class Config:
        orm_mode = True