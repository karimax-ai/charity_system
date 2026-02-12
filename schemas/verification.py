# schemas/verification.py
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from enum import Enum


class DocumentType(str, Enum):
    NATIONAL_ID = "national_id"
    CHARITY_CERT = "charity_cert"
    BUSINESS_LICENSE = "business_license"
    LETTER_OF_REQUEST = "letter_of_request"


class DocumentStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class VerificationDocumentCreate(BaseModel):
    document_type: DocumentType
    document_number: Optional[str]
    file_path: str
    file_name: str
    file_size: Optional[int]
    mime_type: Optional[str]

class VerificationDocumentOut(BaseModel):
    id: int
    uuid: str
    document_type: DocumentType
    document_number: Optional[str]

    file_path: str
    file_name: str
    file_size: Optional[int]
    mime_type: Optional[str]

    status: DocumentStatus
    admin_note: Optional[str]

    created_at: datetime
    reviewed_at: Optional[datetime]
    expires_at: Optional[datetime]

    class Config:
        from_attributes = True  # ✅ خیلی مهم (ORM Mode جدید)
