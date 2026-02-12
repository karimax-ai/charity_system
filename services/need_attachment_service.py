# app/services/need_attachment_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from fastapi import HTTPException, UploadFile
from typing import List, Optional
from datetime import datetime

from models.need_attachment import NeedAttachment, AttachmentPurpose
from models.need_ad import NeedAd
from models.file_attachment import FileAttachment
from models.file_access_log import FileAccessLog
from models.user import User
from services.file_service import FileService
from schemas.file import FileUpload


class NeedAttachmentService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.file_service = FileService(db)

    async def add_attachment(
        self,
        need_id: int,
        file: UploadFile,
        user: User,
        purpose: AttachmentPurpose = AttachmentPurpose.DOCUMENTATION,
        description: Optional[str] = None,
        is_public: bool = False,
        encrypt: bool = True
    ) -> NeedAttachment:
        """اضافه کردن فایل به نیاز با لاگ دسترسی"""

        # بررسی نیاز
        need = await self.db.get(NeedAd, need_id)
        if not need:
            raise HTTPException(status_code=404, detail="Need not found")

        # آپلود فایل
        upload_data = FileUpload(
            title=file.filename,
            description=description,
            access_level="sensitive" if encrypt else "protected",
            entity_type="need_ad",
            entity_id=need_id,
            tags=[purpose.value, "need_attachment"]
        )

        file_attachment = await self.file_service.upload_file(
            file, upload_data, user, encrypt_sensitive=encrypt
        )

        # ایجاد رکورد ارتباط
        need_attachment = NeedAttachment(
            need_id=need_id,
            file_id=file_attachment.id,
            purpose=purpose,
            title=file.filename,
            description=description,
            is_public=is_public,
            access_log_enabled=True
        )

        self.db.add(need_attachment)
        await self.db.commit()
        await self.db.refresh(need_attachment)

        return need_attachment

    async def get_attachments(
        self,
        need_id: int,
        user: Optional[User] = None,
        include_private: bool = False
    ) -> List[NeedAttachment]:
        """دریافت فایل‌های یک نیاز با کنترل دسترسی"""

        query = select(NeedAttachment).where(NeedAttachment.need_id == need_id)

        if not include_private:
            query = query.where(NeedAttachment.is_public == True)

        result = await self.db.execute(query)
        attachments = result.scalars().all()

        # فیلتر دسترسی
        filtered = []
        for attachment in attachments:
            if await self._can_access_attachment(attachment, user):
                filtered.append(attachment)

        return filtered

    async def log_access(
        self,
        attachment_id: int,
        user: Optional[User],
        action: str = "view"
    ):
        """لاگ دسترسی به فایل حساس"""
        attachment = await self.db.get(NeedAttachment, attachment_id)
        if not attachment or not attachment.access_log_enabled:
            return

        # به‌روزرسانی آمار
        attachment.access_count += 1
        attachment.last_accessed_at = datetime.utcnow()
        self.db.add(attachment)

        # ایجاد لاگ
        log = FileAccessLog(
            file_id=attachment.file_id,
            user_id=user.id if user else None,
            action=action,
            ip_address="0.0.0.0",  # از request
            user_agent="system",  # از request
            accessed_via="api",
            success=True
        )
        self.db.add(log)
        await self.db.commit()

    async def _can_access_attachment(
        self,
        attachment: NeedAttachment,
        user: Optional[User]
    ) -> bool:
        """بررسی دسترسی به فایل"""
        if attachment.is_public:
            return True

        if not user:
            return False

        user_roles = [r.key for r in user.roles]

        # ادمین/مدیر
        if "ADMIN" in user_roles or "CHARITY_MANAGER" in user_roles:
            return True

        # مالک نیاز
        need = await self.db.get(NeedAd, attachment.need_id)
        if need and need.needy_user_id == user.id:
            return True

        return False