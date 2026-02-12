# models/notification_template.py
from sqlalchemy import *

from models import Base
from models.notification import NotificationType


class NotificationTemplate(Base):
    __tablename__ = "notification_templates"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text)

    # نوع template
    template_type = Column(Enum(NotificationType), nullable=False)
    language = Column(String(10), default="fa")  # fa, en, etc.

    # محتوای template
    subject_template = Column(String(500))  # برای ایمیل
    title_template = Column(String(200))  # برای push/sms
    body_template = Column(Text, nullable=False)
    html_template = Column(Text)  # برای ایمیل

    # متادیتا
    variables = Column(JSON, default=list)  # لیست متغیرهای مورد نیاز
    default_data = Column(JSON, default=dict)  # داده‌های پیش‌فرض

    # وضعیت
    is_active = Column(Boolean, default=True)
    version = Column(Integer, default=1)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())