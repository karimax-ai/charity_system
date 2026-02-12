# app/api/v1/endpoints/report.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any
from datetime import datetime

from core.database import get_db
from core.permissions import get_current_user, require_roles
from models.user import User
from services.report_service import ReportService
from services.financial_report import FinancialReportService
from schemas.report import (
    ReportRequest, ReportFilter, DateRange,
    ReportType, ReportFormat, SalesReport,
    DonationsReport, NeedsReport, ProductsReport,
    FinancialReport
)

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.post("/sales", response_model=SalesReport)
async def get_sales_report(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        period: str = Query("monthly", regex="^(daily|weekly|monthly|quarterly|yearly)$"),
        charity_id: Optional[int] = None,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER"))
):
    """گزارش فروش - خروجی JSON برای فرانت"""

    service = ReportService(db)

    filters = ReportFilter(
        date_range=DateRange(start_date=start_date, end_date=end_date) if start_date or end_date else None,
        period=period,
        charity_id=charity_id
    )

    request = ReportRequest(
        report_type=ReportType.SALES,
        format=ReportFormat.JSON,
        filters=filters
    )

    return await service.generate_report(request)


@router.post("/donations", response_model=DonationsReport)
async def get_donations_report(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        period: str = Query("monthly", regex="^(daily|weekly|monthly|yearly)$"),
        charity_id: Optional[int] = None,
        need_id: Optional[int] = None,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER"))
):
    """گزارش کمک‌ها - خروجی JSON برای فرانت"""

    service = ReportService(db)

    filters = ReportFilter(
        date_range=DateRange(start_date=start_date, end_date=end_date) if start_date or end_date else None,
        period=period,
        charity_id=charity_id,
        need_id=need_id
    )

    request = ReportRequest(
        report_type=ReportType.DONATIONS,
        format=ReportFormat.JSON,
        filters=filters
    )

    return await service.generate_report(request)


@router.post("/needs", response_model=NeedsReport)
async def get_needs_report(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        period: str = Query("monthly", regex="^(daily|weekly|monthly|yearly)$"),
        charity_id: Optional[int] = None,
        category: Optional[str] = None,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER"))
):
    """گزارش نیازها - خروجی JSON برای فرانت"""

    service = ReportService(db)

    filters = ReportFilter(
        date_range=DateRange(start_date=start_date, end_date=end_date) if start_date or end_date else None,
        period=period,
        charity_id=charity_id,
        category=category
    )

    request = ReportRequest(
        report_type=ReportType.NEEDS,
        format=ReportFormat.JSON,
        filters=filters
    )

    return await service.generate_report(request)


@router.post("/products", response_model=ProductsReport)
async def get_products_report(
        vendor_id: Optional[int] = None,
        category: Optional[str] = None,
        low_stock_only: bool = False,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER", "VENDOR"))
):
    """گزارش محصولات - خروجی JSON برای فرانت"""

    service = ReportService(db)

    filters = ReportFilter(
        vendor_id=vendor_id if vendor_id else current_user.id if "VENDOR" in [r.key for r in
                                                                              current_user.roles] else None,
        category=category
    )

    request = ReportRequest(
        report_type=ReportType.PRODUCTS,
        format=ReportFormat.JSON,
        filters=filters
    )

    report = await service.generate_report(request)

    if low_stock_only:
        report["low_stock"] = report.get("low_stock", [])

    return report


@router.post("/financial", response_model=FinancialReport)
async def get_financial_report(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        period: str = Query("monthly", regex="^(monthly|quarterly|yearly)$"),
        charity_id: Optional[int] = None,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_roles("ADMIN"))
):
    """گزارش مالی - خروجی JSON برای فرانت"""

    service = ReportService(db)

    filters = ReportFilter(
        date_range=DateRange(start_date=start_date, end_date=end_date) if start_date or end_date else None,
        period=period,
        charity_id=charity_id
    )

    request = ReportRequest(
        report_type=ReportType.FINANCIAL,
        format=ReportFormat.JSON,
        filters=filters
    )

    return await service.generate_report(request)


@router.get("/charities")
async def get_charities_report(
        search_text: Optional[str] = None,
        verified_only: bool = False,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER"))
):
    """گزارش خیریه‌ها - خروجی JSON برای فرانت"""

    service = ReportService(db)

    filters = ReportFilter(search_text=search_text)
    report = await service._generate_charities_report(filters)

    if verified_only:
        report["charities"] = [c for c in report["charities"] if c["verified"]]
        report["verified_charities"] = len(report["charities"])

    return report


@router.get("/financial/income-statement/{year}")
async def get_income_statement(
        year: int,
        charity_id: Optional[int] = None,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_roles("ADMIN"))
):
    """صورت سود و زیان سالانه"""

    service = FinancialReportService(db)
    return await service.generate_income_statement(year, charity_id)


@router.get("/financial/charity/{charity_id}/{year}")
async def get_charity_financials(
        charity_id: int,
        year: int,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER"))
):
    """گزارش مالی خیریه"""

    service = FinancialReportService(db)
    return await service.generate_charity_financials(charity_id, year)