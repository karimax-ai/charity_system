# models/notification_preference.py


from sqlalchemy import *
from sqlalchemy.orm import relationship

from models import Base
from models.notification import NotificationType


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    # تنظیمات کلی
    email_enabled = Column(Boolean, default=True)
    sms_enabled = Column(Boolean, default=True)
    push_enabled = Column(Boolean, default=True)
    system_enabled = Column(Boolean, default=True)

    # تنظیمات بر اساس رویداد
    event_settings = Column(JSON, default=dict)  # {"need_approved": {"email": true, "sms": false}}

    # زمان‌بندی دریافت
    quiet_hours_start = Column(String(5))  # "22:00"
    quiet_hours_end = Column(String(5))  # "07:00"
    quiet_hours_enabled = Column(Boolean, default=False)

    # تنظیمات دیگر
    digest_enabled = Column(Boolean, default=False)  # دریافت خلاصه روزانه/هفتگی
    digest_frequency = Column(String(20), default="daily")  # daily, weekly

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", foreign_keys=[user_id])