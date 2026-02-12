# 4️⃣ app/api/v1/endpoints/need_attachments.py
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime

from core.database import get_db
from core.permissions import get_current_user, require_roles
from models.user import User
from services.need_attachment_service import NeedAttachmentService
from schemas.need_attachment import (
    NeedAttachmentCreate, NeedAttachmentRead,
    NeedAttachmentAccessLog, AttachmentPurpose
)

router = APIRouter()


@router.post("/", response_model=NeedAttachmentRead)
async def upload_need_attachment(
        need_id: int,
        file: UploadFile = File(...),
        purpose: AttachmentPurpose = Form(AttachmentPurpose.DOCUMENTATION),
        title: Optional[str] = Form(None),
        description: Optional[str] = Form(None),
        is_public: bool = Form(False),
        encrypt: bool = Form(True),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """آپلود فایل برای نیاز"""
    service = NeedAttachmentService(db)

    attachment = await service.add_attachment(
        need_id=need_id,
        file=file,
        user=current_user,
        purpose=purpose,
        description=description,
        is_public=is_public,
        encrypt=encrypt
    )

    return attachment


@router.get("/", response_model=List[NeedAttachmentRead])
async def get_need_attachments(
        need_id: int,
        include_private: bool = Query(False),
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """دریافت فایل‌های یک نیاز"""
    service = NeedAttachmentService(db)
    attachments = await service.get_attachments(
        need_id, current_user, include_private
    )
    return attachments


@router.get("/{attachment_id}/download")
async def download_attachment(
        need_id: int,
        attachment_id: int,
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """دانلود فایل با لاگ دسترسی"""
    service = NeedAttachmentService(db)

    # ثبت لاگ دسترسی
    await service.log_access(attachment_id, current_user, "download")

    # دانلود فایل
    file_content = await service.download_attachment(attachment_id, current_user)
    return file_content


@router.get("/{attachment_id}/logs", response_model=List[NeedAttachmentAccessLog])
async def get_attachment_access_logs(
        need_id: int,
        attachment_id: int,
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER")),
        db: AsyncSession = Depends(get_db)
):
    """مشاهده لاگ دسترسی به فایل (فقط مدیر)"""
    service = NeedAttachmentService(db)
    logs = await service.get_access_logs(attachment_id)
    return logs