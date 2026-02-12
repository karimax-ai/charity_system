# app/services/need_log_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import Request

from models.file_access_log import FileAccessLog
from models.need_attachment import NeedAttachment
from models.user import User


class NeedLogService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_attachment_access(
            self,
            attachment_id: int,
            user: Optional[User],
            request: Request,
            action: str = "view"
    ) -> FileAccessLog:
        """ثبت دسترسی به فایل پیوست نیاز"""

        attachment = await self.db.get(NeedAttachment, attachment_id)
        if not attachment:
            raise ValueError("Attachment not found")

        log = FileAccessLog(
            file_id=attachment.file_id,
            user_id=user.id if user else None,
            action=action,
            ip_address=request.client.host if request.client else "0.0.0.0",
            user_agent=request.headers.get("user-agent", ""),
            accessed_via="api",
            success=True
        )

        self.db.add(log)

        # به‌روزرسانی آمار
        attachment.access_count += 1
        attachment.last_accessed_at = datetime.utcnow()
        self.db.add(attachment)

        await self.db.commit()
        await self.db.refresh(log)

        return log

    async def get_attachment_logs(
            self,
            attachment_id: int,
            page: int = 1,
            limit: int = 20
    ) -> Dict[str, Any]:
        """دریافت لاگ دسترسی به یک فایل"""

        query = select(FileAccessLog).where(
            FileAccessLog.file_id == FileAccessLog.file_id  # TODO: fix this
        ).order_by(FileAccessLog.accessed_at.desc())

        # TODO: complete this method
        return {
            "items": [],
            "total": 0,
            "page": page,
            "limit": limit
        }

    async def get_need_access_logs(
            self,
            need_id: int,
            admin_user: User,
            page: int = 1,
            limit: int = 20
    ) -> Dict[str, Any]:
        """دریافت همه لاگ‌های دسترسی به فایل‌های یک نیاز (فقط مدیر)"""

        # TODO: complete this method
        return {
            "items": [],
            "total": 0,
            "page": page,
            "limit": limit
        }