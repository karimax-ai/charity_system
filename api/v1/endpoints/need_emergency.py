# 3️⃣ app/api/v1/endpoints/need_emergency.py
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any
from datetime import datetime

from core.database import get_db
from core.permissions import get_current_user, require_roles
from models.user import User
from models.need_ad import NeedAd
from schemas.need_emergency import (
    NeedEmergencyCreate, NeedEmergencyUpdate,
    NeedEmergencyRead
)
from services.need_emergency_service import NeedEmergencyService

router = APIRouter()


@router.post("/", response_model=NeedEmergencyRead, status_code=status.HTTP_201_CREATED)
async def declare_emergency(
        need_id: int,
        emergency_data: NeedEmergencyCreate,
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER")),
        db: AsyncSession = Depends(get_db)
):
    """اعلام وضعیت بحرانی برای یک نیاز (فقط ادمین/مدیر)"""
    service = NeedEmergencyService(db)

    # دریافت نیاز
    need = await db.get(NeedAd, need_id)
    if not need:
        raise HTTPException(status_code=404, detail="Need not found")

    emergency = await service.create_emergency_need(
        need=need,
        emergency_data=emergency_data.dict(),
        user=current_user
    )

    return emergency


@router.patch("/{emergency_id}", response_model=NeedEmergencyRead)
async def update_emergency_status(
        need_id: int,
        emergency_id: int,
        update_data: NeedEmergencyUpdate,
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER")),
        db: AsyncSession = Depends(get_db)
):
    """به‌روزرسانی وضعیت بحران"""
    service = NeedEmergencyService(db)
    emergency = await service.update_emergency_status(
        emergency_id, update_data, current_user
    )
    return emergency


@router.post("/{emergency_id}/notify")
async def send_emergency_notifications(
        need_id: int,
        emergency_id: int,
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER")),
        db: AsyncSession = Depends(get_db)
):
    """ارسال نوتیفیکیشن فوری به همه کاربران"""
    service = NeedEmergencyService(db)
    await service.send_emergency_notifications(emergency_id)
    return {"message": "Emergency notifications sent successfully"}