# app/models/need_ad.py
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, func, ForeignKey, Float, Enum, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import ENUM
import uuid

from models.association_tables import product_need_association
from models.base import Base


class NeedAd(Base):
    __tablename__ = "need_ads"

    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    short_description = Column(String(500))

    # اطلاعات مالی
    target_amount = Column(Float, nullable=False)  # مبلغ هدف
    collected_amount = Column(Float, default=0.0)  # مبلغ جمع‌آوری شده
    currency = Column(String(3), default="IRR")  # ارز
    emergency = relationship("NeedEmergency", back_populates="need", uselist=False, cascade="all, delete-orphan")


    # ✅ ارتباط با فایل‌ها از طریق جدول واسط
    attachments_relation = relationship(
        "NeedAttachment",
        back_populates="need",
        cascade="all, delete-orphan",
    )

    # ✅ لینک محصولات فروشگاهی
    linked_product_ids = Column(JSON, default=list)  # لیست ID محصولات مرتبط
    linked_products = relationship(
        "Product",
        secondary=lambda: product_need_association,
        back_populates="linked_needs",
    )

    # ✅ تنظیمات پیشرفت بصری
    progress_display_settings = Column(JSON, default={
        "show_percentage": True,
        "show_collected": True,
        "show_remaining": True,
        "progress_bar_style": "circular",  # circular, linear
        "progress_bar_color": "primary"
    })

    # ✅ لیست تأییدکنندگان با نشان
    verified_by_list = Column(JSON,
                              default=list)  # [{"charity_id": 1, "charity_name": "...", "verified_at": "...", "badge_url": "..."}]

    # ✅ کمپین زمان‌دار
    campaign_settings = Column(JSON, default={
        "is_campaign": False,
        "campaign_start": None,
        "campaign_end": None,
        "campaign_goal": None,
        "campaign_type": "normal",  # normal, matching, urgent
        "matching_donor": None,  # برای کمپین‌های همسان
        "matching_ratio": 0,  # مثلاً 0.5 یعنی به ازای هر تومان، ۵۰٪ اضافه
        "badge_text": None,
    })

    # ✅ تنظیمات اشتراک‌گذاری اجتماعی
    social_sharing = Column(JSON, default={
        "share_count": 0,
        "platforms": {
            "telegram": 0,
            "whatsapp": 0,
            "twitter": 0,
            "facebook": 0,
            "linkedin": 0
        }
    })

    # ✅ امتیاز اعتماد (Verified Badge)
    trust_score = Column(Float, default=0.0)  # 0-100
    verified_badge = Column(Boolean, default=False)  # نشان اعتماد
    badge_level = Column(String(20), default="bronze")  # bronze, silver, gold, platinum

    # وضعیت
    status = Column(
        Enum("draft", "pending", "approved", "rejected", "active", "completed", "cancelled",
             name="need_status"),
        default="draft"
    )

    # دسته‌بندی
    category = Column(
        Enum("medical", "education", "housing", "food", "clothing", "debt", "other",
             "emergency", "natural_disaster", name="need_category"),
        default="other"
    )

    # سطح دسترسی
    privacy_level = Column(
        Enum("public", "protected", "private", name="privacy_level"),
        default="protected"
    )

    # اطلاعات بحران
    is_urgent = Column(Boolean, default=False)
    is_emergency = Column(Boolean, default=False)
    emergency_type = Column(String(50))  # زلزله، سیل، etc

    # زمان‌بندی
    start_date = Column(DateTime(timezone=True))
    end_date = Column(DateTime(timezone=True))
    deadline = Column(DateTime(timezone=True))

    # موقعیت جغرافیایی
    city = Column(String(100))
    province = Column(String(100))
    latitude = Column(Float)
    longitude = Column(Float)

    # فایل‌های ضمیمه
    attachments = Column(JSON, default=list)  # لیست فایل‌ها

    # Foreign Keys
    charity_id = Column(Integer, ForeignKey("charities.id"))
    needy_user_id = Column(Integer, ForeignKey("users.id"))  # کاربر نیازمند
    created_by_id = Column(Integer, ForeignKey("users.id"))  # ایجادکننده

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    charity = relationship("Charity", back_populates="needs")
    needy_user = relationship("User", foreign_keys=[needy_user_id])
    creator = relationship("User", foreign_keys=[created_by_id])
    donations = relationship("Donation", back_populates="need")
    products = relationship("Product", back_populates="need")
    verifications = relationship(
        "NeedVerification",
        back_populates="need",
        cascade="all, delete-orphan",
    )

    comments = relationship("NeedComment", back_populates="need")

    campaigns = relationship(
        "Campaign",
        back_populates="need",
        cascade="all, delete-orphan"
    )