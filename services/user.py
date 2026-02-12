# app/services/user_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from fastapi import HTTPException, UploadFile
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import secrets
import string
import uuid

from models.user import User, UserStatus
from models.role import Role
from core.security import hash_password, verify_password, create_access_token
from schemas.user import UserUpdate, ChangePassword, UserFilter
from services.file_service import FileService
from services.otp_service import OTPService


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------- دریافت اطلاعات کاربر ----------
    async def get_user_detail(self, user_id: int, current_user: User) -> Dict[str, Any]:
        """دریافت جزئیات کامل کاربر"""

        user = await self.db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # بررسی دسترسی
        if current_user.id != user_id and not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Not authorized")

        # تبدیل به دیکشنری
        user_dict = {
            "id": user.id,
            "uuid": user.uuid,
            "email": user.email,
            "phone": user.phone,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "full_name": user.full_name or f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username,
            "national_id": user.national_id,
            "gender": user.gender,
            "birth_date": user.birth_date,
            "avatar_url": user.avatar_url,
            "bio": user.bio,
            "address": user.address,
            "city": user.city,
            "province": user.province,
            "postal_code": user.postal_code,
            "website": user.website,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "status": user.status,
            "roles": [role.key for role in user.roles],
            "language": user.language,
            "theme": user.theme,
            "two_fa_enabled": user.two_fa_enabled,
            "social_links": user.social_links or {},
            "badges": user.badges or [],
            "badge_level": user.badge_level,
            "trust_score": user.trust_score or 0,
            "created_at": user.created_at,
        }

        # اطلاعات اضافی برای خود کاربر و ادمین
        if current_user.id == user_id or current_user.is_admin:
            user_dict.update({
                "email_verified_at": user.email_verified_at,
                "phone_verified_at": user.phone_verified_at,
                "last_login_at": user.last_login_at,
                "last_login_ip": user.last_login_ip,
                "total_donations": user.total_donations or 0,
                "donations_count": user.donations_count or 0,
                "total_sponsored": user.total_sponsored or 0,
                "sponsored_count": user.sponsored_count or 0,
                "total_needs": user.total_needs or 0,
                "completed_needs": user.completed_needs or 0,
                "settings": user.settings or {},
                "verified_at": user.verified_at,
                "verification_notes": user.verification_notes,
            })

        return user_dict

    # ---------- ویرایش پروفایل ----------
    async def update_user(
            self,
            user_id: int,
            update_data: UserUpdate,
            current_user: User
    ) -> User:
        """ویرایش اطلاعات کاربر"""

        if current_user.id != user_id and not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Not authorized")

        user = await self.db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # به‌روزرسانی فیلدها
        update_dict = update_data.dict(exclude_unset=True)

        # بررسی تکراری نبودن username
        if "username" in update_dict and update_dict["username"] != user.username:
            existing = await self.db.execute(
                select(User).where(User.username == update_dict["username"])
            )
            if existing.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="Username already taken")

        # بررسی تکراری نبودن phone
        if "phone" in update_dict and update_dict["phone"] != user.phone:
            existing = await self.db.execute(
                select(User).where(User.phone == update_dict["phone"])
            )
            if existing.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="Phone number already registered")

        # به‌روزرسانی full_name
        if "first_name" in update_dict or "last_name" in update_dict:
            first_name = update_dict.get("first_name", user.first_name)
            last_name = update_dict.get("last_name", user.last_name)
            user.full_name = f"{first_name or ''} {last_name or ''}".strip()

        for key, value in update_dict.items():
            setattr(user, key, value)

        user.updated_at = datetime.utcnow()
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        return user

    # ---------- آپلود عکس پروفایل ----------
    async def upload_avatar(
            self,
            user_id: int,
            file: UploadFile,
            current_user: User
    ) -> Dict[str, Any]:
        """آپلود عکس پروفایل"""

        if current_user.id != user_id and not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Not authorized")

        user = await self.db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # آپلود فایل
        file_service = FileService(self.db)
        from schemas.file import FileUpload

        upload_data = FileUpload(
            title=f"avatar_{user.id}",
            access_level="public",
            entity_type="user",
            entity_id=user.id,
            tags=["avatar"]
        )

        file_attachment = await file_service.upload_file(
            file, upload_data, current_user, encrypt_sensitive=False
        )

        # به‌روزرسانی avatar_url
        user.avatar_url = f"/api/v1/files/download/{file_attachment.id}"
        self.db.add(user)
        await self.db.commit()

        return {
            "success": True,
            "avatar_url": user.avatar_url,
            "message": "Avatar uploaded successfully"
        }

    # ---------- تغییر رمز عبور ----------
    async def change_password(
            self,
            user: User,
            password_data: ChangePassword
    ) -> Dict[str, Any]:
        """تغییر رمز عبور"""

        if not verify_password(password_data.old_password, user.hashed_password):
            raise HTTPException(status_code=400, detail="Current password is incorrect")

        user.hashed_password = hash_password(password_data.new_password)

        # باطل کردن تمام سشن‌ها
        user.refresh_token = None
        user.refresh_token_expires = None
        user.trusted_devices = []

        self.db.add(user)
        await self.db.commit()

        return {"message": "Password changed successfully"}

    # ---------- تأیید ایمیل ----------
    async def verify_email(self, token: str) -> Dict[str, Any]:
        """تأیید ایمیل با توکن"""

        result = await self.db.execute(
            select(User).where(User.email_verification_token == token)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=400, detail="Invalid verification token")

        user.is_verified = True
        user.email_verified_at = datetime.utcnow()
        user.email_verification_token = None

        self.db.add(user)
        await self.db.commit()

        return {"message": "Email verified successfully"}

    # ---------- تأیید شماره موبایل ----------
    async def verify_phone(self, phone: str, code: str) -> Dict[str, Any]:
        """تأیید شماره موبایل با کد OTP"""

        await OTPService.verify_otp(phone, code, purpose="verify_phone")

        result = await self.db.execute(
            select(User).where(User.phone == phone)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.phone_verified_at = datetime.utcnow()
        self.db.add(user)
        await self.db.commit()

        return {"message": "Phone verified successfully"}

    # ---------- لیست کاربران (ادمین) ----------
    async def list_users(
            self,
            filters: UserFilter,
            page: int = 1,
            limit: int = 20
    ) -> Dict[str, Any]:
        """لیست کاربران با فیلتر (فقط ادمین)"""

        query = select(User)

        conditions = []

        if filters.status:
            conditions.append(User.status == filters.status)

        if filters.is_verified is not None:
            conditions.append(User.is_verified == filters.is_verified)

        if filters.is_active is not None:
            conditions.append(User.is_active == filters.is_active)

        if filters.city:
            conditions.append(User.city.ilike(f"%{filters.city}%"))

        if filters.province:
            conditions.append(User.province.ilike(f"%{filters.province}%"))

        if filters.search_text:
            conditions.append(
                or_(
                    User.email.ilike(f"%{filters.search_text}%"),
                    User.username.ilike(f"%{filters.search_text}%"),
                    User.first_name.ilike(f"%{filters.search_text}%"),
                    User.last_name.ilike(f"%{filters.search_text}%"),
                    User.phone.ilike(f"%{filters.search_text}%")
                )
            )

        if filters.role:
            # فیلتر بر اساس نقش
            subquery = select(User.id).join(User.roles).where(Role.key == filters.role)
            conditions.append(User.id.in_(subquery))

        if filters.min_trust_score:
            conditions.append(User.trust_score >= filters.min_trust_score)

        if filters.has_badge:
            conditions.append(User.badges.contains([filters.has_badge]))

        if conditions:
            query = query.where(and_(*conditions))

        # شمارش کل
        total_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(total_query)

        # صفحه‌بندی
        offset = (page - 1) * limit
        query = query.order_by(User.created_at.desc())
        query = query.offset(offset).limit(limit)

        result = await self.db.execute(query)
        users = result.scalars().all()

        # تبدیل به فرمت خروجی
        user_list = []
        for user in users:
            user_list.append({
                "id": user.id,
                "uuid": user.uuid,
                "email": user.email,
                "phone": user.phone,
                "username": user.username,
                "full_name": user.full_name or f"{user.first_name or ''} {user.last_name or ''}".strip(),
                "avatar_url": user.avatar_url,
                "is_active": user.is_active,
                "is_verified": user.is_verified,
                "status": user.status,
                "roles": [role.key for role in user.roles],
                "badge_level": user.badge_level,
                "trust_score": user.trust_score,
                "created_at": user.created_at,
                "last_login_at": user.last_login_at,
            })

        return {
            "items": user_list,
            "total": total or 0,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit if total > 0 else 0
        }

    # ---------- تغییر وضعیت کاربر (ادمین) ----------
    async def update_user_status(
            self,
            user_id: int,
            status: UserStatus,
            reason: Optional[str],
            admin_user: User
    ) -> Dict[str, Any]:
        """تغییر وضعیت کاربر"""

        user = await self.db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.status = status
        user.status_reason = reason
        user.updated_at = datetime.utcnow()

        if status == UserStatus.ACTIVE:
            user.is_active = True
        elif status == UserStatus.SUSPENDED:
            user.is_active = False

        self.db.add(user)
        await self.db.commit()

        return {
            "user_id": user.id,
            "status": status,
            "message": f"User status updated to {status}"
        }

    # ---------- حذف کاربر (ادمین) ----------
    async def delete_user(
            self,
            user_id: int,
            hard_delete: bool = False,
            admin_user: User = None
    ) -> Dict[str, Any]:
        """حذف کاربر"""

        user = await self.db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if hard_delete:
            await self.db.delete(user)
            message = "User permanently deleted"
        else:
            user.is_active = False
            user.status = UserStatus.SUSPENDED
            user.deleted_at = datetime.utcnow()
            self.db.add(user)
            message = "User soft deleted"

        await self.db.commit()

        return {
            "user_id": user_id,
            "hard_delete": hard_delete,
            "message": message
        }