# app/api/v1/endpoints/report.py - جایگزین کامل
import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
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


# ========== گزارش‌های فروش (ادمین، مدیر خیریه، فروشنده) ==========
@router.post("/sales", response_model=SalesReport)
async def get_sales_report(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        period: str = Query("monthly", regex="^(daily|weekly|monthly|quarterly|yearly)$"),
        charity_id: Optional[int] = None,
        vendor_id: Optional[int] = None,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """گزارش فروش - دسترسی بر اساس نقش"""

    service = ReportService(db)

    # ✅ تعیین سطح دسترسی
    user_roles = [r.key for r in current_user.roles]

    # ادمین: همه چیز
    if "SUPER_ADMIN" in user_roles:
        pass  # بدون محدودیت

    # مدیر خیریه: فقط خیریه‌های خودش
    elif "CHARITY_MANAGER" in user_roles:
        from models.charity import Charity
        result = await db.execute(
            select(Charity.id).where(Charity.manager_id == current_user.id)
        )
        managed_charities = result.scalars().all()
        if charity_id and charity_id not in managed_charities:
            raise HTTPException(status_code=403, detail="شما به این خیریه دسترسی ندارید")
        if not charity_id and managed_charities:
            charity_id = managed_charities[0]  # پیش‌فرض اولین خیریه

    # فروشنده: فقط فروشگاه خودش
    elif "VENDOR" in user_roles:
        from models.shop import Shop
        result = await db.execute(
            select(Shop.id).where(Shop.owner_id == current_user.id)
        )
        shops = result.scalars().all()
        if shops:
            # دریافت سفارشات محصولات این فروشنده
            vendor_id = current_user.id
        else:
            raise HTTPException(status_code=403, detail="شما فروشگاهی ندارید")

    else:
        raise HTTPException(status_code=403, detail="دسترسی به این گزارش ندارید")

    filters = ReportFilter(
        date_range=DateRange(start_date=start_date, end_date=end_date) if start_date or end_date else None,
        period=period,
        charity_id=charity_id,
        vendor_id=vendor_id
    )

    request = ReportRequest(
        report_type=ReportType.SALES,
        format=ReportFormat.JSON,
        filters=filters,
        requested_by=current_user.id
    )

    return await service.generate_report(request)


# ========== گزارش کمک‌ها (ادمین، مدیر خیریه، خیر) ==========
@router.post("/donations", response_model=DonationsReport)
async def get_donations_report(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        period: str = Query("monthly", regex="^(daily|weekly|monthly|yearly)$"),
        charity_id: Optional[int] = None,
        need_id: Optional[int] = None,
        donor_id: Optional[int] = None,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """گزارش کمک‌ها - خیرها گزارش خودشان را می‌بینند"""

    service = ReportService(db)
    user_roles = [r.key for r in current_user.roles]

    # ✅ خیر: فقط کمک‌های خودش
    if "DONOR" in user_roles and not any(r in user_roles for r in ["SUPER_ADMIN", "CHARITY_MANAGER"]):
        donor_id = current_user.id

    filters = ReportFilter(
        date_range=DateRange(start_date=start_date, end_date=end_date) if start_date or end_date else None,
        period=period,
        charity_id=charity_id,
        need_id=need_id,
        donor_id=donor_id
    )

    request = ReportRequest(
        report_type=ReportType.DONATIONS,
        format=ReportFormat.JSON,
        filters=filters,
        requested_by=current_user.id
    )

    return await service.generate_report(request)


# ========== گزارش نیازها (ادمین، مدیر خیریه، نیازمند) ==========
@router.post("/needs", response_model=NeedsReport)
async def get_needs_report(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        period: str = Query("monthly", regex="^(daily|weekly|monthly|yearly)$"),
        charity_id: Optional[int] = None,
        category: Optional[str] = None,
        needy_id: Optional[int] = None,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """گزارش نیازها - نیازمندان گزارش خودشان را می‌بینند"""

    service = ReportService(db)
    user_roles = [r.key for r in current_user.roles]

    # ✅ نیازمند: فقط نیازهای خودش
    if "NEEDY" in user_roles and not any(r in user_roles for r in ["SUPER_ADMIN", "CHARITY_MANAGER"]):
        needy_id = current_user.id

    filters = ReportFilter(
        date_range=DateRange(start_date=start_date, end_date=end_date) if start_date or end_date else None,
        period=period,
        charity_id=charity_id,
        category=category,
        needy_id=needy_id
    )

    request = ReportRequest(
        report_type=ReportType.NEEDS,
        format=ReportFormat.JSON,
        filters=filters,
        requested_by=current_user.id
    )

    return await service.generate_report(request)


# ========== گزارش محصولات (ادمین، مدیر خیریه، فروشنده) ==========
@router.get("/report/products")
async def get_products_report(
    category_id: Optional[int] = Query(None),
    shop_id: Optional[int] = Query(None),
    min_stock: Optional[int] = Query(None),
    max_stock: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(require_roles("ADMIN", "VENDOR", "MANAGER")),
    db: AsyncSession = Depends(get_db)
):
    """گزارش محصولات فروشنده/مدیر"""
    from sqlalchemy import select, and_, or_, func
    from models.product import Product
    from models.shop import Shop

    query_conditions = []

    # اگر کاربر VENDOR یا MANAGER هست، فقط محصولات shopهای خودش
    user_roles = [r.key for r in current_user.roles]
    if "VENDOR" in user_roles or "MANAGER" in user_roles:
        # پیدا کردن همه shopهایی که این فروشنده مالک یا مدیرش هست
        shops_result = await db.execute(
            select(Shop.id).where(
                or_(
                    Shop.manager_id == current_user.id,
                    Shop.vendor_id == current_user.id
                )
            )
        )
        shop_ids = [row[0] for row in shops_result.all()]
        query_conditions.append(Product.shop_id.in_(shop_ids))

    # فیلتر دسته‌بندی
    if category_id:
        query_conditions.append(Product.category_id == category_id)

    # فیلتر موجودی
    if min_stock is not None:
        query_conditions.append(Product.stock_quantity >= min_stock)
    if max_stock is not None:
        query_conditions.append(Product.stock_quantity <= max_stock)

    # فیلتر shop مشخص (برای ADMIN)
    if shop_id and "ADMIN" in user_roles:
        query_conditions.append(Product.shop_id == shop_id)

    # شمارش کل
    total_query = select(func.count()).select_from(Product)
    if query_conditions:
        total_query = total_query.where(and_(*query_conditions))

    total = await db.scalar(total_query)

    # صفحه‌بندی
    offset = (page - 1) * limit
    product_query = select(Product)
    if query_conditions:
        product_query = product_query.where(and_(*query_conditions))

    product_query = product_query.order_by(Product.id.asc()).offset(offset).limit(limit)
    result = await db.execute(product_query)
    products = result.scalars().all()

    # ساخت خروجی
    product_list = []
    for product in products:
        product_list.append({
            "id": product.id,
            "name": product.name,
            "sku": product.sku,
            "price": product.price,
            "currency": product.currency,
            "stock_quantity": product.stock_quantity,
            "max_order_quantity": product.max_order_quantity,
            "status": product.status,
            "shop_id": product.shop_id,
            "shop_name": product.shop.name if product.shop else None,
            "vendor_id": product.vendor_id,
            "vendor_name": product.vendor.username if product.vendor else None,
            "created_at": product.created_at,
            "updated_at": product.updated_at
        })

    return {
        "total": total or 0,
        "page": page,
        "limit": limit,
        "total_pages": math.ceil(total / limit) if total and total > 0 else 0,
        "items": product_list
    }



