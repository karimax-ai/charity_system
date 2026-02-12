# app/services/need_emergency_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from fastapi import HTTPException, status
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from models.need_emergency import NeedEmergency, EmergencyType, EmergencySeverity, EmergencyStatus
from models.need_ad import NeedAd
from models.user import User
from services.notification_service import NotificationService


class NeedEmergencyService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.notification_service = NotificationService(db)

    async def create_emergency_need(
            self,
            need: NeedAd,
            emergency_data: Dict[str, Any],
            user: User
    ) -> NeedEmergency:
        """تبدیل نیاز معمولی به نیاز اضطراری"""

        # بررسی مجوز
        user_roles = [r.key for r in user.roles]
        if "ADMIN" not in user_roles and "CHARITY_MANAGER" not in user_roles:
            raise HTTPException(status_code=403, detail="Only admins can declare emergencies")

        # ایجاد رکورد بحران
        emergency = NeedEmergency(
            need_id=need.id,
            emergency_type=emergency_data.get("emergency_type"),
            severity=emergency_data.get("severity", EmergencySeverity.MODERATE),
            affected_area=emergency_data.get("affected_area"),
            latitude=emergency_data.get("latitude"),
            longitude=emergency_data.get("longitude"),
            radius_km=emergency_data.get("radius_km"),
            estimated_affected_people=emergency_data.get("estimated_affected_people"),
            estimated_damage_cost=emergency_data.get("estimated_damage_cost"),
            government_reference_number=emergency_data.get("government_reference_number"),
            declared_by=emergency_data.get("declared_by"),
            occurred_at=emergency_data.get("occurred_at", datetime.utcnow()),
            media_attachments=emergency_data.get("media_attachments", []),
            news_links=emergency_data.get("news_links", []),
        )

        self.db.add(emergency)
        await self.db.flush()

        # به‌روزرسانی نیاز
        need.is_emergency = True
        need.is_urgent = True
        need.emergency_id = emergency.id
        need.status = "active"
        need.privacy_level = "public"  # بحران‌ها عمومی هستند

        self.db.add(need)
        await self.db.commit()

        # ارسال نوتیفیکیشن فوری
        if emergency_data.get("notify_all_users", True):
            await self._send_emergency_notifications(emergency, need)

        return emergency

    async def _send_emergency_notifications(self, emergency: NeedEmergency, need: NeedAd):
        """ارسال نوتیفیکیشن فوری به کاربران"""

        # پیام نوتیفیکیشن
        title = f"⚠️ وضعیت بحرانی: {emergency.emergency_type.value}"
        message = f"نیاز فوری به کمک در {emergency.affected_area or need.city}"

        # ارسال به همه کاربران
        await self.notification_service.broadcast_to_all_users(
            title=title,
            message=message,
            data={
                "emergency_id": emergency.id,
                "need_id": need.id,
                "type": "emergency",
                "priority": "urgent"
            },
            send_sms=emergency.notify_sms,
            send_email=emergency.notify_email,
            send_push=emergency.notify_push,
        )