from pydantic import BaseModel, EmailStr, constr, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime
from models.user import UserStatus
from enum import Enum


# ---------- ثبت‌نام ----------
class UserCreate(BaseModel):
    email: EmailStr
    username: Optional[constr(min_length=3, max_length=50)]
    phone: Optional[str]
    password: constr(min_length=6)
    role_key: Optional[str] = "USER"
    captcha_token: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "username": "johndoe",
                "phone": "09123456789",
                "password": "StrongPass123!",
                "role_key": "USER"
            }
        }


class UserGender(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"



class UserRead(BaseModel):
    id: int
    uuid: str
    email: EmailStr
    phone: Optional[str]
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    full_name: Optional[str]
    national_id: Optional[str]
    gender: Optional[UserGender]
    birth_date: Optional[datetime]
    avatar_url: Optional[str]
    bio: Optional[str]
    address: Optional[str]
    city: Optional[str]
    province: Optional[str]
    postal_code: Optional[str]
    website: Optional[str]
    is_active: bool
    is_verified: bool
    status: UserStatus
    roles: List[str] = []
    language: str
    theme: str
    two_fa_enabled: bool
    social_links: Dict[str, str] = {}
    badges: List[str] = []
    badge_level: str
    trust_score: float
    created_at: datetime

    class Config:
        orm_mode = True





class UserDetail(UserRead):
    """جزئیات کامل کاربر (فقط برای خود کاربر و ادمین)"""
    email_verified_at: Optional[datetime]
    phone_verified_at: Optional[datetime]
    last_login_at: Optional[datetime]
    last_login_ip: Optional[str]
    total_donations: float
    donations_count: int
    total_sponsored: float
    sponsored_count: int
    total_needs: int
    completed_needs: int
    settings: Dict[str, Any] = {}
    verification_documents: List[Dict[str, Any]] = []
    verified_at: Optional[datetime]
    verification_notes: Optional[str]


# ---------- ویرایش پروفایل ----------
class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    phone: Optional[str] = None
    bio: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    postal_code: Optional[str] = None
    website: Optional[str] = None
    gender: Optional[UserGender] = None
    birth_date: Optional[datetime] = None
    language: Optional[str] = None
    theme: Optional[str] = None
    social_links: Optional[Dict[str, str]] = None
    settings: Optional[Dict[str, Any]] = None



# ---------- خروجی کاربر ----------
class UserRead(BaseModel):
    uuid: str
    email: EmailStr
    username: Optional[str]
    phone: Optional[str]
    is_active: bool
    is_verified: bool
    roles: List[str] = []

    class Config:
        orm_mode = True


# ---------- ورود ----------
class UserLogin(BaseModel):
    email: EmailStr
    password: str
    captcha_token: Optional[str] = None
    device_id: Optional[str] = None


# ---------- توکن ----------
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- OTP ----------
class OTPRequest(BaseModel):
    phone: str
    purpose: Optional[str] = "login"  # login, register, password_reset, 2fa


class OTPVerify(BaseModel):
    phone: str
    code: str
    purpose: Optional[str] = "login"


# ---------- تغییر رمز ----------
class ChangePassword(BaseModel):
    old_password: str
    new_password: constr(min_length=8)

    @validator('new_password')
    def validate_password(cls, v):
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        if not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in v):
            raise ValueError('Password must contain at least one special character')
        return v


# ---------- Google OAuth ----------
class GoogleOAuth(BaseModel):
    token: str
    device_id: Optional[str] = None


# ---------- توکن پاسخ ----------
class TokenResponse(BaseModel):
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None  # ✅ اضافه شد
    token_type: str = "bearer"
    roles: List[str] = []
    status: UserStatus
    message: Optional[str] = None
    requires_2fa: bool = False  # ✅ اضافه شد
    requires_verification: bool = False  # ✅ اضافه شد

    class Config:
        orm_mode = True
        use_enum_values = True


# ---------- درخواست بازنشانی رمز ----------
class PasswordResetRequest(BaseModel):
    email: EmailStr
    captcha_token: Optional[str] = None


class PasswordResetVerify(BaseModel):
    email: EmailStr
    otp: str
    new_password: constr(min_length=8)

    @validator('new_password')
    def validate_password(cls, v):
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v


# ========== ✅ کلاس‌های جدید اضافه شده ==========

# ---------- رفرش توکن ----------
class RefreshToken(BaseModel):
    """درخواست رفرش توکن"""
    refresh_token: str

    class Config:
        json_schema_extra = {
            "example": {
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
            }
        }


# ---------- ایجاد کاربران گروهی ----------
class BulkUserCreate(BaseModel):
    """ایجاد دسته‌جمعی کاربران توسط ادمین"""
    users: List[Dict[str, str]] = Field(..., description="لیست کاربران با ایمیل/شماره")
    role_key: str = Field(..., description="نقش اختصاص داده شده به همه کاربران")
    send_sms: bool = True
    send_email: bool = True

    @validator('users')
    def validate_users(cls, v):
        for idx, user in enumerate(v):
            if 'email' not in user and 'phone' not in user:
                raise ValueError(f'User {idx}: must have either email or phone')
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "users": [
                    {"email": "user1@example.com", "phone": "09123456789", "username": "user1"},
                    {"email": "user2@example.com", "phone": "09129876543", "username": "user2"}
                ],
                "role_key": "NEEDY",
                "send_sms": True,
                "send_email": True
            }
        }


class BulkUserResponse(BaseModel):
    """پاسخ ایجاد کاربران گروهی"""
    success_count: int
    failed_count: int
    failed_users: List[Dict[str, str]] = Field(default_factory=list)
    generated_passwords: Dict[str, str] = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "success_count": 1,
                "failed_count": 1,
                "failed_users": [
                    {"email": "user2@example.com", "reason": "Email already exists"}
                ],
                "generated_passwords": {
                    "user1@example.com": "aB3$kL9#pQ"
                }
            }
        }


# ---------- مدارک احراز هویت ----------
class DocumentType(str, Enum):
    NATIONAL_ID = "national_id"
    CHARITY_CERT = "charity_cert"
    BUSINESS_LICENSE = "business_license"
    LETTER_OF_REQUEST = "letter_of_request"


class VerificationDocument(BaseModel):
    """مدرک ارسالی برای احراز هویت"""
    document_type: DocumentType
    document_number: Optional[str] = None
    file_url: str
    file_name: str
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    expiry_date: Optional[datetime] = None


class VerificationRequest(BaseModel):
    """درخواست احراز هویت"""
    user_id: str
    documents: List[VerificationDocument]
    notes: Optional[str] = None


class VerificationReview(BaseModel):
    """بررسی درخواست احراز هویت توسط ادمین"""
    request_id: int
    status: UserStatus  # ACTIVE یا REJECTED
    admin_notes: Optional[str] = None

    @validator('status')
    def validate_status(cls, v):
        if v not in [UserStatus.ACTIVE, UserStatus.REJECTED]:
            raise ValueError('Status must be ACTIVE or REJECTED')
        return v


# ---------- CAPTCHA ----------
class CaptchaResponse(BaseModel):
    """پاسخ CAPTCHA"""
    captcha_id: str
    captcha_image: str  # base64


# ---------- دستگاه‌های معتبر ----------
class TrustDeviceRequest(BaseModel):
    """اعتماد به دستگاه"""
    device_id: str
    device_name: Optional[str] = None


# ---------- پاسخ عمومی ----------
class MessageResponse(BaseModel):
    """پاسخ ساده با پیام"""
    message: str
    detail: Optional[Dict[str, Any]] = None



class VerifyEmail(BaseModel):
    token: str


class VerifyPhone(BaseModel):
    phone: str
    code: str


# ---------- فیلتر جستجو ----------
class UserFilter(BaseModel):
    status: Optional[UserStatus] = None
    role: Optional[str] = None
    is_verified: Optional[bool] = None
    is_active: Optional[bool] = None
    search_text: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    min_trust_score: Optional[float] = None
    has_badge: Optional[str] = None