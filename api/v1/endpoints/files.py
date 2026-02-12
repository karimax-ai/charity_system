# api/v1/endpoints/files.py
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File as FastAPIFile, Form, Query, BackgroundTasks, \
    status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any
from datetime import datetime
import mimetypes
import os

from core.database import get_db
from core.permissions import get_current_user, require_roles
from models.user import User
from schemas.file import (
    FileRead, FileDetail, FileFilter, FileUpload,
    FileUpdate, MultiFileUpload, FileStats
)
from services.file_service import FileService

router = APIRouter()


# ---------- آپلود فایل ----------
@router.post("/upload", response_model=FileRead)
async def upload_file(
        file: UploadFile = FastAPIFile(...),
        title: Optional[str] = Form(None),
        description: Optional[str] = Form(None),
        access_level: str = Form("protected"),
        entity_type: str = Form(...),
        entity_id: int = Form(...),
        tags: str = Form("[]"),  # JSON string
        expires_at: Optional[datetime] = Form(None),
        encrypt_sensitive: bool = Form(True),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """آپلود یک فایل"""
    # تبدیل tags از JSON string به list
    import json
    try:
        tags_list = json.loads(tags) if tags else []
    except json.JSONDecodeError:
        tags_list = []

    upload_data = FileUpload(
        title=title,
        description=description,
        access_level=access_level,
        entity_type=entity_type,
        entity_id=entity_id,
        tags=tags_list,
        expires_at=expires_at
    )

    service = FileService(db)
    file_attachment = await service.upload_file(
        file, upload_data, current_user, encrypt_sensitive
    )

    return file_attachment


@router.post("/upload/multiple", response_model=List[FileRead])
async def upload_multiple_files(
        files: List[UploadFile] = FastAPIFile(...),
        entity_type: str = Form(...),
        entity_id: int = Form(...),
        access_level: str = Form("protected"),
        compress: bool = Form(False),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """آپلود چندین فایل"""
    service = FileService(db)
    uploaded_files = []

    for file in files:
        upload_data = FileUpload(
            title=file.filename,
            entity_type=entity_type,
            entity_id=entity_id,
            access_level=access_level
        )

        try:
            file_attachment = await service.upload_file(
                file, upload_data, current_user
            )
            uploaded_files.append(file_attachment)
        except Exception as e:
            # ادامه با فایل بعدی در صورت خطا
            print(f"Failed to upload {file.filename}: {str(e)}")
            continue

    return uploaded_files


# ---------- دانلود فایل ----------
@router.get("/download/{file_id}")
async def download_file(
        file_id: int,
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """دانلود فایل"""
    service = FileService(db)
    file_attachment, content = await service.download_file(file_id, current_user)

    # تعیین Content-Type
    mime_type = file_attachment.mime_type or "application/octet-stream"

    # برای تصاویر و PDF می‌توان نمایش در مرورگر داد
    if mime_type.startswith("image/") or mime_type == "application/pdf":
        media_type = mime_type
    else:
        media_type = "application/octet-stream"

    return StreamingResponse(
        iter([content]),
        media_type=media_type,
        headers={
            "Content-Disposition": f"inline; filename=\"{file_attachment.original_filename}\"",
            "Content-Length": str(file_attachment.file_size)
        }
    )


@router.get("/view/{file_id}")
async def view_file(
        file_id: int,
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """مشاهده فایل (برای تصاویر و PDF)"""
    service = FileService(db)
    file_attachment, content = await service.download_file(file_id, current_user)

    # فقط برای تصاویر و PDF اجازه مشاهده مستقیم
    mime_type = file_attachment.mime_type or "application/octet-stream"
    if not (mime_type.startswith("image/") or mime_type == "application/pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File cannot be viewed directly"
        )

    return StreamingResponse(
        iter([content]),
        media_type=mime_type,
        headers={
            "Content-Disposition": f"inline; filename=\"{file_attachment.original_filename}\"",
            "Content-Length": str(file_attachment.file_size)
        }
    )


# ---------- دریافت اطلاعات ----------
@router.get("/{file_id}", response_model=FileDetail)
async def get_file(
        file_id: int,
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """دریافت اطلاعات یک فایل"""
    service = FileService(db)
    file_attachment = await service.get_file_info(file_id, current_user)
    return file_attachment


@router.get("/", response_model=Dict[str, Any])
async def list_files(
        file_type: Optional[str] = Query(None),
        access_level: Optional[str] = Query(None),
        entity_type: Optional[str] = Query(None),
        entity_id: Optional[int] = Query(None),
        uploaded_by: Optional[int] = Query(None),
        min_size: Optional[int] = Query(None),
        max_size: Optional[int] = Query(None),
        start_date: Optional[datetime] = Query(None),
        end_date: Optional[datetime] = Query(None),
        search_text: Optional[str] = Query(None),
        tags: Optional[str] = Query(None),
        sort_by: str = Query("uploaded_at"),
        sort_order: str = Query("desc"),
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """لیست فایل‌ها با فیلتر"""
    # تبدیل tags از query string
    tags_list = []
    if tags:
        tags_list = [tag.strip() for tag in tags.split(",")]

    filters = FileFilter(
        file_type=file_type,
        access_level=access_level,
        entity_type=entity_type,
        entity_id=entity_id,
        uploaded_by=uploaded_by,
        min_size=min_size,
        max_size=max_size,
        start_date=start_date,
        end_date=end_date,
        search_text=search_text,
        tags=tags_list,
        sort_by=sort_by,
        sort_order=sort_order
    )

    service = FileService(db)
    return await service.list_files(filters, current_user, page, limit)


# ---------- ویرایش فایل ----------
@router.put("/{file_id}", response_model=FileRead)
async def update_file(
        file_id: int,
        update_data: FileUpdate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """ویرایش اطلاعات فایل"""
    service = FileService(db)
    file_attachment = await service.update_file(file_id, update_data, current_user)
    return file_attachment


# ---------- حذف فایل ----------
@router.delete("/{file_id}")
async def delete_file(
        file_id: int,
        soft_delete: bool = Query(True),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """حذف فایل"""
    service = FileService(db)
    result = await service.delete_file(file_id, current_user, soft_delete)
    return result


# ---------- آمار و گزارش ----------
@router.get("/stats/summary", response_model=FileStats)
async def get_file_stats(
        entity_type: Optional[str] = Query(None),
        entity_id: Optional[int] = Query(None),
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """آمار فایل‌ها"""
    service = FileService(db)
    stats = await service.get_file_stats(current_user, entity_type, entity_id)
    return stats


@router.get("/{file_id}/access-logs")
async def get_file_access_logs(
        file_id: int,
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """لاگ دسترسی به فایل"""
    service = FileService(db)
    return await service.get_file_access_logs(file_id, current_user, page, limit)


# ---------- عملیات مدیریتی ----------
@router.post("/cleanup/expired")
async def cleanup_expired_files(
        current_user: User = Depends(require_roles("ADMIN")),
        db: AsyncSession = Depends(get_db)
):
    """پاک‌سازی فایل‌های منقضی شده (فقط ادمین)"""
    service = FileService(db)
    result = await service.cleanup_expired_files(current_user)
    return result


@router.post("/{file_id}/restore")
async def restore_file(
        file_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """بازیابی فایل soft-deleted"""
    service = FileService(db)
    file_attachment = await service._get_file(file_id)

    # بررسی مالکیت
    if not await service._check_file_ownership(file_attachment, current_user):
        raise HTTPException(status_code=403, detail="Not authorized")

    if file_attachment.is_active:
        raise HTTPException(status_code=400, detail="File is already active")

    file_attachment.is_active = True
    db.add(file_attachment)
    await db.commit()

    await service._log_file_access(
        file_id,
        current_user.id,
        "restore",
        success=True
    )

    return {"success": True, "message": "File restored successfully"}


# ---------- عملیات دسته‌ای ----------
@router.post("/batch/delete")
async def batch_delete_files(
        file_ids: List[int],
        soft_delete: bool = Query(True),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """حذف دسته‌ای فایل‌ها"""
    service = FileService(db)
    results = []

    for file_id in file_ids:
        try:
            result = await service.delete_file(file_id, current_user, soft_delete)
            results.append({
                "file_id": file_id,
                "success": True,
                "result": result
            })
        except Exception as e:
            results.append({
                "file_id": file_id,
                "success": False,
                "error": str(e)
            })

    return {
        "total": len(file_ids),
        "successful": len([r for r in results if r["success"]]),
        "failed": len([r for r in results if not r["success"]]),
        "results": results
    }


@router.post("/batch/update-access")
async def batch_update_access_level(
        file_ids: List[int],
        access_level: str,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """تغییر سطح دسترسی دسته‌ای"""
    from schemas.file import FileAccessLevel

    try:
        access_level_enum = FileAccessLevel(access_level)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid access level")

    service = FileService(db)
    results = []

    for file_id in file_ids:
        try:
            file_attachment = await service._get_file(file_id)

            # بررسی مالکیت
            if not await service._check_file_ownership(file_attachment, current_user):
                results.append({
                    "file_id": file_id,
                    "success": False,
                    "error": "Not authorized"
                })
                continue

            file_attachment.access_level = access_level_enum
            db.add(file_attachment)

            await service._log_file_access(
                file_id,
                current_user.id,
                "batch_update_access",
                success=True,
                data={"new_access_level": access_level}
            )

            results.append({
                "file_id": file_id,
                "success": True
            })

        except Exception as e:
            results.append({
                "file_id": file_id,
                "success": False,
                "error": str(e)
            })

    await db.commit()

    return {
        "total": len(file_ids),
        "updated": len([r for r in results if r["success"]]),
        "failed": len([r for r in results if not r["success"]]),
        "results": results
    }


# ---------- تولید thumbnail ----------
@router.get("/{file_id}/thumbnail")
async def get_file_thumbnail(
        file_id: int,
        width: int = Query(200, ge=50, le=1000),
        height: int = Query(200, ge=50, le=1000),
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """دریافت thumbnail برای تصاویر"""
    service = FileService(db)
    file_attachment = await service.get_file_info(file_id, current_user)

    # فقط برای تصاویر
    if not file_attachment.mime_type or not file_attachment.mime_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Thumbnail only available for images"
        )

    # در حالت واقعی، thumbnail تولید و کش می‌شود
    # اینجا فایل اصلی را برمی‌گردانیم
    _, content = await service.download_file(file_id, current_user)

    return StreamingResponse(
        iter([content]),
        media_type=file_attachment.mime_type,
        headers={
            "Content-Disposition": f"inline; filename=\"thumbnail_{file_attachment.original_filename}\""
        }
    )