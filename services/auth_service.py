import asyncio
import hashlib
import random

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




ALLOWED_PUBLIC_ROLES = {"USER", "DONOR", "NEEDY", "VENDOR"}


class DeviceVerificationRequired(Exception):
    pass


class AuthService:
    def __init__(self, db: AsyncSession, request=None):
        self.db = db
        self.request = request

    # ------------------------------------------------
    # REGISTER
    # ------------------------------------------------
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
        # captcha
        if settings.ENABLE_CAPTCHA:
            from services.captcha_service import CaptchaService
            await CaptchaService.verify(captcha_token)

        # role restriction
        if role_key not in ALLOWED_PUBLIC_ROLES:
            raise HTTPException(403, "Invalid role")

        # duplicate check
        result = await self.db.execute(
            select(User).where(or_(User.email == email, User.phone == phone if phone else False))
        )
        if result.scalar_one_or_none():
            raise HTTPException(400, "User already exists")

        # password strength
        if not self._is_strong_password(password):
            raise HTTPException(400, "Weak password")

        # role
        role = (await self.db.execute(select(Role).where(Role.key == role_key))).scalar_one_or_none()
        if not role:
            raise HTTPException(400, "Role not found")

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

        if phone and settings.ENABLE_PHONE_VERIFICATION:
            await OTPService.send_otp(phone, purpose="register")

        return user

    # ------------------------------------------------
    # LOGIN
    # ------------------------------------------------
    async def authenticate_user(self, email: str, password: str, ip_address=None, device_id=None):

        result = await self.db.execute(
            select(User).where(or_(User.email == email, User.phone == email))
        )
        user = result.scalar_one_or_none()

        if not user:
            await self._fake_delay()
            raise HTTPException(401, "Invalid credentials")

        if user.deleted_at:
            raise HTTPException(403, "Account disabled")

        # lock check
        if user.locked_until and user.locked_until > datetime.utcnow():
            raise HTTPException(403, "Account locked temporarily")

        # password verify
        if not verify_password(password, user.hashed_password):
            user.failed_login_attempts += 1

            if user.failed_login_attempts >= settings.MAX_LOGIN_ATTEMPTS:
                user.locked_until = datetime.utcnow() + timedelta(minutes=settings.ACCOUNT_LOCKOUT_MINUTES)
                user.failed_login_attempts = 0

            await self.db.commit()
            await self._fake_delay()
            raise HTTPException(401, "Invalid credentials")

        if not user.is_active:
            raise HTTPException(403, "Account disabled")

        # device trust
        if device_id and settings.ENABLE_TRUSTED_DEVICES:
            device_hash = self._hash_device(device_id)

            if device_hash not in (user.trusted_devices or []):
                if user.phone:
                    await OTPService.send_otp(user.phone, purpose="device")
                    raise DeviceVerificationRequired()

        # reset attempts
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = datetime.utcnow()
        user.last_login_ip = ip_address
        await self.db.commit()

        return user

    # ------------------------------------------------
    # TOKEN
    # ------------------------------------------------
    async def create_token(self, user: User, device_id=None):

        roles = [r.key for r in user.roles]

        # 2FA
        if user.two_fa_enabled:
            if user.two_fa_method == "sms" and user.phone:
                await OTPService.send_otp(user.phone, purpose="2fa")

            return TokenResponse(
                access_token=None,
                refresh_token=None,
                roles=roles,
                requires_2fa=True,
                message="2FA required"
            )

        # verification
        if user.status == UserStatus.NEED_VERIFICATION:
            return TokenResponse(
                access_token=None,
                refresh_token=None,
                roles=roles,
                requires_verification=True,
                message="Account pending verification"
            )

        access = create_access_token(subject=user.uuid, extra_data={"roles": roles})
        refresh = create_refresh_token(subject=user.uuid)

        # rotation
        user.refresh_token = refresh
        user.refresh_token_expires = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        await self.db.commit()

        return TokenResponse(access_token=access, refresh_token=refresh, roles=roles, message="Login successful")

    # ------------------------------------------------
    # REFRESH
    # ------------------------------------------------
    async def refresh_token(self, token: str):
        from jose import jwt, JWTError

        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            uid = payload.get("sub")

            user = (
                await self.db.execute(
                    select(User).where(
                        and_(
                            User.uuid == uid,
                            User.refresh_token == token,
                            User.refresh_token_expires > datetime.utcnow()
                        )
                    )
                )
            ).scalar_one_or_none()

            if not user:
                raise HTTPException(401, "Invalid refresh token")

            return await self.create_token(user)

        except JWTError:
            raise HTTPException(401, "Invalid refresh token")

    # ------------------------------------------------
    # PASSWORD CHANGE
    # ------------------------------------------------
    async def change_password(self, user: User, old: str, new: str):
        if not verify_password(old, user.hashed_password):
            raise HTTPException(400, "Wrong password")

        if not self._is_strong_password(new):
            raise HTTPException(400, "Weak password")

        user.hashed_password = hash_password(new)
        user.refresh_token = None
        user.trusted_devices = []

        await self.db.commit()

        if user.phone:
            await OTPService.send_notification(user.phone, "Password changed")

        return {"message": "Password changed"}

    # ------------------------------------------------
    # HELPERS
    # ------------------------------------------------
    def _hash_device(self, fp: str):
        return hashlib.sha256(fp.encode()).hexdigest()

    async def _fake_delay(self):
        await asyncio.sleep(random.uniform(0.5, 1.2))

    def _is_strong_password(self, password: str):
        import re
        return (
            len(password) >= 8
            and re.search(r"[A-Z]", password)
            and re.search(r"[a-z]", password)
            and re.search(r"\d", password)
            and re.search(r"[!@#$%^&*]", password)
        )


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