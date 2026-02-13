import secrets
import hmac
from datetime import datetime, timedelta
from fastapi import HTTPException
import redis.asyncio as redis
from core.config import settings

otp_store = {}


class OTPService:
    EXPIRY_MINUTES = 5
    MAX_ATTEMPTS = 3
    ATTEMPT_WINDOW = 900

    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True) if settings.REDIS_URL else None

    @staticmethod
    def _normalize(phone: str) -> str:
        return phone.replace(" ", "").replace("-", "")

    # --------------------------------------------------
    # SEND
    # --------------------------------------------------
    @classmethod
    async def send_otp(cls, phone: str, purpose: str = "login"):
        phone = cls._normalize(phone)
        code = f"{secrets.randbelow(900000)+100000}"

        if cls.redis_client:
            key = f"otp:{purpose}:{phone}"
            attempts = f"otp_attempts:{purpose}:{phone}"

            # rate limit send
            if await cls.redis_client.exists(key):
                raise HTTPException(429, "OTP already sent. Wait.")

            await cls.redis_client.setex(key, cls.EXPIRY_MINUTES * 60, code)
            await cls.redis_client.setex(attempts, cls.ATTEMPT_WINDOW, 0)

        else:
            otp_store[phone] = {
                "code": code,
                "expires": datetime.utcnow() + timedelta(minutes=cls.EXPIRY_MINUTES),
                "attempts": 0,
                "purpose": purpose
            }

        # provider send
        if settings.SMS_PROVIDER == "console":
            print(f"[OTP] {phone} -> {code}")

        return code

    # --------------------------------------------------
    # VERIFY
    # --------------------------------------------------
    @classmethod
    async def verify_otp(cls, phone: str, code: str, purpose: str = "login"):
        phone = cls._normalize(phone)

        if cls.redis_client:
            key = f"otp:{purpose}:{phone}"
            attempts_key = f"otp_attempts:{purpose}:{phone}"

            stored = await cls.redis_client.get(key)
            attempts = int(await cls.redis_client.get(attempts_key) or 0)

            if attempts >= cls.MAX_ATTEMPTS:
                raise HTTPException(429, "Too many attempts")

            await cls.redis_client.incr(attempts_key)

            if not stored:
                raise HTTPException(400, "OTP expired")

            if not hmac.compare_digest(stored, code):
                raise HTTPException(400, "Invalid OTP")

            await cls.redis_client.delete(key)
            await cls.redis_client.delete(attempts_key)
            return True

        # fallback
        data = otp_store.get(phone)
        if not data or data["purpose"] != purpose:
            raise HTTPException(400, "OTP invalid")

        if data["expires"] < datetime.utcnow():
            del otp_store[phone]
            raise HTTPException(400, "Expired")

        if not hmac.compare_digest(data["code"], code):
            data["attempts"] += 1
            if data["attempts"] >= cls.MAX_ATTEMPTS:
                del otp_store[phone]
                raise HTTPException(429, "Too many attempts")
            raise HTTPException(400, "Invalid")

        del otp_store[phone]
        return True
