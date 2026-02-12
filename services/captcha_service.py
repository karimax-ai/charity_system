import httpx
import secrets
import hashlib
import json
from datetime import datetime, timedelta
from fastapi import HTTPException, Request
from typing import Optional, Dict
import redis.asyncio as redis
from core.config import settings


class CaptchaService:
    """سیستم ضد تقلب CAPTCHA"""

    @staticmethod
    async def verify(token: str, ip_address: Optional[str] = None) -> bool:
        """تأیید توکن Google reCAPTCHA"""
        if not settings.ENABLE_CAPTCHA:
            return True

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://www.google.com/recaptcha/api/siteverify",
                data={
                    "secret": settings.RECAPTCHA_SECRET_KEY,
                    "response": token,
                    "remoteip": ip_address
                }
            )
            result = response.json()

            if not result.get("success"):
                raise HTTPException(status_code=400, detail="CAPTCHA verification failed")

            # بررسی امتیاز (برای v3)
            if result.get("score", 1) < settings.RECAPTCHA_MIN_SCORE:
                raise HTTPException(status_code=400, detail="Suspicious activity detected")

            return True


class FraudDetectionService:
    """سرویس تشخیص تقلب و رفتار مشکوک"""

    def __init__(self, redis_client: redis.Redis = None):
        self.redis = redis_client

    async def check_suspicious_activity(
            self,
            request: Request,
            email: str = None,
            phone: str = None
    ) -> Dict:
        """بررسی فعالیت مشکوک در ثبت‌نام/ورود"""

        ip = request.client.host
        user_agent = request.headers.get("user-agent", "")
        device_id = request.headers.get("x-device-id")

        suspicious = []
        score = 0  # 0 = امن, 100 = قطعاً تقلب

        # 1. بررسی IP تکراری برای ثبت‌نام‌های متعدد
        if await self._check_multiple_accounts_same_ip(ip):
            suspicious.append("multiple_accounts_same_ip")
            score += 30

        # 2. بررسی VPN/Proxy
        if await self._is_vpn_or_proxy(ip):
            suspicious.append("vpn_or_proxy")
            score += 25

        # 3. بررسی User-Agent عجیب
        if self._is_suspicious_user_agent(user_agent):
            suspicious.append("suspicious_user_agent")
            score += 15

        # 4. بررسی ایمیل یکبار مصرف
        if email and await self._is_disposable_email(email):
            suspicious.append("disposable_email")
            score += 20

        # 5. بررسی سرعت درخواست‌ها (rate limit)
        if await self._check_request_rate(ip):
            suspicious.append("high_request_rate")
            score += 30

        # 6. بررسی دستگاه تکراری برای حساب‌های مختلف
        if device_id and await self._check_device_id_for_multiple_accounts(device_id):
            suspicious.append("device_id_abuse")
            score += 40

        is_suspicious = score >= settings.FRAUD_SCORE_THRESHOLD

        return {
            "is_suspicious": is_suspicious,
            "score": score,
            "reasons": suspicious,
            "requires_captcha": score >= settings.CAPTCHA_TRIGGER_SCORE,
            "requires_admin_review": score >= settings.ADMIN_REVIEW_SCORE
        }

    async def _check_multiple_accounts_same_ip(self, ip: str) -> bool:
        """بررسی تعداد حساب‌های ساخته شده از یک IP"""
        if not self.redis:
            return False

        key = f"accounts:ip:{ip}"
        count = await self.redis.get(key)
        return int(count or 0) > settings.MAX_ACCOUNTS_PER_IP

    async def _is_vpn_or_proxy(self, ip: str) -> bool:
        """بررسی VPN/Proxy با سرویس‌های آنلاین"""
        if not settings.ENABLE_VPN_DETECTION:
            return False

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"https://ipqualityscore.com/api/json/ip/{settings.IPQS_API_KEY}/{ip}",
                    timeout=3
                )
                data = response.json()
                return data.get("proxy", False) or data.get("vpn", False)
            except:
                return False

    def _is_suspicious_user_agent(self, user_agent: str) -> bool:
        """بررسی User-Agent عجیب"""
        if not user_agent:
            return True

        suspicious_patterns = [
            "curl", "wget", "python", "java", "go-http-client",
            "scrapy", "bot", "crawler", "spider"
        ]

        ua_lower = user_agent.lower()
        return any(pattern in ua_lower for pattern in suspicious_patterns)

    async def _is_disposable_email(self, email: str) -> bool:
        """بررسی ایمیل یکبار مصرف"""
        domain = email.split("@")[1]

        # لیست دامنه‌های یکبار مصرف
        disposable_domains = [
            "tempmail", "10minute", "guerrillamail", "mailinator",
            "yopmail", "throwaway", "disposable"
        ]

        return any(domain in d for d in disposable_domains)

    async def _check_request_rate(self, ip: str) -> bool:
        """بررسی سرعت درخواست‌ها از یک IP"""
        if not self.redis:
            return False

        key = f"requests:ip:{ip}"
        count = await self.redis.incr(key)
        if count == 1:
            await self.redis.expire(key, 60)  # 1 دقیقه

        return count > settings.MAX_REQUESTS_PER_MINUTE

    async def _check_device_id_for_multiple_accounts(self, device_id: str) -> bool:
        """بررسی اینکه یک دستگاه برای چند حساب استفاده شده"""
        if not self.redis:
            return False

        key = f"device:accounts:{device_id}"
        count = await self.redis.get(key)
        return int(count or 0) > settings.MAX_ACCOUNTS_PER_DEVICE