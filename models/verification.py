import uuid

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum as SQLEnum, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from models.base import Base


class DocumentType(str, enum.Enum):
    NATIONAL_ID = "national_id"
    CHARITY_CERT = "charity_cert"
    BUSINESS_LICENSE = "business_license"
    LETTER_OF_REQUEST = "letter_of_request"


class DocumentStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class VerificationDocument(Base):
    __tablename__ = "verification_documents"

    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    document_type = Column(SQLEnum(DocumentType), nullable=False)
    document_number = Column(String(100), nullable=True)

    # مسیر فایل (در S3 یا فضای ابری)
    file_path = Column(String(500), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=True)
    mime_type = Column(String(100), nullable=True)

    status = Column(SQLEnum(DocumentStatus), default=DocumentStatus.PENDING)
    admin_note = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # relationships
    user = relationship("User", back_populates="verification_documents")
    reviewer = relationship("User", foreign_keys=[reviewed_by])