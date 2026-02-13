# app/schemas/campaign.py
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import re
import slugify


class CampaignStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class CampaignType(str, Enum):
    PEER_TO_PEER = "peer_to_peer"
    BIRTHDAY = "birthday"
    WEDDING = "wedding"
    MEMORIAL = "memorial"
    CORPORATE = "corporate"
    SCHOOL = "school"
    MOSQUE = "mosque"
    OTHER = "other"


# ---------- ایجاد کمپین ----------
class CampaignCreate(BaseModel):
    title: str = Field(..., min_length=5, max_length=200)
    description: str = Field(..., min_length=20)
    short_description: Optional[str] = Field(None, max_length=500)

    need_id: Optional[int] = None
    charity_id: int

    target_amount: float = Field(..., gt=0)
    currency: str = "IRR"

    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    duration_days: Optional[int] = Field(None, ge=1, le=365)

    campaign_type: CampaignType = CampaignType.PEER_TO_PEER

    cover_image: Optional[str] = None
    video_url: Optional[str] = None

    personal_message: Optional[str] = None
    dedication_name: Optional[str] = None
    dedication_message: Optional[str] = None

    is_public: bool = True
    allow_comments: bool = True
    show_donors: bool = True

    theme_color: Optional[str] = "#4CAF50"

    @validator('title')
    def create_slug(cls, v):
        return slugify.slugify(v)

    @validator('end_date')
    def validate_dates(cls, v, values):
        if v and 'start_date' in values and values['start_date']:
            if v <= values['start_date']:
                raise ValueError('End date must be after start date')
        return v

    @validator('duration_days')
    def validate_duration(cls, v, values):
        if v and 'end_date' in values and values['end_date']:
            raise ValueError('Cannot set both duration_days and end_date')
        return v

    @validator('video_url')
    def validate_video_url(cls, v):
        if v:
            if not re.match(r'^(https?://)?(www\.)?(youtube\.com|youtu\.be|aparat\.com|vimeo\.com)', v):
                raise ValueError('Video URL must be from YouTube, Aparat, or Vimeo')
        return v


# ---------- به‌روزرسانی کمپین ----------
class CampaignUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=5, max_length=200)
    description: Optional[str] = Field(None, min_length=20)
    short_description: Optional[str] = Field(None, max_length=500)

    target_amount: Optional[float] = Field(None, gt=0)
    end_date: Optional[datetime] = None

    status: Optional[CampaignStatus] = None

    cover_image: Optional[str] = None
    video_url: Optional[str] = None

    personal_message: Optional[str] = None
    dedication_name: Optional[str] = None
    dedication_message: Optional[str] = None

    is_public: Optional[bool] = None
    allow_comments: Optional[bool] = None
    show_donors: Optional[bool] = None

    is_featured: Optional[bool] = None
    theme_color: Optional[str] = None


# ---------- پاسخ کمپین ----------
class CampaignRead(BaseModel):
    id: int
    uuid: str
    title: str
    slug: str
    description: str
    short_description: Optional[str]

    owner_id: int
    owner_name: Optional[str]
    need_id: Optional[int]
    need_title: Optional[str]
    charity_id: int
    charity_name: Optional[str]

    target_amount: float
    currency: str
    collected_amount: float
    donor_count: int
    progress_percentage: float

    start_date: datetime
    end_date: Optional[datetime]
    days_remaining: Optional[int]

    status: CampaignStatus
    campaign_type: CampaignType

    share_code: str
    share_url: Optional[str]
    share_count: int

    cover_image: Optional[str]
    video_url: Optional[str]

    personal_message: Optional[str]
    dedication_name: Optional[str]
    dedication_message: Optional[str]

    is_featured: bool
    is_public: bool
    allow_comments: bool
    show_donors: bool

    view_count: int
    conversion_rate: float

    created_at: datetime
    published_at: Optional[datetime]

    class Config:
        orm_mode = True


class CampaignDetail(CampaignRead):
    description: str
    team_members: List[Dict[str, Any]] = []
    theme_color: str
    recent_donations: List[Dict[str, Any]] = []
    top_donors: List[Dict[str, Any]] = []
    comments: List[Dict[str, Any]] = []


# ---------- کمک به کمپین ----------
class CampaignDonate(BaseModel):
    campaign_id: int
    amount: float = Field(..., gt=0)
    currency: str = "IRR"
    message: Optional[str] = Field(None, max_length=500)
    is_anonymous: bool = False
    share_code: Optional[str] = None  # کد اشتراک (برای رهگیری)


class CampaignDonationRead(BaseModel):
    id: int
    campaign_id: int
    donor_id: Optional[int]
    donor_name: Optional[str]
    amount: float
    currency: str
    message: Optional[str]
    is_anonymous: bool
    shared_by: Optional[int]
    shared_by_name: Optional[str]
    donated_at: datetime

    class Config:
        orm_mode = True


# ---------- اشتراک‌گذاری کمپین ----------
class CampaignShareCreate(BaseModel):
    campaign_id: int
    platform: Optional[str] = None  # telegram, whatsapp, etc.


class CampaignShareRead(BaseModel):
    id: int
    uuid: str
    campaign_id: int
    user_id: int
    user_name: Optional[str]
    share_code: str
    share_url: str
    platform: Optional[str]
    click_count: int
    donation_count: int
    donation_amount: float
    conversion_rate: float
    shared_at: datetime
    last_clicked_at: Optional[datetime]

    class Config:
        orm_mode = True


# ---------- نظر ----------
class CampaignCommentCreate(BaseModel):
    campaign_id: int
    content: str = Field(..., min_length=1, max_length=1000)
    parent_id: Optional[int] = None


class CampaignCommentRead(BaseModel):
    id: int
    campaign_id: int
    user_id: Optional[int]
    user_name: Optional[str]
    user_avatar: Optional[str]
    content: str
    parent_id: Optional[int]
    likes: int
    created_at: datetime
    replies: List[Dict[str, Any]] = []

    class Config:
        orm_mode = True


# ---------- فیلتر جستجو ----------
class CampaignFilter(BaseModel):
    status: Optional[CampaignStatus] = None
    campaign_type: Optional[CampaignType] = None
    charity_id: Optional[int] = None
    need_id: Optional[int] = None
    owner_id: Optional[int] = None
    is_featured: Optional[bool] = None
    is_public: Optional[bool] = None
    min_target: Optional[float] = None
    max_target: Optional[float] = None
    min_progress: Optional[float] = None
    search_text: Optional[str] = None
    sort_by: str = "created_at"
    sort_order: str = "desc"