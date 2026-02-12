# app/schemas/need_ad.py
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import uuid


class NeedCategory(str, Enum):
    MEDICAL = "medical"
    EDUCATION = "education"
    HOUSING = "housing"
    FOOD = "food"
    CLOTHING = "clothing"
    DEBT = "debt"
    OTHER = "other"
    EMERGENCY = "emergency"
    NATURAL_DISASTER = "natural_disaster"


class NeedStatus(str, Enum):
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PrivacyLevel(str, Enum):
    PUBLIC = "public"
    PROTECTED = "protected"
    PRIVATE = "private"


class EmergencyType(str, Enum):
    EARTHQUAKE = "earthquake"
    FLOOD = "flood"
    FIRE = "fire"
    ACCIDENT = "accident"
    STORM = "storm"
    DROUGHT = "drought"
    WAR = "war"
    PANDEMIC = "pandemic"
    OTHER = "other"


class EmergencySeverity(str, Enum):
    CRITICAL = "critical"
    SEVERE = "severe"
    MODERATE = "moderate"
    LOW = "low"


class BadgeLevel(str, Enum):
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"


class ProgressBarStyle(str, Enum):
    CIRCULAR = "circular"
    LINEAR = "linear"


class CampaignType(str, Enum):
    NORMAL = "normal"
    MATCHING = "matching"
    URGENT = "urgent"


# ---------- مراحل Wizard ----------
class Step1BasicInfo(BaseModel):
    """مرحله ۱: اطلاعات پایه"""
    title: str = Field(..., min_length=5, max_length=200)
    short_description: str = Field(..., max_length=500)
    category: NeedCategory
    is_urgent: bool = False
    is_emergency: bool = False
    emergency_type: Optional[EmergencyType] = None


class Step2FinancialInfo(BaseModel):
    """مرحله ۲: اطلاعات مالی"""
    target_amount: float = Field(..., gt=0)
    currency: str = "IRR"
    deadline: Optional[datetime] = None
    is_campaign: bool = False
    campaign_end: Optional[datetime] = None
    campaign_goal: Optional[float] = None
    campaign_type: Optional[CampaignType] = CampaignType.NORMAL
    matching_ratio: Optional[float] = Field(None, ge=0, le=1)


class Step3LocationInfo(BaseModel):
    """مرحله ۳: موقعیت جغرافیایی"""
    city: str
    province: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    # برای بحران
    affected_area: Optional[str] = None
    radius_km: Optional[float] = None


class Step4Details(BaseModel):
    """مرحله ۴: جزئیات کامل"""
    description: str = Field(..., min_length=10)
    privacy_level: PrivacyLevel = PrivacyLevel.PROTECTED
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    # تنظیمات نمایش
    progress_bar_style: ProgressBarStyle = ProgressBarStyle.CIRCULAR
    show_percentage: bool = True
    show_collected: bool = True
    show_remaining: bool = True


class Step5Attachments(BaseModel):
    """مرحله ۵: فایل‌های ضمیمه"""
    attachments: List[Dict[str, Any]] = []  # لیست فایل‌ها
    accept_terms: bool = Field(..., description="Must accept terms")


# ---------- اطلاعات بحران ----------
class EmergencyInfo(BaseModel):
    """اطلاعات بحران/فوریت"""
    emergency_type: EmergencyType
    severity: EmergencySeverity = EmergencySeverity.MODERATE
    affected_area: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    radius_km: Optional[float] = None
    estimated_affected_people: Optional[int] = None
    estimated_damage_cost: Optional[float] = None
    government_reference_number: Optional[str] = None
    declared_by: Optional[str] = None
    occurred_at: datetime
    media_attachments: List[Dict[str, Any]] = []
    news_links: List[str] = []
    notify_all_users: bool = True
    notify_sms: bool = True
    notify_email: bool = True
    notify_push: bool = True


# ---------- اطلاعات تأییدیه ----------
class VerifiedByInfo(BaseModel):
    """اطلاعات تأییدکننده با نشان"""
    charity_id: int
    charity_name: str
    charity_logo: Optional[str] = None
    verified_at: datetime
    badge_url: Optional[str] = None
    comment: Optional[str] = None


# ---------- اطلاعات کمپین ----------
class CampaignSettings(BaseModel):
    """تنظیمات کمپین زمان‌دار"""
    is_campaign: bool = False
    campaign_start: Optional[datetime] = None
    campaign_end: Optional[datetime] = None
    campaign_goal: Optional[float] = None
    campaign_type: CampaignType = CampaignType.NORMAL
    matching_donor: Optional[str] = None
    matching_ratio: float = 0
    badge_text: Optional[str] = None
    collected_in_campaign: float = 0
    donors_count: int = 0


# ---------- اطلاعات اشتراک‌گذاری ----------
class SocialSharing(BaseModel):
    """آمار اشتراک‌گذاری اجتماعی"""
    share_count: int = 0
    telegram: int = 0
    whatsapp: int = 0
    twitter: int = 0
    facebook: int = 0
    linkedin: int = 0


# ---------- ایجاد کامل نیاز ----------
class NeedAdCreate(BaseModel):
    """ایجاد نیاز جدید (یکجا)"""
    title: str
    short_description: str
    description: str
    category: NeedCategory
    target_amount: float
    currency: str = "IRR"
    city: str
    province: str
    privacy_level: PrivacyLevel = PrivacyLevel.PROTECTED
    is_urgent: bool = False
    is_emergency: bool = False
    emergency_type: Optional[EmergencyType] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    deadline: Optional[datetime] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    attachments: List[Dict[str, Any]] = []
    charity_id: int

    # ✅ فیلدهای جدید
    emergency_info: Optional[EmergencyInfo] = None
    campaign_settings: Optional[CampaignSettings] = None
    progress_display_settings: Optional[Dict[str, Any]] = None
    linked_product_ids: Optional[List[int]] = []


# ---------- به‌روزرسانی نیاز ----------
class NeedAdUpdate(BaseModel):
    """ویرایش نیاز"""
    title: Optional[str] = None
    short_description: Optional[str] = None
    description: Optional[str] = None
    category: Optional[NeedCategory] = None
    target_amount: Optional[float] = None
    privacy_level: Optional[PrivacyLevel] = None
    is_urgent: Optional[bool] = None
    is_emergency: Optional[bool] = None
    emergency_type: Optional[EmergencyType] = None
    deadline: Optional[datetime] = None
    attachments: Optional[List[Dict[str, Any]]] = None
    campaign_settings: Optional[CampaignSettings] = None
    progress_display_settings: Optional[Dict[str, Any]] = None
    linked_product_ids: Optional[List[int]] = None


class NeedAdStatusUpdate(BaseModel):
    """تغییر وضعیت نیاز"""
    status: NeedStatus
    reject_reason: Optional[str] = None


# ---------- خروجی نیاز (عمومی) ----------
class NeedAdRead(BaseModel):
    """خواندن نیاز (عمومی)"""
    id: int
    uuid: str
    title: str
    short_description: str
    category: NeedCategory
    target_amount: float
    collected_amount: float
    currency: str
    status: NeedStatus
    privacy_level: PrivacyLevel
    is_urgent: bool
    is_emergency: bool
    emergency_type: Optional[str] = None
    city: str
    province: str
    charity_id: int
    charity_name: Optional[str] = None
    created_at: datetime
    progress_percentage: float = 0.0
    days_remaining: Optional[int] = None
    verification_count: int = 0

    # ✅ فیلدهای جدید برای نمایش عمومی
    verified_badge: bool = False
    badge_level: Optional[str] = None
    is_campaign: bool = False
    campaign_badge_text: Optional[str] = None
    trust_score: float = 0.0
    share_count: int = 0

    class Config:
        orm_mode = True


# ---------- خروجی نیاز (جزئیات کامل) ----------
class NeedAdDetail(NeedAdRead):
    """جزئیات کامل نیاز (برای کاربران مجاز)"""
    description: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    deadline: Optional[datetime] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    attachments: List[Dict[str, Any]] = []
    needy_user_id: Optional[int] = None
    created_by_id: int

    # ✅ فیلدهای جدید
    emergency_info: Optional[EmergencyInfo] = None
    verified_by_list: List[VerifiedByInfo] = []
    campaign_settings: Optional[CampaignSettings] = None
    progress_display_settings: Dict[str, Any] = {
        "show_percentage": True,
        "show_collected": True,
        "show_remaining": True,
        "progress_bar_style": "circular",
        "progress_bar_color": "primary"
    }
    linked_product_ids: List[int] = []
    linked_products: List[Dict[str, Any]] = []
    social_sharing: SocialSharing = SocialSharing()
    trust_score: float = 0.0
    verifications: List[Dict] = []
    comments: List[Dict] = []

    class Config:
        orm_mode = True


# ---------- فیلتر و جستجو ----------
class NeedAdFilter(BaseModel):
    """فیلترهای جستجوی نیازها"""
    category: Optional[NeedCategory] = None
    status: Optional[NeedStatus] = None
    city: Optional[str] = None
    province: Optional[str] = None
    charity_id: Optional[int] = None
    is_urgent: Optional[bool] = None
    is_emergency: Optional[bool] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    verified_only: bool = False

    # ✅ فیلترهای جدید
    has_verified_badge: Optional[bool] = None
    is_campaign: Optional[bool] = None
    min_trust_score: Optional[float] = Field(None, ge=0, le=100)
    emergency_type: Optional[EmergencyType] = None

    search_text: Optional[str] = None
    sort_by: str = "created_at"
    sort_order: str = "desc"


# ---------- پیش‌نمایش Wizard ----------
class WizardPreview(BaseModel):
    """پیش‌نمایش نهایی قبل از ثبت"""
    basic_info: Step1BasicInfo
    financial_info: Step2FinancialInfo
    location_info: Step3LocationInfo
    details: Step4Details
    attachments: Step5Attachments
    charity_id: int
    total_steps: int = 5
    current_step: int = 5

    # ✅ پیش‌نمایش فیلدهای جدید
    emergency_info: Optional[EmergencyInfo] = None
    campaign_settings: Optional[CampaignSettings] = None
    estimated_completion_date: Optional[datetime] = None
    trust_score_preview: float = 0.0


# ---------- لاگ دسترسی به فایل‌ها ----------
class NeedAttachmentAccessLog(BaseModel):
    """لاگ دسترسی به فایل‌های حساس"""
    attachment_id: int
    file_name: str
    accessed_by: str
    accessed_at: datetime
    ip_address: str
    action: str  # view, download


# ---------- به‌روزرسانی پیشرفت مالی ----------
class NeedProgressUpdate(BaseModel):
    """به‌روزرسانی دستی پیشرفت توسط مدیر"""
    collected_amount: float = Field(..., ge=0)
    notes: Optional[str] = None
    update_reason: str


# ---------- لینک محصول به نیاز ----------
class LinkProductToNeed(BaseModel):
    """لینک کردن محصول فروشگاهی به نیاز"""
    product_id: int
    donation_amount: Optional[float] = None
    charity_percentage: Optional[float] = None


# ---------- اشتراک‌گذاری اجتماعی ----------
class SocialShare(BaseModel):
    """ثبت اشتراک‌گذاری در شبکه‌های اجتماعی"""
    platform: str  # telegram, whatsapp, twitter, facebook, linkedin
    share_url: str