# app/api/v1/endpoints/user.py
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from typing import Optional, List, Dict, Any
from datetime import datetime

from core.database import get_db
from core.permissions import get_current_user, require_roles
from models.user import User, UserStatus
from schemas.user import (
    UserRead, UserDetail, UserUpdate, ChangePassword,
    UserFilter, VerifyEmail, VerifyPhone
)
from services.user import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserDetail)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """پروفایل کاربر جاری"""
    service = UserService(db)
    return await service.get_user_detail(current_user.id, current_user)


@router.put("/me", response_model=UserRead)
async def update_current_user(
    update_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """ویرایش پروفایل کاربر جاری"""
    service = UserService(db)
    return await service.update_user(current_user.id, update_data, current_user)


@router.post("/me/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """آپلود عکس پروفایل"""
    service = UserService(db)
    return await service.upload_avatar(current_user.id, file, current_user)


@router.post("/change-password")
async def change_password(
    password_data: ChangePassword,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """تغییر رمز عبور"""
    service = UserService(db)
    return await service.change_password(current_user, password_data)


@router.post("/verify-email")
async def verify_email(
    verify_data: VerifyEmail,
    db: AsyncSession = Depends(get_db)
):
    """تأیید ایمیل"""
    service = UserService(db)
    return await service.verify_email(verify_data.token)


@router.post("/verify-phone")
async def verify_phone(
    verify_data: VerifyPhone,
    db: AsyncSession = Depends(get_db)
):
    """تأیید شماره موبایل"""
    service = UserService(db)
    return await service.verify_phone(verify_data.phone, verify_data.code)


@router.get("/{user_id}", response_model=UserDetail)
async def get_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """دریافت اطلاعات کاربر (فقط خود کاربر و ادمین)"""
    service = UserService(db)
    return await service.get_user_detail(user_id, current_user)


@router.get("/", response_model=Dict[str, Any])
async def list_users(
    status: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    is_verified: Optional[bool] = Query(None),
    search_text: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    province: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_roles("ADMIN")),
    db: AsyncSession = Depends(get_db)
):
    """لیست کاربران (فقط ادمین)"""
    filters = UserFilter(
        status=status,
        role=role,
        is_verified=is_verified,
        search_text=search_text,
        city=city,
        province=province
    )
    service = UserService(db)
    return await service.list_users(filters, page, limit)


@router.put("/{user_id}/status")
async def update_user_status(
    user_id: int,
    status: UserStatus,
    reason: Optional[str] = None,
    current_user: User = Depends(require_roles("ADMIN")),
    db: AsyncSession = Depends(get_db)
):
    """تغییر وضعیت کاربر (فقط ادمین)"""
    service = UserService(db)
    return await service.update_user_status(user_id, status, reason, current_user)


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    hard_delete: bool = False,
    current_user: User = Depends(require_roles("ADMIN")),
    db: AsyncSession = Depends(get_db)
):
    """حذف کاربر (فقط ادمین)"""
    service = UserService(db)
    return await service.delete_user(user_id, hard_delete, current_user)