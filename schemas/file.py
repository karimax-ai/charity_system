# schemas/file.py
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import re


class FileType(str, Enum):
    IMAGE = "image"
    DOCUMENT = "document"
    PDF = "pdf"
    OTHER = "other"


class FileAccessLevel(str, Enum):
    PUBLIC = "public"
    PROTECTED = "protected"
    PRIVATE = "private"
    SENSITIVE = "sensitive"


# ---------- ایجاد فایل ----------
class FileUpload(BaseModel):
    """داده‌های آپلود فایل"""
    title: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    access_level: FileAccessLevel = FileAccessLevel.PROTECTED
    entity_type: str  # need_ad, user, charity, etc.
    entity_id: int
    tags: List[str] = []
    expires_at: Optional[datetime] = None


class MultiFileUpload(BaseModel):
    """آپلود چند فایل"""
    files: List[FileUpload]
    compress: bool = False  # فشرده‌سازی خودکار


# ---------- به‌روزرسانی فایل ----------
class FileUpdate(BaseModel):
    """ویرایش اطلاعات فایل"""
    title: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    access_level: Optional[FileAccessLevel] = None
    tags: Optional[List[str]] = None
    is_active: Optional[bool] = None


# ---------- جستجو و فیلتر ----------
class FileFilter(BaseModel):
    """فیلترهای جستجوی فایل‌ها"""
    file_type: Optional[FileType] = None
    access_level: Optional[FileAccessLevel] = None
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    uploaded_by: Optional[int] = None
    min_size: Optional[int] = None  # به بایت
    max_size: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    search_text: Optional[str] = None
    tags: Optional[List[str]] = None
    sort_by: str = "uploaded_at"
    sort_order: str = "desc"


# ---------- خروجی فایل ----------
class FileRead(BaseModel):
    """خواندن اطلاعات فایل"""
    id: int
    uuid: str
    original_filename: str
    file_type: FileType
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    access_level: FileAccessLevel
    uploaded_by: int
    uploader_name: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = []
    download_count: int = 0
    view_count: int = 0
    is_active: bool = True
    is_encrypted: bool = False
    uploaded_at: datetime
    last_accessed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    download_url: Optional[str] = None  # برای دسترسی سریع
    thumbnail_url: Optional[str] = None  # برای تصاویر

    class Config:
        orm_mode = True


class FileDetail(FileRead):
    """جزئیات کامل فایل (برای مالک یا ادمین)"""
    stored_filename: str
    storage_path: Optional[str] = None
    storage_provider: str = "local"
    file_hash: Optional[str] = None
    encryption_key_id: Optional[str] = None
    access_logs_count: int = 0

    class Config:
        orm_mode = True


# ---------- آمار فایل‌ها ----------
class FileStats(BaseModel):
    """آمار فایل‌ها"""
    total_files: int
    total_size: int  # مجموع حجم به بایت
    by_file_type: Dict[str, int]
    by_access_level: Dict[str, int]
    by_entity_type: Dict[str, int]
    recent_uploads: List[FileRead] = []

    class Config:
        orm_mode = True