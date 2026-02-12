# models/notification.py
import enum
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, func, ForeignKey, Enum, JSON
from sqlalchemy.orm import relationship
import uuid
from models.base import Base


class NotificationType(str, enum.Enum):
    """انواع نوتیفیکیشن"""
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"  # برای اپ موبایل
    SYSTEM = "system"  # نوتیفیکیشن داخلی سیستم
    URGENT = "urgent"  # فوری (برای بحران‌ها)


class NotificationStatus(str, enum.Enum):
    """وضعیت نوتیفیکیشن"""
    PENDING = "pending"  # در انتظار ارسال
    SENT = "sent"  # ارسال شده
    DELIVERED = "delivered"  # تحویل داده شده (برای SMS/Email)
    READ = "read"  # خوانده شده (برای PUSH/SYSTEM)
    FAILED = "failed"  # ارسال ناموفق
    CANCELLED = "cancelled"  # لغو شده


class NotificationPriority(str, enum.Enum):
    """اولویت نوتیفیکیشن"""
    LOW = "low"  # معمولی
    NORMAL = "normal"  # عادی
    HIGH = "high"  # مهم
    URGENT = "urgent"  # فوری


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))

    # اطلاعات پایه
    type = Column(Enum(NotificationType), nullable=False)
    status = Column(Enum(NotificationStatus), default=NotificationStatus.PENDING)
    priority = Column(Enum(NotificationPriority), default=NotificationPriority.NORMAL)

    # اطلاعات گیرنده
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    recipient_email = Column(String(255))
    recipient_phone = Column(String(20))
    recipient_device_token = Column(String(500))  # برای push notifications

    # محتوای پیام
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    template_name = Column(String(100))  # نام template (اختیاری)

    # داده‌های پویا
    data = Column(JSON, default=dict)  # داده‌های اضافی برای template
    payload = Column(JSON)


    # اطلاعات ارسال
    sent_via = Column(String(50))  # provider: twilio, kavenegar, etc.
    external_id = Column(String(255))  # ID در سرویس خارجی
    delivery_receipt = Column(JSON)  # رسید تحویل از سرویس خارجی

    # زمان‌ها
    scheduled_for = Column(DateTime(timezone=True))  # زمان برنامه‌ریزی شده
    sent_at = Column(DateTime(timezone=True))  # زمان ارسال واقعی
    delivered_at = Column(DateTime(timezone=True))  # زمان تحویل
    read_at = Column(DateTime(timezone=True))  # زمان خواندن
    expires_at = Column(DateTime(timezone=True))  # زمان انقضا

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", foreign_keys=[user_id])