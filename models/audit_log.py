# app/models/audit_log.py
from sqlalchemy import Column, Integer, String, Text, DateTime, func, ForeignKey, JSON
from sqlalchemy.orm import relationship
import uuid
from models.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))

    # اطلاعات لاگ
    action = Column(String(100), nullable=False)  # ایجاد، خواندن، به‌روزرسانی، حذف
    entity_type = Column(String(50), nullable=False)  # User, NeedAd, etc
    entity_id = Column(Integer)
    entity_uuid = Column(String(36))

    # تغییرات
    old_values = Column(JSON)
    new_values = Column(JSON)

    # اطلاعات درخواست
    ip_address = Column(String(45))
    user_agent = Column(Text)
    endpoint = Column(String(500))
    method = Column(String(10))

    # Foreign Keys
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", foreign_keys=[user_id])