# app/models/need_emergency.py
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, func, ForeignKey, Float, Enum, JSON
from sqlalchemy.orm import relationship
import uuid
import enum
from models.base import Base


class EmergencyType(str, enum.Enum):
    EARTHQUAKE = "earthquake"  # زلزله
    FLOOD = "flood"  # سیل
    FIRE = "fire"  # آتش‌سوزی
    ACCIDENT = "accident"  # حادثه
    STORM = "storm"  # طوفان
    DROUGHT = "drought"  # خشکسالی
    WAR = "war"  # جنگ
    PANDEMIC = "pandemic"  # همه‌گیری
    OTHER = "other"  # سایر


class EmergencySeverity(str, enum.Enum):
    CRITICAL = "critical"  # بحرانی
    SEVERE = "severe"  # شدید
    MODERATE = "moderate"  # متوسط
    LOW = "low"  # کم


class EmergencyStatus(str, enum.Enum):
    ACTIVE = "active"  # فعال
    RESPONDING = "responding"  # در حال پاسخگویی
    STABILIZED = "stabilized"  # تثبیت شده
    RECOVERING = "recovering"  # در حال بازسازی
    CLOSED = "closed"  # بسته شده


class NeedEmergency(Base):
    __tablename__ = "need_emergencies"

    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))

    # ارتباط با نیاز
    need_id = Column(Integer, ForeignKey("need_ads.id", ondelete="CASCADE"), nullable=False, unique=True)

    # اطلاعات بحران
    emergency_type = Column(Enum(EmergencyType), nullable=False)
    severity = Column(Enum(EmergencySeverity), default=EmergencySeverity.MODERATE)
    status = Column(Enum(EmergencyStatus), default=EmergencyStatus.ACTIVE)

    # موقعیت جغرافیایی
    affected_area = Column(String(500))  # منطقه آسیب‌دیده
    latitude = Column(Float)
    longitude = Column(Float)
    radius_km = Column(Float)  # شعاع تحت تأثیر

    # آمار بحران
    estimated_affected_people = Column(Integer)
    estimated_damage_cost = Column(Float)
    death_toll = Column(Integer, default=0)
    injured_count = Column(Integer, default=0)
    displaced_count = Column(Integer, default=0)

    # اطلاعات دولتی
    government_reference_number = Column(String(100))  # شماره ارجاع دولتی
    declared_by = Column(String(200))  # اعلام‌کننده (استانداری، هلال احمر، etc)

    # زمان‌بندی
    occurred_at = Column(DateTime(timezone=True), nullable=False)  # زمان وقوع
    declared_at = Column(DateTime(timezone=True), server_default=func.now())  # زمان اعلام
    expected_end_date = Column(DateTime(timezone=True))  # زمان پایان تخمینی
    closed_at = Column(DateTime(timezone=True))  # زمان بسته شدن

    # رسانه
    media_attachments = Column(JSON, default=list)  # تصاویر، ویدئوها، مدارک
    news_links = Column(JSON, default=list)  # لینک اخبار مرتبط

    # تنظیمات نوتیفیکیشن
    notify_all_users = Column(Boolean, default=True)  # به همه کاربران نوتیفیکیشن ارسال شود
    notify_sms = Column(Boolean, default=True)
    notify_email = Column(Boolean, default=True)
    notify_push = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    need = relationship("NeedAd", back_populates="emergency")