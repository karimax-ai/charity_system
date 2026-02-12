# services/file_service.py
import os
import hashlib
import mimetypes
from pathlib import Path
from typing import Optional, List, Dict, Any, BinaryIO, Tuple
from datetime import datetime, timedelta
import aiofiles
from fastapi import UploadFile, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc
import uuid
import secrets
from cryptography.fernet import Fernet

from models.file_attachment import FileAttachment, FileType, FileAccessLevel
from models.file_access_log import FileAccessLog
from models.user import User
from schemas.file import FileUpload, FileFilter, FileUpdate


class FileService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.storage_path = os.getenv("FILE_STORAGE_PATH", "./uploads")
        self.max_file_size = 100 * 1024 * 1024  # 100MB
        self.allowed_mime_types = {
            "image": ["image/jpeg", "image/png", "image/gif", "image/webp"],
            "document": [
                "application/pdf",
                "application/msword",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "text/plain",
                "application/vnd.ms-excel",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ]
        }

        # ایجاد پوشه ذخیره‌سازی
        Path(self.storage_path).mkdir(parents=True, exist_ok=True)

        # کلید رمزنگاری (در پروژه واقعی از مدیریت کلید استفاده کن)
        self.encryption_key = Fernet.generate_key()
        self.cipher = Fernet(self.encryption_key)

    async def upload_file(
            self,
            file: UploadFile,
            upload_data: FileUpload,
            user: User,
            encrypt_sensitive: bool = True
    ) -> FileAttachment:
        """آپلود و ذخیره فایل جدید"""

        # بررسی حجم فایل
        content = await file.read()
        await file.seek(0)

        if len(content) > self.max_file_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File size exceeds limit: {self.max_file_size // (1024 * 1024)}MB"
            )

        # بررسی نوع فایل
        mime_type = file.content_type or mimetypes.guess_type(file.filename)[0] or "application/octet-stream"
        file_type = self._get_file_type(mime_type, file.filename)

        if not self._is_mime_type_allowed(mime_type, file_type):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"File type {mime_type} is not allowed"
            )

        # محاسبه hash فایل
        file_hash = self._calculate_file_hash(content)

        # بررسی تکراری نبودن فایل
        existing = await self.db.execute(
            select(FileAttachment).where(FileAttachment.file_hash == file_hash)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="File already exists"
            )

        # نام یکتا برای ذخیره‌سازی
        file_ext = Path(file.filename).suffix or self._get_extension_from_mime(mime_type)
        stored_filename = f"{uuid.uuid4().hex}{file_ext}"
        storage_path = self._get_storage_path(file_type, stored_filename)

        # رمزنگاری اگر فایل حساس است
        if encrypt_sensitive and upload_data.access_level == FileAccessLevel.SENSITIVE:
            content = self._encrypt_content(content)

        # ذخیره فایل
        await self._save_file(storage_path, content)

        # ایجاد رکورد در دیتابیس
        file_attachment = FileAttachment(
            original_filename=file.filename,
            stored_filename=stored_filename,
            file_type=file_type,
            mime_type=mime_type,
            file_size=len(content),
            file_hash=file_hash,
            storage_path=storage_path,
            access_level=upload_data.access_level,
            is_encrypted=(encrypt_sensitive and upload_data.access_level == FileAccessLevel.SENSITIVE),
            encryption_key_id=self.encryption_key.decode() if encrypt_sensitive else None,
            uploaded_by=user.id,
            entity_type=upload_data.entity_type,
            entity_id=upload_data.entity_id,
            title=upload_data.title or Path(file.filename).stem,
            description=upload_data.description,
            tags=upload_data.tags,
            expires_at=upload_data.expires_at
        )

        self.db.add(file_attachment)
        await self.db.commit()
        await self.db.refresh(file_attachment)

        # ثبت لاگ
        await self._log_file_access(
            file_attachment.id,
            user.id,
            "upload",
            success=True
        )

        return file_attachment

    async def download_file(
            self,
            file_id: int,
            user: Optional[User] = None,
            check_permission: bool = True
    ) -> Tuple[FileAttachment, bytes]:
        """دانلود فایل با بررسی دسترسی"""

        file_attachment = await self._get_file(file_id)

        # بررسی دسترسی
        if check_permission:
            if not await self._check_file_access(file_attachment, user):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to this file"
                )

        # خواندن فایل از storage
        content = await self._read_file(file_attachment.storage_path)

        # رمزگشایی اگر رمزنگاری شده
        if file_attachment.is_encrypted:
            try:
                content = self._decrypt_content(content)
            except Exception as e:
                await self._log_file_access(
                    file_id,
                    user.id if user else None,
                    "download",
                    success=False,
                    error_message=f"Decryption failed: {str(e)}"
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="File decryption failed"
                )

        # به‌روزرسانی آمار
        file_attachment.download_count += 1
        file_attachment.last_accessed_at = datetime.utcnow()
        self.db.add(file_attachment)
        await self.db.commit()

        # ثبت لاگ
        await self._log_file_access(
            file_id,
            user.id if user else None,
            "download",
            success=True
        )

        return file_attachment, content

    async def get_file_info(
            self,
            file_id: int,
            user: Optional[User] = None
    ) -> FileAttachment:
        """دریافت اطلاعات فایل"""

        file_attachment = await self._get_file(file_id)

        # بررسی دسترسی برای مشاهده اطلاعات
        if not await self._check_file_access(file_attachment, user, view_only=True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to file information"
            )

        # به‌روزرسانی آمار بازدید
        file_attachment.view_count += 1
        file_attachment.last_accessed_at = datetime.utcnow()
        self.db.add(file_attachment)
        await self.db.commit()

        # ثبت لاگ
        await self._log_file_access(
            file_id,
            user.id if user else None,
            "view",
            success=True
        )

        return file_attachment

    async def update_file(
            self,
            file_id: int,
            update_data: FileUpdate,
            user: User
    ) -> FileAttachment:
        """ویرایش اطلاعات فایل"""

        file_attachment = await self._get_file(file_id)

        # بررسی مالکیت یا دسترسی ادمین
        if not await self._check_file_ownership(file_attachment, user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this file"
            )

        # به‌روزرسانی فیلدها
        for key, value in update_data.dict(exclude_unset=True).items():
            if value is not None:
                setattr(file_attachment, key, value)

        self.db.add(file_attachment)
        await self.db.commit()
        await self.db.refresh(file_attachment)

        # ثبت لاگ
        await self._log_file_access(
            file_id,
            user.id,
            "update",
            success=True,
            data={"fields_updated": list(update_data.dict(exclude_unset=True).keys())}
        )

        return file_attachment

    async def delete_file(
            self,
            file_id: int,
            user: User,
            soft_delete: bool = True
    ) -> Dict[str, Any]:
        """حذف فایل (soft یا hard delete)"""

        file_attachment = await self._get_file(file_id)

        # بررسی مالکیت یا دسترسی ادمین
        if not await self._check_file_ownership(file_attachment, user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this file"
            )

        if soft_delete:
            # soft delete
            file_attachment.is_active = False
            self.db.add(file_attachment)
            await self.db.commit()

            result = {
                "success": True,
                "message": "File soft deleted successfully",
                "file_id": file_id,
                "soft_delete": True
            }
        else:
            # hard delete - حذف فایل فیزیکی و رکورد دیتابیس
            try:
                # حذف فایل فیزیکی
                await self._delete_physical_file(file_attachment.storage_path)

                # حذف رکورد دیتابیس
                await self.db.delete(file_attachment)
                await self.db.commit()

                result = {
                    "success": True,
                    "message": "File permanently deleted",
                    "file_id": file_id,
                    "soft_delete": False
                }
            except Exception as e:
                await self._log_file_access(
                    file_id,
                    user.id,
                    "delete",
                    success=False,
                    error_message=str(e)
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to delete file: {str(e)}"
                )

        # ثبت لاگ
        await self._log_file_access(
            file_id,
            user.id,
            "delete",
            success=True,
            data={"soft_delete": soft_delete}
        )

        return result

    async def list_files(
            self,
            filters: FileFilter,
            user: Optional[User] = None,
            page: int = 1,
            limit: int = 20
    ) -> Dict[str, Any]:
        """لیست فایل‌ها با فیلتر"""

        query = select(FileAttachment).where(FileAttachment.is_active == True)

        # اعمال فیلترها
        conditions = []

        if filters.file_type:
            conditions.append(FileAttachment.file_type == filters.file_type)

        if filters.access_level:
            conditions.append(FileAttachment.access_level == filters.access_level)

        if filters.entity_type:
            conditions.append(FileAttachment.entity_type == filters.entity_type)

        if filters.entity_id:
            conditions.append(FileAttachment.entity_id == filters.entity_id)

        if filters.uploaded_by:
            conditions.append(FileAttachment.uploaded_by == filters.uploaded_by)

        if filters.min_size:
            conditions.append(FileAttachment.file_size >= filters.min_size)

        if filters.max_size:
            conditions.append(FileAttachment.file_size <= filters.max_size)

        if filters.start_date:
            conditions.append(FileAttachment.uploaded_at >= filters.start_date)

        if filters.end_date:
            conditions.append(FileAttachment.uploaded_at <= filters.end_date)

        if filters.search_text:
            conditions.append(
                or_(
                    FileAttachment.original_filename.ilike(f"%{filters.search_text}%"),
                    FileAttachment.title.ilike(f"%{filters.search_text}%"),
                    FileAttachment.description.ilike(f"%{filters.search_text}%")
                )
            )

        if filters.tags:
            # جستجو در فیلد JSON tags
            for tag in filters.tags:
                conditions.append(FileAttachment.tags.contains([tag]))

        # فیلترهای دسترسی
        if user:
            user_roles = [r.key for r in user.roles]
            is_admin = "ADMIN" in user_roles or "CHARITY_MANAGER" in user_roles

            if not is_admin:
                # کاربران عادی فقط فایل‌های عمومی، محافظت‌شده یا فایل‌های خودشان را می‌بینند
                access_conditions = [
                    FileAttachment.access_level.in_([FileAccessLevel.PUBLIC, FileAccessLevel.PROTECTED]),
                    FileAttachment.uploaded_by == user.id
                ]

                # اگر کاربر نیازمند است، فایل‌های private خودش را هم می‌بیند
                if "NEEDY" in user_roles:
                    access_conditions.append(
                        and_(
                            FileAttachment.access_level == FileAccessLevel.PRIVATE,
                            FileAttachment.uploaded_by == user.id
                        )
                    )

                conditions.append(or_(*access_conditions))
        else:
            # کاربران مهمان فقط فایل‌های عمومی
            conditions.append(FileAttachment.access_level == FileAccessLevel.PUBLIC)

        if conditions:
            query = query.where(and_(*conditions))

        # مرتب‌سازی
        sort_column = getattr(FileAttachment, filters.sort_by, FileAttachment.uploaded_at)
        if filters.sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # شمارش کل
        total_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(total_query)

        # صفحه‌بندی
        offset = (page - 1) * limit
        query = query.offset(offset).limit(limit)

        # اجرای کوئری
        result = await self.db.execute(query)
        files = result.scalars().all()

        return {
            "items": files,
            "total": total or 0,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit if total > 0 else 0
        }

    async def get_file_stats(
            self,
            user: Optional[User] = None,
            entity_type: Optional[str] = None,
            entity_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """آمار فایل‌ها"""

        query = select(FileAttachment).where(FileAttachment.is_active == True)

        # فیلترهای اختیاری
        if entity_type:
            query = query.where(FileAttachment.entity_type == entity_type)
        if entity_id:
            query = query.where(FileAttachment.entity_id == entity_id)

        # فیلتر دسترسی
        if user:
            if not await self._is_admin(user):
                query = query.where(
                    or_(
                        FileAttachment.access_level.in_([FileAccessLevel.PUBLIC, FileAccessLevel.PROTECTED]),
                        FileAttachment.uploaded_by == user.id
                    )
                )

        result = await self.db.execute(query)
        files = result.scalars().all()

        # محاسبات آماری
        stats = {
            "total_files": len(files),
            "total_size": sum(f.file_size or 0 for f in files),
            "by_file_type": {},
            "by_access_level": {},
            "by_entity_type": {}
        }

        for file in files:
            # شمارش بر اساس نوع فایل
            stats["by_file_type"][file.file_type.value] = stats["by_file_type"].get(file.file_type.value, 0) + 1

            # شمارش بر اساس سطح دسترسی
            stats["by_access_level"][file.access_level.value] = stats["by_access_level"].get(file.access_level.value,
                                                                                             0) + 1

            # شمارش بر اساس موجودیت مرتبط
            if file.entity_type:
                stats["by_entity_type"][file.entity_type] = stats["by_entity_type"].get(file.entity_type, 0) + 1

        # فایل‌های اخیر
        recent_query = query.order_by(FileAttachment.uploaded_at.desc()).limit(10)
        recent_result = await self.db.execute(recent_query)
        stats["recent_uploads"] = recent_result.scalars().all()

        return stats

    async def get_file_access_logs(
            self,
            file_id: int,
            user: User,
            page: int = 1,
            limit: int = 20
    ) -> Dict[str, Any]:
        """دریافت لاگ دسترسی به فایل"""

        file_attachment = await self._get_file(file_id)

        # بررسی دسترسی - فقط مالک یا ادمین
        if not await self._check_file_ownership(file_attachment, user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view access logs"
            )

        query = select(FileAccessLog).where(FileAccessLog.file_id == file_id)

        # شمارش کل
        total_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(total_query)

        # صفحه‌بندی
        offset = (page - 1) * limit
        query = query.order_by(FileAccessLog.accessed_at.desc())
        query = query.offset(offset).limit(limit)

        result = await self.db.execute(query)
        logs = result.scalars().all()

        return {
            "file_id": file_id,
            "file_name": file_attachment.original_filename,
            "items": logs,
            "total": total or 0,
            "page": page,
            "limit": limit
        }

    async def cleanup_expired_files(self, user: User) -> Dict[str, Any]:
        """پاک‌سازی فایل‌های منقضی شده"""

        if not await self._is_admin(user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can cleanup files"
            )

        # یافتن فایل‌های منقضی شده
        query = select(FileAttachment).where(
            and_(
                FileAttachment.expires_at.is_not(None),
                FileAttachment.expires_at < datetime.utcnow(),
                FileAttachment.is_active == True
            )
        )

        result = await self.db.execute(query)
        expired_files = result.scalars().all()

        deleted_count = 0
        errors = []

        for file in expired_files:
            try:
                # حذف فایل فیزیکی
                await self._delete_physical_file(file.storage_path)

                # حذف رکورد دیتابیس
                await self.db.delete(file)

                # ثبت لاگ
                await self._log_file_access(
                    file.id,
                    user.id,
                    "auto_delete",
                    success=True,
                    data={"reason": "file_expired"}
                )

                deleted_count += 1

            except Exception as e:
                errors.append({
                    "file_id": file.id,
                    "filename": file.original_filename,
                    "error": str(e)
                })

        await self.db.commit()

        return {
            "deleted_count": deleted_count,
            "errors": errors,
            "message": f"Cleaned up {deleted_count} expired files"
        }

    # ---------- Helper Methods ----------

    async def _get_file(self, file_id: int) -> FileAttachment:
        """دریافت فایل با بررسی وجود"""
        file = await self.db.get(FileAttachment, file_id)
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
        return file

    async def _check_file_access(
            self,
            file: FileAttachment,
            user: Optional[User],
            view_only: bool = False
    ) -> bool:
        """بررسی دسترسی به فایل"""

        # فایل‌های عمومی
        if file.access_level == FileAccessLevel.PUBLIC:
            return True

        # اگر کاربر لاگین نکرده
        if not user:
            return False

        # مالک فایل همیشه دسترسی دارد
        if file.uploaded_by == user.id:
            return True

        # ادمین و مدیران خیریه
        user_roles = [r.key for r in user.roles]
        if "ADMIN" in user_roles or "CHARITY_MANAGER" in user_roles:
            return True

        # فایل‌های محافظت‌شده برای کاربران ثبت‌نام‌شده
        if file.access_level == FileAccessLevel.PROTECTED and user.is_active:
            return True

        # فایل‌های private فقط برای مالک
        if file.access_level == FileAccessLevel.PRIVATE:
            # برای view-only ممکن است اجازه دهیم
            if view_only and "NEEDY" in user_roles:
                # نیازمند می‌تواند فایل‌های private مربوط به نیازش را ببیند
                # اینجا می‌توان منطق خاصی اضافه کرد
                pass
            return False

        # فایل‌های حساس فقط برای ادمین/مدیر
        if file.access_level == FileAccessLevel.SENSITIVE:
            return False

        return False

    async def _check_file_ownership(self, file: FileAttachment, user: User) -> bool:
        """بررسی مالکیت فایل"""
        user_roles = [r.key for r in user.roles]
        return file.uploaded_by == user.id or "ADMIN" in user_roles

    async def _is_admin(self, user: User) -> bool:
        """بررسی ادمین بودن"""
        user_roles = [r.key for r in user.roles]
        return "ADMIN" in user_roles or "CHARITY_MANAGER" in user_roles

    async def _log_file_access(
            self,
            file_id: int,
            user_id: Optional[int],
            action: str,
            success: bool = True,
            error_message: Optional[str] = None,
            data: Optional[Dict] = None
    ):
        """ثبت لاگ دسترسی"""

        # در حالت واقعی IP و User-Agent از request می‌آیند
        log = FileAccessLog(
            file_id=file_id,
            user_id=user_id,
            action=action,
            ip_address="0.0.0.0",  # باید از request گرفته شود
            user_agent="system",  # باید از request گرفته شود
            accessed_via="api",
            success=success,
            error_message=error_message
        )

        self.db.add(log)
        await self.db.commit()

    def _get_file_type(self, mime_type: str, filename: str) -> FileType:
        """تعیین نوع فایل"""
        if mime_type.startswith("image/"):
            return FileType.IMAGE
        elif mime_type == "application/pdf":
            return FileType.PDF
        elif any(mime_type.startswith(prefix) for prefix in ["application/", "text/"]):
            return FileType.DOCUMENT
        else:
            return FileType.OTHER

    def _is_mime_type_allowed(self, mime_type: str, file_type: FileType) -> bool:
        """بررسی مجاز بودن نوع فایل"""
        if file_type == FileType.IMAGE:
            return mime_type in self.allowed_mime_types["image"]
        elif file_type == FileType.DOCUMENT or file_type == FileType.PDF:
            return mime_type in self.allowed_mime_types["document"]
        elif file_type == FileType.OTHER:
            # فایل‌های دیگر با احتیاط
            return True
        return False

    def _calculate_file_hash(self, content: bytes) -> str:
        """محاسبه هش فایل"""
        return hashlib.sha256(content).hexdigest()

    def _get_storage_path(self, file_type: FileType, filename: str) -> str:
        """تعیین مسیر ذخیره‌سازی"""
        # ایجاد پوشه بر اساس نوع و تاریخ
        date_str = datetime.utcnow().strftime("%Y/%m/%d")
        type_folder = file_type.value
        full_path = Path(self.storage_path) / type_folder / date_str

        # ایجاد پوشه‌ها اگر وجود ندارند
        full_path.mkdir(parents=True, exist_ok=True)

        return str(full_path / filename)

    def _get_extension_from_mime(self, mime_type: str) -> str:
        """گرفتن پسوند از mime type"""
        ext = mimetypes.guess_extension(mime_type)
        return ext or ".bin"

    async def _save_file(self, path: str, content: bytes):
        """ذخیره فایل در storage"""
        path_obj = Path(path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(path, "wb") as f:
            await f.write(content)

    async def _read_file(self, path: str) -> bytes:
        """خواندن فایل از storage"""
        try:
            async with aiofiles.open(path, "rb") as f:
                return await f.read()
        except FileNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found in storage"
            )

    async def _delete_physical_file(self, path: str):
        """حذف فایل فیزیکی"""
        try:
            path_obj = Path(path)
            if path_obj.exists():
                path_obj.unlink()
        except Exception as e:
            raise Exception(f"Failed to delete physical file: {str(e)}")

    def _encrypt_content(self, content: bytes) -> bytes:
        """رمزنگاری محتوای فایل"""
        return self.cipher.encrypt(content)

    def _decrypt_content(self, encrypted_content: bytes) -> bytes:
        """رمزگشایی محتوای فایل"""
        return self.cipher.decrypt(encrypted_content)