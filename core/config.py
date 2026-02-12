# app/core/config.py
from typing import *

from pydantic_settings import BaseSettings



class Settings(BaseSettings):
    APP_NAME: str = "Charity Platform"
    DEBUG: bool = False

    # Security
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    FILE_STORAGE_PATH: str = "./uploads"
    MAX_FILE_SIZE: int = 100 * 1024 * 1024  # 100MB
    ALLOWED_FILE_TYPES: List[str] = [
        "image/jpeg", "image/png", "image/gif", "image/webp",
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ]
    MAX_LOGIN_ATTEMPTS: int = 5
    ACCOUNT_LOCKOUT_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    ALGORITHM: str = "HS256"

    # ✅新增: CAPTCHA
    ENABLE_CAPTCHA: bool = True
    RECAPTCHA_SECRET_KEY: Optional[str] = None
    RECAPTCHA_SITE_KEY: Optional[str] = None
    RECAPTCHA_MIN_SCORE: float = 0.5

    # ✅新增: SMS
    SMS_PROVIDER: str = "kavenegar"  # kavenegar, farazsms
    KAVENEGAR_API_KEY: Optional[str] = None
    FARAZSMS_USERNAME: Optional[str] = None
    FARAZSMS_PASSWORD: Optional[str] = None
    SMS_SENDER: Optional[str] = None
    SMS_OTP_TEMPLATE: str = "otp"
    SMS_OTP_PATTERN: str = "otp-pattern"

    # ✅新增: Redis
    REDIS_URL: Optional[str] = None

    # ✅新增: تشخیص تقلب
    ENABLE_VPN_DETECTION: bool = False
    IPQS_API_KEY: Optional[str] = None
    MAX_ACCOUNTS_PER_IP: int = 3
    MAX_ACCOUNTS_PER_DEVICE: int = 2
    MAX_REQUESTS_PER_MINUTE: int = 30
    FRAUD_SCORE_THRESHOLD: int = 50
    CAPTCHA_TRIGGER_SCORE: int = 30
    ADMIN_REVIEW_SCORE: int = 70

    # ✅新增: احراز هویت
    ENABLE_PHONE_VERIFICATION: bool = True
    ENABLE_TRUSTED_DEVICES: bool = True

    # Encryption
    FILE_ENCRYPTION_KEY: Optional[str] = None

    # Database
    DATABASE_URL: str

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
