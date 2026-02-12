# app/api/v1/endpoints/export.py
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, Optional
from datetime import datetime
import os

from core.database import get_db
from core.permissions import get_current_user, require_roles
from models.user import User
from services.export_service import ExportService
from services.report_service import ReportService
from schemas.export import ExportRequest, ExportTemplate, ExportFormat, ExportResult
from schemas.report import ReportRequest, ReportFilter, ReportType, DateRange

router = APIRouter()


@router.post("/report", response_model=ExportResult)
async def export_report(
        request: ExportRequest,
        background_tasks: BackgroundTasks,
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER")),
        db: AsyncSession = Depends(get_db)
):
    """خروجی‌گیری از گزارش به صورت فایل (Excel, PDF, CSV)"""

    report_service = ReportService(db)
    export_service = ExportService()

    report_type = None
    filters = ReportFilter()

    if request.template == ExportTemplate.SALES_SUMMARY:
        report_type = ReportType.SALES
    elif request.template == ExportTemplate.DONATIONS_DETAILED:
        report_type = ReportType.DONATIONS
    elif request.template == ExportTemplate.NEEDS_REPORT:
        report_type = ReportType.NEEDS
    elif request.template == ExportTemplate.FINANCIAL_STATEMENT:
        report_type = ReportType.FINANCIAL
    elif request.template == ExportTemplate.CHARITY_IMPACT:
        report_type = ReportType.CHARITIES

    if request.date_range:
        filters.date_range = DateRange(
            start_date=request.date_range.get("start"),
            end_date=request.date_range.get("end")
        )

    report_request = ReportRequest(
        report_type=report_type,
        format=ExportFormat.JSON,
        filters=filters,
        title=request.title
    )

    report_data = await report_service.generate_report(report_request)
    export_data = await prepare_export_data(report_data, request.template)
    result = await export_service.export_data(request, export_data)

    return result


@router.get("/download/{filename}")
async def download_export(
        filename: str,
        current_user: User = Depends(get_current_user)
):
    """دانلود فایل خروجی"""
    filepath = os.path.join("exports", filename)

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=filepath,
        filename=filename,
        media_type="application/octet-stream"
    )


@router.delete("/cleanup")
async def cleanup_exports(
        days: int = Query(7, ge=1),
        current_user: User = Depends(require_roles("ADMIN"))
):
    """پاک‌سازی فایل‌های قدیمی"""
    deleted = 0
    cutoff = datetime.utcnow().timestamp() - (days * 24 * 60 * 60)

    for filename in os.listdir("exports"):
        filepath = os.path.join("exports", filename)
        if os.path.getmtime(filepath) < cutoff:
            os.remove(filepath)
            deleted += 1

    return {
        "success": True,
        "deleted_files": deleted,
        "message": f"Cleaned up {deleted} files older than {days} days"
    }


async def prepare_export_data(report_data: Dict[str, Any], template: ExportTemplate) -> Dict[str, Any]:
    """آماده‌سازی داده‌ها برای خروجی"""

    if template == ExportTemplate.SALES_SUMMARY:
        return {
            "sheets": [
                {
                    "name": "خلاصه فروش",
                    "columns": [
                        {"key": "period", "header": "دوره"},
                        {"key": "order_count", "header": "تعداد سفارش"},
                        {"key": "revenue", "header": "درآمد", "format": "currency"},
                        {"key": "charity_amount", "header": "کمک به خیریه", "format": "currency"}
                    ],
                    "data": report_data.get("daily_stats", [])
                },
                {
                    "name": "محصولات",
                    "columns": [
                        {"key": "product_name", "header": "محصول"},
                        {"key": "quantity_sold", "header": "تعداد فروش"},
                        {"key": "revenue", "header": "درآمد", "format": "currency"},
                        {"key": "charity_amount", "header": "کمک", "format": "currency"}
                    ],
                    "data": report_data.get("by_product", [])
                },
                {
                    "name": "خیریه‌ها",
                    "columns": [
                        {"key": "charity_name", "header": "خیریه"},
                        {"key": "order_count", "header": "تعداد سفارش"},
                        {"key": "charity_amount", "header": "کمک دریافتی", "format": "currency"}
                    ],
                    "data": report_data.get("by_charity", [])
                }
            ]
        }

    elif template == ExportTemplate.DONATIONS_DETAILED:
        return {
            "sheets": [
                {
                    "name": "خلاصه کمک‌ها",
                    "columns": [
                        {"key": "period", "header": "دوره"},
                        {"key": "donation_count", "header": "تعداد کمک"},
                        {"key": "total_amount", "header": "مبلغ کل", "format": "currency"},
                        {"key": "average_amount", "header": "میانگین", "format": "currency"}
                    ],
                    "data": report_data.get("daily_stats", [])
                },
                {
                    "name": "کمک‌ها بر اساس خیریه",
                    "columns": [
                        {"key": "charity_name", "header": "خیریه"},
                        {"key": "donation_count", "header": "تعداد کمک"},
                        {"key": "total_amount", "header": "مبلغ کل", "format": "currency"}
                    ],
                    "data": report_data.get("by_charity", [])
                }
            ]
        }

    elif template == ExportTemplate.CHARITY_IMPACT:
        return {
            "sheets": [
                {
                    "name": "تأثیر خیریه‌ها",
                    "columns": [
                        {"key": "charity_name", "header": "خیریه"},
                        {"key": "needs_count", "header": "تعداد نیاز"},
                        {"key": "donations_total", "header": "کمک‌های مستقیم", "format": "currency"},
                        {"key": "orders_total", "header": "کمک از فروش", "format": "currency"},
                        {"key": "total_received", "header": "جمع کل", "format": "currency"}
                    ],
                    "data": report_data.get("charities", [])
                }
            ]
        }

    else:
        return {
            "sheets": [
                {
                    "name": "گزارش",
                    "columns": [
                        {"key": k, "header": k}
                        for k in report_data.keys()
                    ],
                    "data": [report_data]
                }
            ]
        }