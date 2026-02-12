from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from models.user import User, UserStatus
from models.role import Role
from core.security import hash_password, verify_password, create_access_token, create_refresh_token
from fastapi import HTTPException, status, Request
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import secrets
import string

from schemas.user import TokenResponse, BulkUserResponse
from services.otp_service import OTPService
from core.config import settings


class AuthService:
    def __init__(self, db: AsyncSession, request: Optional[Request] = None):
        self.db = db
        self.request = request

    # ✅ ثبت‌نام با امنیت بالا
    async def register_user(
            self,
            email: str,
            password: str,
            username: str = None,
            phone: str = None,
            role_key: str = "USER",
            captcha_token: str = None,
            ip_address: str = None
    ):
        # 1. بررسی CAPTCHA
        if settings.ENABLE_CAPTCHA:
            from services.captcha_service import CaptchaService
            await CaptchaService.verify(captcha_token)

        # 2. بررسی تکراری بودن
        result = await self.db.execute(
            select(User).where(
                or_(
                    User.email == email,
                    User.phone == phone if phone else False
                )
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            if existing.email == email:
                raise HTTPException(status_code=400, detail="Email already registered")
            if phone and existing.phone == phone:
                raise HTTPException(status_code=400, detail="Phone number already registered")

        # 3. بررسی رمز عبور قوی
        if not self._is_strong_password(password):
            raise HTTPException(
                status_code=400,
                detail="Password must be at least 8 characters with uppercase, lowercase, number and special character"
            )

        # 4. نقش
        result = await self.db.execute(select(Role).where(Role.key == role_key))
        role = result.scalar_one_or_none()
        if not role:
            raise HTTPException(status_code=400, detail="Role not found")

        # 5. ایجاد کاربر
        user = User(
            email=email,
            username=username,
            phone=phone,
            hashed_password=hash_password(password),
            roles=[role],
            status=UserStatus.NEED_VERIFICATION if role_key in ["NEEDY", "VENDOR"] else UserStatus.ACTIVE,
            last_login_ip=ip_address
        )

        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        # 6. ارسال OTP تأیید شماره (اختیاری)
        if phone and settings.ENABLE_PHONE_VERIFICATION:
            await OTPService.send_otp(phone, purpose="register")

        return user

    # ✅ ورود با تشخیص حمله و قفل خودکار
    async def authenticate_user(
            self,
            email: str,
            password: str,
            ip_address: str = None,
            device_id: str = None
    ):
        # 1. یافتن کاربر
        result = await self.db.execute(
            select(User).where(
                or_(
                    User.email == email,
                    User.phone == email  # امکان ورود با شماره
                )
            )
        )
        user = result.scalar_one_or_none()

        if not user:
            # جلوگیری از تشخیص وجود کاربر
            await self._fake_login_delay()
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # 2. بررسی قفل بودن حساب
        if user.locked_until and user.locked_until > datetime.utcnow():
            remaining = (user.locked_until - datetime.utcnow()).seconds // 60
            raise HTTPException(
                status_code=403,
                detail=f"Account is locked for {remaining} minutes. Try again later."
            )

        # 3. بررسی رمز عبور
        if not user.hashed_password or not verify_password(password, user.hashed_password):
            # افزایش تعداد تلاش‌های ناموفق
            user.failed_login_attempts += 1

            # قفل کردن حساب پس از 5 تلاش ناموفق
            if user.failed_login_attempts >= settings.MAX_LOGIN_ATTEMPTS:
                user.locked_until = datetime.utcnow() + timedelta(minutes=settings.ACCOUNT_LOCKOUT_MINUTES)
                user.failed_login_attempts = 0

            await self.db.commit()

            # تأخیر تصادفی برای جلوگیری از brute force
            await self._fake_login_delay()
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # 4. بررسی فعال بودن کاربر
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account is disabled")

        # 5. بررسی دستگاه معتبر (اختیاری)
        if device_id and settings.ENABLE_TRUSTED_DEVICES:
            if device_id not in (user.trusted_devices or []):
                # ارسال OTP برای تأیید دستگاه جدید
                if user.phone:
                    await OTPService.send_otp(user.phone, purpose="device_verification")
                    return {"status": "DEVICE_VERIFICATION_REQUIRED", "user": user}

        # 6. بازنشانی تلاش‌های ناموفق
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = datetime.utcnow()
        user.last_login_ip = ip_address
        await self.db.commit()

        return user

    # ✅ ایجاد توکن با پشتیبانی 2FA و رفرش توکن
    async def create_token(self, user: User, device_id: str = None) -> TokenResponse:
        roles_keys = [role.key for role in user.roles]

        # 1. بررسی 2FA
        if user.two_fa_enabled:
            # ارسال OTP برای 2FA پیامکی
            if user.two_fa_method == "sms" and user.phone:
                await OTPService.send_otp(user.phone, purpose="2fa")

            return TokenResponse(
                access_token=None,
                refresh_token=None,
                roles=roles_keys,
                status="2FA_REQUIRED",
                message="Two-factor authentication required",
                requires_2fa=True
            )

        # 2. بررسی تأیید هویت
        if user.status == UserStatus.NEED_VERIFICATION:
            return TokenResponse(
                access_token=None,
                refresh_token=None,
                roles=roles_keys,
                status=user.status,
                message="Account pending verification",
                requires_verification=True
            )

        # 3. صدور توکن‌ها
        access_token = create_access_token(
            subject=user.uuid,
            extra_data={
                "email": user.email,
                "roles": roles_keys,
                "device_id": device_id
            }
        )

        refresh_token = create_refresh_token(subject=user.uuid)

        # ذخیره رفرش توکن در دیتابیس
        user.refresh_token = refresh_token
        user.refresh_token_expires = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        await self.db.commit()

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            roles=roles_keys,
            status=UserStatus.ACTIVE,
            message="Login successful"
        )

    # ✅ رفرش توکن
    async def refresh_token(self, refresh_token: str):
        from jose import jwt, JWTError

        try:
            payload = jwt.decode(
                refresh_token,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM]
            )
            user_id = payload.get("sub")

            if not user_id:
                raise HTTPException(status_code=401, detail="Invalid refresh token")

            result = await self.db.execute(
                select(User).where(
                    and_(
                        User.uuid == user_id,
                        User.refresh_token == refresh_token,
                        User.refresh_token_expires > datetime.utcnow()
                    )
                )
            )
            user = result.scalar_one_or_none()

            if not user:
                raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

            # صدور توکن جدید
            return await self.create_token(user)

        except JWTError:
            raise HTTPException(status_code=401, detail="Invalid refresh token")

    # ✅ تغییر رمز عبور
    async def change_password(
            self,
            user: User,
            old_password: str,
            new_password: str
    ):
        if not verify_password(old_password, user.hashed_password):
            raise HTTPException(status_code=400, detail="Current password is incorrect")

        if not self._is_strong_password(new_password):
            raise HTTPException(
                status_code=400,
                detail="New password must be at least 8 characters with uppercase, lowercase, number and special character"
            )

        user.hashed_password = hash_password(new_password)
        # باطل کردن تمام سشن‌ها
        user.refresh_token = None
        user.refresh_token_expires = None
        user.trusted_devices = []

        await self.db.commit()

        # ارسال نوتیفیکیشن
        if user.phone:
            await OTPService.send_notification(user.phone, "Your password was changed successfully")

        return {"message": "Password changed successfully"}

    # ✅ ارسال رمز تکی/گروهی توسط ادمین
    async def bulk_create_users(
            self,
            users_data: List[Dict],
            role_key: str,
            send_sms: bool = True,
            send_email: bool = True
    ) -> BulkUserResponse:
        """
        ایجاد دسته‌جمعی کاربران با رمزهای تصادفی
        برای ادمین/مدیر خیریه
        """
        result = await self.db.execute(select(Role).where(Role.key == role_key))
        role = result.scalar_one_or_none()
        if not role:
            raise HTTPException(status_code=400, detail="Role not found")

        success_count = 0
        failed_count = 0
        failed_users = []
        generated_passwords = {}

        for user_data in users_data:
            try:
                email = user_data.get("email")
                phone = user_data.get("phone")
                username = user_data.get("username")

                # رمز تصادفی 10 رقمی
                password = self._generate_secure_password()

                # بررسی تکراری نبودن
                existing = await self.db.execute(
                    select(User).where(
                        or_(
                            User.email == email,
                            User.phone == phone if phone else False
                        )
                    )
                )
                if existing.scalar_one_or_none():
                    raise ValueError("User already exists")

                user = User(
                    email=email,
                    username=username,
                    phone=phone,
                    hashed_password=hash_password(password),
                    roles=[role],
                    status=UserStatus.NEED_VERIFICATION if role_key in ["NEEDY", "VENDOR"] else UserStatus.ACTIVE,
                    is_verified=False
                )

                self.db.add(user)
                await self.db.flush()

                generated_passwords[email] = password
                success_count += 1

                # ارسال رمز به کاربر
                if send_sms and phone:
                    await OTPService.send_password(phone, password)
                if send_email:
                    await self._send_password_email(email, password)

            except Exception as e:
                failed_count += 1
                failed_users.append({
                    "email": user_data.get("email"),
                    "reason": str(e)
                })

        await self.db.commit()

        return BulkUserResponse(
            success_count=success_count,
            failed_count=failed_count,
            failed_users=failed_users,
            generated_passwords=generated_passwords  # فقط برای ادمین
        )

    # ✅ تأیید هویت با مدارک
    async def submit_verification_documents(
            self,
            user: User,
            documents: List[Dict],
            ip_address: str = None
    ):
        from models.verification import VerificationDocument, DocumentType, DocumentStatus

        for doc in documents:
            verification_doc = VerificationDocument(
                user_id=user.id,
                document_type=doc["document_type"],
                document_number=doc.get("document_number"),
                file_path=doc["file_url"],
                file_name=doc.get("file_name"),
                file_size=doc.get("file_size"),
                mime_type=doc.get("mime_type"),
                status=DocumentStatus.PENDING
            )
            self.db.add(verification_doc)

        user.status = UserStatus.NEED_VERIFICATION
        await self.db.commit()

        # ارسال نوتیفیکیشن به ادمین
        await self._notify_admin("new_verification_request", {
            "user_id": user.uuid,
            "email": user.email
        })

        return {"message": "Documents submitted successfully"}

    # ✅ تأیید مدارک توسط ادمین
    async def review_verification_request(
            self,
            admin_user: User,
            user_id: int,
            approve: bool,
            admin_notes: str = None
    ):
        from models.verification import VerificationDocument, DocumentStatus

        # بروزرسانی وضعیت مدارک
        result = await self.db.execute(
            select(VerificationDocument).where(
                and_(
                    VerificationDocument.user_id == user_id,
                    VerificationDocument.status == DocumentStatus.PENDING
                )
            )
        )
        documents = result.scalars().all()

        for doc in documents:
            doc.status = DocumentStatus.APPROVED if approve else DocumentStatus.REJECTED
            doc.reviewed_at = datetime.utcnow()
            doc.reviewed_by = admin_user.id
            doc.admin_note = admin_notes

        # بروزرسانی وضعیت کاربر
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one()

        if approve:
            user.status = UserStatus.ACTIVE
            user.is_verified = True
            user.verified_at = datetime.utcnow()
            user.verified_by = admin_user.id
        else:
            user.status = UserStatus.REJECTED

        await self.db.commit()

        # ارسال نتیجه به کاربر
        if user.phone:
            status_text = "approved" if approve else "rejected"
            await OTPService.send_notification(
                user.phone,
                f"Your verification request was {status_text}"
            )

        return {"message": f"Verification {'approved' if approve else 'rejected'}"}

    # ✅ ابزارهای کمکی
    def _is_strong_password(self, password: str) -> bool:
        import re
        if len(password) < 8:
            return False
        if not re.search(r"[A-Z]", password):
            return False
        if not re.search(r"[a-z]", password):
            return False
        if not re.search(r"\d", password):
            return False
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            return False
        return True

    def _generate_secure_password(self, length: int = 10) -> str:
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        while True:
            password = ''.join(secrets.choice(alphabet) for _ in range(length))
            if self._is_strong_password(password):
                return password

    async def _fake_login_delay(self):
        import asyncio
        import random
        await asyncio.sleep(random.uniform(0.5, 1.5))