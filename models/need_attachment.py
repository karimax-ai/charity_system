# app/models/need_attachment.py
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, func, ForeignKey, Enum, JSON
from sqlalchemy.orm import relationship
import uuid
import enum
from models.base import Base


class AttachmentPurpose(str, enum.Enum):
    DOCUMENTATION = "documentation"  # مستندات
    PROOF = "proof"  # مدرک
    RECEIPT = "receipt"  # رسید
    MEDICAL = "medical"  # مدارک پزشکی
    LEGAL = "legal"  # مدارک قانونی
    IMAGE = "image"  # تصویر
    OTHER = "other"  # سایر


class NeedAttachment(Base):
    __tablename__ = "need_attachments"

    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))

    # ارتباطات
    need_id = Column(Integer, ForeignKey("need_ads.id", ondelete="CASCADE"), nullable=False)
    file_id = Column(Integer, ForeignKey("file_attachments.id", ondelete="CASCADE"), nullable=False)

    # اطلاعات
    purpose = Column(Enum(AttachmentPurpose), default=AttachmentPurpose.DOCUMENTATION)
    title = Column(String(200))
    description = Column(Text)
    is_public = Column(Boolean, default=False)  # آیا برای عموم قابل مشاهده است؟

    # لاگ دسترسی
    access_log_enabled = Column(Boolean, default=True)  # آیا دسترسی به این فایل لاگ شود؟
    last_accessed_at = Column(DateTime(timezone=True))
    access_count = Column(Integer, default=0)

    # زمان‌ها
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    need = relationship("NeedAd", back_populates="attachments_relation")
    file = relationship("FileAttachment")