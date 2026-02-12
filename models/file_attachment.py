# models/file_attachment.py
import enum
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, func, ForeignKey, Enum, JSON
from sqlalchemy.orm import relationship
import uuid
from models.base import Base


class FileType(str, enum.Enum):
    IMAGE = "image"
    DOCUMENT = "document"
    PDF = "pdf"
    OTHER = "other"


class FileAccessLevel(str, enum.Enum):
    PUBLIC = "public"  # همه می‌توانند ببینند
    PROTECTED = "protected"  # کاربران ثبت‌نام‌شده
    PRIVATE = "private"  # فقط کاربران خاص
    SENSITIVE = "sensitive"  # فقط ادمین/مدیران خیریه


class FileAttachment(Base):
    __tablename__ = "file_attachments"

    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))

    # اطلاعات فایل
    original_filename = Column(String(500), nullable=False)
    stored_filename = Column(String(500), nullable=False, unique=True)
    file_type = Column(Enum(FileType), nullable=False)
    mime_type = Column(String(100))
    file_size = Column(Integer)  # به بایت
    file_hash = Column(String(64))  # SHA-256 برای یکتایی

    # مسیر ذخیره‌سازی
    storage_path = Column(String(500))
    storage_provider = Column(String(50), default="local")  # local, s3, cloud_storage

    # سطح دسترسی
    access_level = Column(Enum(FileAccessLevel), default=FileAccessLevel.PROTECTED)
    is_encrypted = Column(Boolean, default=False)
    encryption_key_id = Column(String(100))  # برای فایل‌های رمزنگاری شده

    # اطلاعات مالکیت
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    entity_type = Column(String(50))  # need_ad, user, charity, product, etc.
    entity_id = Column(Integer)  # ID موجودیت مرتبط

    # متادیتا
    title = Column(String(200))
    description = Column(Text)
    tags = Column(JSON, default=list)

    # آمار و وضعیت
    download_count = Column(Integer, default=0)
    view_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

    # زمان‌ها
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    last_accessed_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))  # برای فایل‌های موقت

    # Relationships
    uploader = relationship("User", foreign_keys=[uploaded_by])