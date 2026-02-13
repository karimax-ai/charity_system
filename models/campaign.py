# app/models/campaign.py
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, Enum, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum
from models.base import Base


class CampaignStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class CampaignType(str, enum.Enum):
    PEER_TO_PEER = "peer_to_peer"  # کمپین شخصی برای جمع‌آوری برای یک نیاز
    BIRTHDAY = "birthday"  # کمپین تولد
    WEDDING = "wedding"  # کمپین عروسی
    MEMORIAL = "memorial"  # کمپین یادبود
    CORPORATE = "corporate"  # کمپین شرکتی
    SCHOOL = "school"  # کمپین مدرسه/دانشگاه
    MOSQUE = "mosque"  # کمپین مسجد/هیئت
    OTHER = "other"


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))

    # 👤 سازنده کمپین
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    need_id = Column(Integer, ForeignKey("need_ads.id"), nullable=True)  # نیاز هدف (اختیاری)
    charity_id = Column(Integer, ForeignKey("charities.id"), nullable=False)  # خیریه مقصد

    # 📝 اطلاعات پایه
    title = Column(String(200), nullable=False)
    slug = Column(String(200), unique=True, nullable=False)  # برای URL
    description = Column(Text, nullable=False)
    short_description = Column(String(500), nullable=True)
    cover_image = Column(String(500), nullable=True)  # تصویر شاخص
    video_url = Column(String(500), nullable=True)  # ویدئوی معرفی

    # 🎯 اهداف
    target_amount = Column(Float, nullable=False)
    currency = Column(String(3), default="IRR")
    collected_amount = Column(Float, default=0.0)
    donor_count = Column(Integer, default=0)

    # 📅 زمان‌بندی
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=True)
    duration_days = Column(Integer, nullable=True)  # مدت زمان به روز

    # 📊 وضعیت
    status = Column(Enum(CampaignStatus), default=CampaignStatus.DRAFT)
    campaign_type = Column(Enum(CampaignType), default=CampaignType.PEER_TO_PEER)

    # 🔗 اشتراک‌گذاری
    share_code = Column(String(50), unique=True, nullable=False)  # کد یکتا برای اشتراک
    share_url = Column(String(500), nullable=True)  # URL کامل
    share_count = Column(Integer, default=0)

    # 💝 پیام شخصی
    personal_message = Column(Text, nullable=True)  # پیام شخصی سازنده
    dedication_name = Column(String(200), nullable=True)  # به نام چه کسی؟
    dedication_message = Column(Text, nullable=True)  # پیام هدیه

    # 🏆 تنظیمات
    is_featured = Column(Boolean, default=False)  # نمایش ویژه
    is_public = Column(Boolean, default=True)  # عمومی/خصوصی
    allow_comments = Column(Boolean, default=True)
    show_donors = Column(Boolean, default=True)  # نمایش اسامی اهداکنندگان

    # 📈 آمار
    view_count = Column(Integer, default=0)
    unique_visitors = Column(Integer, default=0)
    conversion_rate = Column(Float, default=0.0)  # نرخ تبدیل بازدید به کمک

    # 🤝 تیم (برای کمپین‌های گروهی)
    team_members = Column(JSON, default=list)  # [{user_id, name, role}]

    # 🎨 سفارشی‌سازی
    theme_color = Column(String(20), default="#4CAF50")
    custom_css = Column(Text, nullable=True)
    custom_html = Column(Text, nullable=True)

    # 🕒 زمان‌ها
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    published_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_reason = Column(String(500), nullable=True)

    # 🔗 Relationships
    owner = relationship("User", foreign_keys=[owner_id], back_populates="campaigns_owned")
    need = relationship("NeedAd", back_populates="campaigns")
    charity = relationship("Charity", back_populates="campaigns")
    donations = relationship("CampaignDonation", back_populates="campaign", cascade="all, delete-orphan")
    shares = relationship("CampaignShare", back_populates="campaign", cascade="all, delete-orphan")
    comments = relationship("CampaignComment", back_populates="campaign", cascade="all, delete-orphan")


class CampaignDonation(Base):
    __tablename__ = "campaign_donations"

    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))

    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    donor_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # nullable برای ناشناس
    donation_id = Column(Integer, ForeignKey("donations.id"), nullable=True)  # ارجاع به کمک اصلی

    # 💰 اطلاعات کمک
    amount = Column(Float, nullable=False)
    currency = Column(String(3), default="IRR")
    message = Column(Text, nullable=True)  # پیام همراه کمک
    is_anonymous = Column(Boolean, default=False)

    # 🔗 اطلاعات اشتراک
    shared_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # کاربری که لینک را اشتراک گذاشته
    share_id = Column(Integer, ForeignKey("campaign_shares.id"), nullable=True)  # کدام اشتراک

    # 🕒 زمان
    donated_at = Column(DateTime(timezone=True), server_default=func.now())

    # 🔗 Relationships
    campaign = relationship("Campaign", back_populates="donations")
    donor = relationship("User", foreign_keys=[donor_id])
    sharer = relationship("User", foreign_keys=[shared_by])
    share = relationship("CampaignShare")
    donation = relationship("Donation")


class CampaignShare(Base):
    __tablename__ = "campaign_shares"

    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))

    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # اشتراک‌گذار

    # 🔗 اطلاعات اشتراک
    share_code = Column(String(50), unique=True, nullable=False)  # کد یکتا برای این اشتراک
    share_url = Column(String(500), nullable=True)  # URL اختصاصی
    platform = Column(String(50), nullable=True)  # telegram, whatsapp, twitter, etc.

    # 📊 آمار
    click_count = Column(Integer, default=0)
    donation_count = Column(Integer, default=0)
    donation_amount = Column(Float, default=0.0)
    conversion_rate = Column(Float, default=0.0)

    # 🕒 زمان
    shared_at = Column(DateTime(timezone=True), server_default=func.now())
    last_clicked_at = Column(DateTime(timezone=True), nullable=True)

    # 🔗 Relationships
    campaign = relationship("Campaign", back_populates="shares")
    user = relationship("User", foreign_keys=[user_id])
    donations = relationship("CampaignDonation", back_populates="share")


class CampaignComment(Base):
    __tablename__ = "campaign_comments"

    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    parent_id = Column(Integer, ForeignKey("campaign_comments.id"), nullable=True)  # پاسخ به نظر

    content = Column(Text, nullable=False)
    is_approved = Column(Boolean, default=True)
    likes = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 🔗 Relationships
    campaign = relationship("Campaign", back_populates="comments")
    user = relationship("User")
    parent = relationship("CampaignComment", remote_side=[id])
    replies = relationship("CampaignComment", back_populates="parent", cascade="all, delete-orphan")