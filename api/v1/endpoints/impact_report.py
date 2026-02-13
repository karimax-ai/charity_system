# app/api/v1/endpoints/impact_report.py - فایل جدید

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import datetime, timedelta

from core.database import get_db
from core.permissions import get_current_user, require_roles
from models.user import User
from services.impact_report_service import ImpactReportService

router = APIRouter(prefix="/reports/impact", tags=["Impact Reports"])


@router.get("/products-on-needs")
async def get_product_impact_report(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        charity_id: Optional[int] = None,
        need_id: Optional[int] = None,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER", "SUPER_ADMIN"))
):
    """
    گزارش تأثیر فروش محصولات بر آگهی‌های نیاز
    - کدام محصولات بیشترین کمک را به نیازها کرده‌اند
    - هر نیاز چقدر از طریق فروش محصولات تأمین شده
    """
    service = ImpactReportService(db)
    return await service.generate_impact_report(start_date, end_date, charity_id, need_id)


@router.get("/charity/{charity_id}")
async def get_charity_impact_report(
        charity_id: int,
        year: Optional[int] = None,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER"))
):
    """
    گزارش تأثیر خیریه - درصد تأمین نیازها از طریق فروش محصولات
    """
    service = ImpactReportService(db)
    return await service.generate_charity_impact_report(charity_id, year)


@router.get("/top-products")
async def get_top_impact_products(
        limit: int = Query(10, ge=1, le=50),
        period: str = Query("month", regex="^(week|month|quarter|year)$"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER"))
):
    """
    رتبه‌بندی محصولات بر اساس میزان تأثیر در تأمین نیازها
    """
    end_date = datetime.utcnow()

    if period == "week":
        start_date = end_date - timedelta(days=7)
    elif period == "month":
        start_date = end_date - timedelta(days=30)
    elif period == "quarter":
        start_date = end_date - timedelta(days=90)
    elif period == "year":
        start_date = end_date - timedelta(days=365)
    else:
        start_date = end_date - timedelta(days=30)

    service = ImpactReportService(db)
    report = await service.generate_impact_report(start_date, end_date)

    return {
        "period": period,
        "top_products": report["top_impact_products"][:limit],
        "generated_at": datetime.utcnow().isoformat()
    }