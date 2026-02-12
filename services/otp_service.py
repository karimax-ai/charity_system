import random
import secrets
from datetime import datetime, timedelta
from fastapi import HTTPException
from typing import Optional, Dict
import httpx
import redis.asyncio as redis
from core.config import settings


# ✅ استفاده از Redis (جایگزین حافظه موقت)
class OTPService:
    EXPIRY_MINUTES = 5
    MAX_ATTEMPTS = 3
    ATTEMPT_WINDOW = 15  # دقیقه

    def __init__(self):
        self.redis_client = None
        if settings.REDIS_URL:
            self.redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

    async def _get_redis(self):
        if not self.redis_client and settings.REDIS_URL:
            self.redis_client = await redis.from_url(settings.REDIS_URL, decode_responses=True)
        return self.redis_client

    # ✅ ارسال OTP واقعی با سرویس پیامک
    @classmethod
    async def send_otp(cls, phone: str, purpose: str = "login") -> str:
        instance = cls()
        code = f"{secrets.randbelow(900000) + 100000}"  # 6 رقم تصادفی امن

        # ذخیره در Redis
        redis_client = await instance._get_redis()
        if redis_client:
            key = f"otp:{purpose}:{phone}"
            await redis_client.setex(
                key,
                cls.EXPIRY_MINUTES * 60,
                code
            )
            # ذخیره تعداد تلاش‌ها
            attempt_key = f"otp_attempts:{purpose}:{phone}"
            await redis_client.setex(attempt_key, cls.ATTEMPT_WINDOW * 60, 0)
        else:
            # fallback به حافظه
            otp_store[phone] = {
                "code": code,
                "expires": datetime.utcnow() + timedelta(minutes=cls.EXPIRY_MINUTES),
                "attempts": 0,
                "purpose": purpose
            }

        # ✅ ارسال واقعی SMS
        if settings.SMS_PROVIDER == "kavenegar":
            await cls._send_kavenegar(phone, code)
        elif settings.SMS_PROVIDER == "farazsms":
            await cls._send_farazsms(phone, code)
        else:
            # در محیط توسعه
            print(f"[OTP] {purpose}: {phone} -> {code}")

        return code

    @staticmethod
    async def _send_kavenegar(phone: str, code: str):
        """ارسال پیامک با Kavenegar"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.kavenegar.com/v1/{settings.KAVENEGAR_API_KEY}/verify/lookup.json",
                params={
                    "receptor": phone,
                    "token": code,
                    "template": settings.SMS_OTP_TEMPLATE
                }
            )
            if response.status_code != 200:
                print(f"Kavenegar error: {response.text}")

    @staticmethod
    async def _send_farazsms(phone: str, code: str):
        """ارسال پیامک با FarazSMS"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://ippanel.com/api/select",
                json={
                    "op": "pattern",
                    "user": settings.FARAZSMS_USERNAME,
                    "pass": settings.FARAZSMS_PASSWORD,
                    "fromNum": settings.SMS_SENDER,
                    "toNum": phone,
                    "patternCode": settings.SMS_OTP_PATTERN,
                    "inputData": [{"verification-code": code}]
                }
            )

    # ✅ تأیید OTP با محدودیت تلاش
    @classmethod
    async def verify_otp(cls, phone: str, code: str, purpose: str = "login") -> bool:
        instance = cls()
        redis_client = await instance._get_redis()

        if redis_client:
            key = f"otp:{purpose}:{phone}"
            attempt_key = f"otp_attempts:{purpose}:{phone}"

            stored_code = await redis_client.get(key)
            attempts = await redis_client.get(attempt_key)
            attempts = int(attempts) if attempts else 0

            # بررسی تعداد تلاش‌ها
            if attempts >= cls.MAX_ATTEMPTS:
                raise HTTPException(
                    status_code=429,
                    detail=f"Too many attempts. Try again in {cls.ATTEMPT_WINDOW} minutes"
                )

            await redis_client.incr(attempt_key)

            if not stored_code:
                raise HTTPException(status_code=400, detail="OTP expired or not requested")

            if stored_code != code:
                raise HTTPException(status_code=400, detail="Invalid OTP")

            # موفق: حذف OTP
            await redis_client.delete(key)
            await redis_client.delete(attempt_key)
            return True
        else:
            # fallback به حافظه
            data = otp_store.get(phone)
            if not data:
                raise HTTPException(status_code=400, detail="No OTP requested")
            if data.get("purpose") != purpose:
                raise HTTPException(status_code=400, detail="Invalid OTP purpose")
            if data["expires"] < datetime.utcnow():
                del otp_store[phone]
                raise HTTPException(status_code=400, detail="OTP expired")
            if data["code"] != code:
                data["attempts"] = data.get("attempts", 0) + 1
                if data["attempts"] >= cls.MAX_ATTEMPTS:
                    del otp_store[phone]
                    raise HTTPException(status_code=429, detail="Too many attempts")
                raise HTTPException(status_code=400, detail="Invalid OTP")

            del otp_store[phone]
            return True


# ✅ نگهداری برای backward compatibility
otp_store = {}