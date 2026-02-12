# 2️⃣ app/schemas/need_attachment.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class AttachmentPurpose(str, Enum):
    DOCUMENTATION = "documentation"
    PROOF = "proof"
    RECEIPT = "receipt"
    MEDICAL = "medical"
    LEGAL = "legal"
    IMAGE = "image"
    OTHER = "other"


class NeedAttachmentCreate(BaseModel):
    purpose: AttachmentPurpose = AttachmentPurpose.DOCUMENTATION
    title: Optional[str] = None
    description: Optional[str] = None
    is_public: bool = False
    access_log_enabled: bool = True


class NeedAttachmentRead(BaseModel):
    id: int
    uuid: str
    need_id: int
    file_id: int
    purpose: AttachmentPurpose
    title: Optional[str]
    description: Optional[str]
    is_public: bool
    access_log_enabled: bool
    access_count: int
    last_accessed_at: Optional[datetime]
    created_at: datetime

    # اطلاعات فایل
    file_name: Optional[str]
    file_size: Optional[int]
    mime_type: Optional[str]
    file_url: Optional[str]

    class Config:
        orm_mode = True


class NeedAttachmentAccessLog(BaseModel):
    attachment_id: int
    file_name: str
    accessed_by: str
    accessed_at: datetime
    ip_address: str
    action: str
    success: bool