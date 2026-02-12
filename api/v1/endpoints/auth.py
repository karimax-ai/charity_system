# app/api/v1/endpoints
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.permissions import get_current_user, require_roles
from core.security import hash_password
from models.verification import VerificationDocument
from schemas.verification import VerificationDocumentCreate
from services.auth_service import AuthService
from schemas.user import UserCreate, UserRead, UserLogin, Token, TokenResponse, OTPRequest, OTPVerify, \
    PasswordResetRequest, PasswordResetVerify, ChangePassword, BulkUserCreate, RefreshToken, BulkUserResponse, \
    VerificationReview
from schemas.user import GoogleOAuth  # اضافه کن
from services.oauth_service import GoogleOAuthService  # اضافه کن
from models.user import User, UserStatus  # برای select
from sqlalchemy import select

from services.otp_service import OTPService
from services.twofa_service import TwoFAService

router = APIRouter()


@router.post("/register", response_model=TokenResponse)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    service = AuthService(db)
    user = await service.register_user(
        email=user_data.email,
        password=user_data.password,
        username=user_data.username,
        phone=user_data.phone,
        role_key=user_data.role_key
    )

    # برای نیازمندها یا فروشنده‌ها، وضعیت NEED_VERIFICATION
    if user_data.role_key in ["NEEDY", "VENDOR"]:
        user.status = UserStatus.NEED_VERIFICATION
        db.add(user)
        await db.commit()
        await db.refresh(user)

    token_resp = await service.create_token(user)
    return token_resp


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    service = AuthService(db)
    user = await service.authenticate_user(email=data.email, password=data.password)
    token_resp = await service.create_token(user)
    return token_resp


@router.post("/google", response_model=TokenResponse)
async def google_login(data: GoogleOAuth, db: AsyncSession = Depends(get_db)):
    user_info = await GoogleOAuthService.verify_token(data.token)
    service = AuthService(db)

    result = await db.execute(select(User).where(User.email == user_info["email"]))
    user = result.scalar_one_or_none()
    if not user:
        user = await service.register_user(email=user_info["email"], password="oauth_dummy", username=user_info.get("name"))
    token_resp = await service.create_token(user)
    return token_resp



# app/api/v1/endpoints/auth/routes.py


@router.post("/2fa/enable")
async def enable_2fa(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.two_fa_enabled:
        raise HTTPException(status_code=400, detail="2FA already enabled")
    secret = TwoFAService.generate_secret()
    user.two_fa_secret = secret
    user.two_fa_enabled = True
    db.add(user)
    await db.commit()
    qr_b64 = TwoFAService.get_qr_code_uri(user.email, secret)
    return {"qr_code": qr_b64, "secret": secret}  # فرانت از QR اسکن می‌کنه

@router.post("/2fa/verify")
async def verify_2fa(token: str, user: User = Depends(get_current_user)):
    if not user.two_fa_enabled or not user.two_fa_secret:
        raise HTTPException(status_code=400, detail="2FA not enabled")
    if not TwoFAService.verify_token(user.two_fa_secret, token):
        raise HTTPException(status_code=400, detail="Invalid 2FA code")
    return {"detail": "2FA verified successfully"}




router.post("/otp/request")
async def request_otp(data: OTPRequest):
    code = OTPService.send_otp(data.phone)
    return {"detail": f"OTP sent to {data.phone}"}



@router.post("/otp/verify", response_model=TokenResponse)
async def verify_otp(data: OTPVerify, db: AsyncSession = Depends(get_db)):
    # تایید کد
    OTPService.verify_otp(data.phone, data.code)

    # پیدا کردن کاربر
    result = await db.execute(select(User).where(User.phone == data.phone))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="User not found or inactive")

    # JWT یا 2FA check
    service = AuthService(db)
    token_resp = await service.create_token(user)
    return token_resp


@router.post("/password/reset/request")
async def password_reset_request(data: PasswordResetRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    # ارسال OTP (می‌تواند روی ایمیل یا SMS)
    OTPService.send_otp(user.phone or user.email)
    return {"detail": "Password reset OTP sent"}



@router.post("/password/reset/verify")
async def password_reset_verify(data: PasswordResetVerify, db: AsyncSession = Depends(get_db)):
    OTPService.verify_otp(data.email, data.otp)

    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    user.hashed_password = hash_password(data.new_password)
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return {"detail": "Password reset successfully"}


# ✅新增: تغییر رمز عبور
@router.post("/change-password")
async def change_password(
        data: ChangePassword,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    service = AuthService(db)
    return await service.change_password(user, data.old_password, data.new_password)


# ✅新增: رفرش توکن
@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
        data: RefreshToken,
        db: AsyncSession = Depends(get_db)
):
    service = AuthService(db)
    return await service.refresh_token(data.refresh_token)


# ✅新增: ایجاد کاربران گروهی توسط ادمین
@router.post("/admin/bulk-create", response_model=BulkUserResponse)
async def bulk_create_users(
        data: BulkUserCreate,
        admin: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER")),
        db: AsyncSession = Depends(get_db)
):
    service = AuthService(db)
    return await service.bulk_create_users(
        users_data=data.users,
        role_key=data.role_key,
        send_sms=data.send_sms,
        send_email=data.send_email
    )


# ✅新增: ارسال مدارک تأیید هویت
@router.post("/verification/documents")
async def submit_verification_documents(
        documents: List[VerificationDocumentCreate],  # ✅
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
        request: Request = None
):
    service = AuthService(db, request)
    return await service.submit_verification_documents(
        user=user,
        documents=[doc.dict() for doc in documents],
        ip_address=request.client.host if request else None
    )

# ✅新增: بررسی و تأیید مدارک توسط ادمین
@router.post("/admin/verification/review")
async def review_verification(
        data: VerificationReview,
        admin: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER")),
        db: AsyncSession = Depends(get_db)
):
    service = AuthService(db)
    return await service.review_verification_request(
        admin_user=admin,
        user_id=data.user_id,
        approve=data.status == UserStatus.ACTIVE,
        admin_notes=data.admin_notes
    )


# ✅新增: لاگین با 2FA کامل
@router.post("/2fa/login")
async def login_with_2fa(
        email: str,
        otp_code: str,
        db: AsyncSession = Depends(get_db),
        request: Request = None
):
    # تأیید OTP 2FA
    user_result = await db.execute(select(User).where(User.email == email))
    user = user_result.scalar_one_or_none()

    if not user or not user.two_fa_enabled:
        raise HTTPException(status_code=400, detail="2FA not enabled")

    # تأیید کد 2FA
    if user.two_fa_method == "sms":
        await OTPService.verify_otp(user.phone, otp_code, purpose="2fa")
    else:
        if not TwoFAService.verify_token(user.two_fa_secret, otp_code):
            raise HTTPException(status_code=400, detail="Invalid 2FA code")

    # صدور توکن
    service = AuthService(db, request)
    return await service.create_token(user)


# ✅新增: CAPTCHA
@router.get("/captcha")
async def get_captcha():
    """تولید CAPTCHA برای فرانت"""
    from services.captcha_service import CaptchaService
    captcha_id, image_b64 = await CaptchaService.generate()
    return {"captcha_id": captcha_id, "image": image_b64}


# ✅新增: لاگوت
@router.post("/logout")
async def logout(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """خروج از حساب کاربری و باطل کردن رفرش توکن"""
    user.refresh_token = None
    user.refresh_token_expires = None
    await db.commit()
    return {"message": "Logged out successfully"}


# ✅新增: دستگاه‌های معتبر
@router.post("/devices/trust")
async def trust_device(
        device_id: str,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """اعتماد به دستگاه جاری"""
    if not user.trusted_devices:
        user.trusted_devices = []
    if device_id not in user.trusted_devices:
        user.trusted_devices.append(device_id)
    await db.commit()
    return {"message": "Device trusted"}


@router.delete("/devices/revoke")
async def revoke_device(
        device_id: str,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """لغو اعتماد دستگاه"""
    if user.trusted_devices and device_id in user.trusted_devices:
        user.trusted_devices.remove(device_id)
    await db.commit()
    return {"message": "Device revoked"}