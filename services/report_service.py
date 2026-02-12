# app/services/report_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from fastapi import HTTPException

from models.order import Order, OrderItem
from models.donation import Donation
from models.need_ad import NeedAd
from models.product import Product
from models.charity import Charity
from core.report_generator import ReportGenerator
from schemas.report import (
    ReportRequest, ReportFilter, DateRange,
    ReportType
)


class ReportService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_report(self, request: ReportRequest) -> Dict[str, Any]:
        """تولید گزارش بر اساس نوع"""

        # دریافت بازه زمانی
        date_range = await self._get_date_range(request.filters)

        if request.report_type == ReportType.SALES:
            return await self._generate_sales_report(date_range, request.filters)
        elif request.report_type == ReportType.DONATIONS:
            return await self._generate_donations_report(date_range, request.filters)
        elif request.report_type == ReportType.NEEDS:
            return await self._generate_needs_report(date_range, request.filters)
        elif request.report_type == ReportType.PRODUCTS:
            return await self._generate_products_report(request.filters)
        elif request.report_type == ReportType.FINANCIAL:
            return await self._generate_financial_report(date_range, request.filters)
        elif request.report_type == ReportType.CHARITIES:
            return await self._generate_charities_report(request.filters)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported report type: {request.report_type}")

    async def _generate_sales_report(self, date_range: Dict, filters: ReportFilter) -> Dict[str, Any]:
        """گزارش فروش"""

        # دریافت سفارشات
        orders_query = select(Order).where(
            and_(
                Order.created_at.between(date_range["start"], date_range["end"]),
                Order.status != "cancelled"
            )
        )

        if filters.charity_id:
            orders_query = orders_query.where(Order.charity_id == filters.charity_id)

        orders_result = await self.db.execute(orders_query)
        orders = orders_result.scalars().all()

        # دریافت آیتم‌های سفارش
        order_ids = [o.id for o in orders]
        items = []
        if order_ids:
            items_query = select(OrderItem).where(OrderItem.order_id.in_(order_ids))
            items_result = await self.db.execute(items_query)
            items = items_result.scalars().all()

        # تبدیل به دیکشنری
        orders_data = [self._order_to_dict(o) for o in orders]
        items_data = [self._item_to_dict(i) for i in items]

        # محاسبات
        report_data = ReportGenerator.generate_sales_report(orders_data, items_data)

        # آمار روزانه و ماهانه
        report_data["daily_stats"] = await self._group_by_period(orders, "day")
        report_data["monthly_stats"] = await self._group_by_period(orders, "month")
        report_data["generated_at"] = datetime.utcnow()

        # تکمیل اطلاعات
        report_data = await self._enrich_sales_report(report_data)

        return report_data

    async def _generate_donations_report(self, date_range: Dict, filters: ReportFilter) -> Dict[str, Any]:
        """گزارش کمک‌ها"""

        query = select(Donation).where(
            and_(
                Donation.created_at.between(date_range["start"], date_range["end"]),
                Donation.status == "completed"
            )
        )

        if filters.charity_id:
            query = query.where(Donation.charity_id == filters.charity_id)
        if filters.need_id:
            query = query.where(Donation.need_id == filters.need_id)

        result = await self.db.execute(query)
        donations = result.scalars().all()

        donations_data = [self._donation_to_dict(d) for d in donations]

        report_data = ReportGenerator.generate_donations_report(donations_data)
        report_data["daily_stats"] = await self._group_donations_by_period(donations, "day")
        report_data["monthly_stats"] = await self._group_donations_by_period(donations, "month")
        report_data["generated_at"] = datetime.utcnow()

        return report_data

    async def _generate_needs_report(self, date_range: Dict, filters: ReportFilter) -> Dict[str, Any]:
        """گزارش نیازها"""

        query = select(NeedAd).where(
            NeedAd.created_at.between(date_range["start"], date_range["end"])
        )

        if filters.charity_id:
            query = query.where(NeedAd.charity_id == filters.charity_id)
        if filters.category:
            query = query.where(NeedAd.category == filters.category)

        result = await self.db.execute(query)
        needs = result.scalars().all()

        needs_data = [self._need_to_dict(n) for n in needs]

        report_data = ReportGenerator.generate_needs_report(needs_data)
        report_data["monthly_trend"] = await self._group_needs_by_period(needs, "month")
        report_data["generated_at"] = datetime.utcnow()

        return report_data

    async def _generate_products_report(self, filters: ReportFilter) -> Dict[str, Any]:
        """گزارش محصولات"""

        query = select(Product)

        if filters.vendor_id:
            query = query.where(Product.vendor_id == filters.vendor_id)
        if filters.category:
            query = query.where(Product.category == filters.category)

        result = await self.db.execute(query)
        products = result.scalars().all()

        # دریافت آمار فروش
        date_range = await self._get_date_range(filters)
        sales_query = select(OrderItem).join(
            Order, OrderItem.order_id == Order.id
        ).where(
            and_(
                Order.created_at.between(date_range["start"], date_range["end"]),
                Order.status == "delivered"
            )
        )

        sales_result = await self.db.execute(sales_query)
        sales = sales_result.scalars().all()

        products_data = [self._product_to_dict(p) for p in products]
        sales_data = [self._item_to_dict(s) for s in sales]

        report_data = ReportGenerator.generate_products_report(products_data, sales_data)
        report_data["generated_at"] = datetime.utcnow()

        return report_data

    async def _generate_financial_report(self, date_range: Dict, filters: ReportFilter) -> Dict[str, Any]:
        """گزارش مالی"""

        # سفارشات
        orders_query = select(Order).where(
            and_(
                Order.created_at.between(date_range["start"], date_range["end"]),
                Order.status.in_(["delivered", "shipped", "confirmed"])
            )
        )

        if filters.charity_id:
            orders_query = orders_query.where(Order.charity_id == filters.charity_id)

        orders_result = await self.db.execute(orders_query)
        orders = orders_result.scalars().all()

        # کمک‌ها
        donations_query = select(Donation).where(
            and_(
                Donation.created_at.between(date_range["start"], date_range["end"]),
                Donation.status == "completed"
            )
        )

        if filters.charity_id:
            donations_query = donations_query.where(Donation.charity_id == filters.charity_id)

        donations_result = await self.db.execute(donations_query)
        donations = donations_result.scalars().all()

        orders_data = [self._order_to_dict(o) for o in orders]
        donations_data = [self._donation_to_dict(d) for d in donations]

        report_data = ReportGenerator.generate_financial_report(orders_data, donations_data)
        report_data["monthly_revenue"] = await self._group_by_period(orders, "month")
        report_data["generated_at"] = datetime.utcnow()

        return report_data

    async def _generate_charities_report(self, filters: ReportFilter) -> Dict[str, Any]:
        """گزارش خیریه‌ها"""

        query = select(Charity)

        if filters.search_text:
            query = query.where(
                or_(
                    Charity.name.ilike(f"%{filters.search_text}%"),
                    Charity.description.ilike(f"%{filters.search_text}%")
                )
            )

        result = await self.db.execute(query)
        charities = result.scalars().all()

        charity_stats = []
        for charity in charities:
            needs_count = await self.db.scalar(
                select(func.count(NeedAd.id)).where(NeedAd.charity_id == charity.id)
            )

            donations_total = await self.db.scalar(
                select(func.coalesce(func.sum(Donation.amount), 0))
                .where(
                    and_(
                        Donation.charity_id == charity.id,
                        Donation.status == "completed"
                    )
                )
            )

            orders_total = await self.db.scalar(
                select(func.coalesce(func.sum(Order.charity_amount), 0))
                .where(
                    and_(
                        Order.charity_id == charity.id,
                        Order.status.in_(["delivered", "confirmed"])
                    )
                )
            )

            charity_stats.append({
                "charity_id": charity.id,
                "charity_name": charity.name,
                "verified": charity.verified,
                "needs_count": needs_count or 0,
                "donations_total": float(donations_total or 0),
                "orders_total": float(orders_total or 0),
                "total_received": float((donations_total or 0) + (orders_total or 0))
            })

        return {
            "total_charities": len(charities),
            "verified_charities": len([c for c in charities if c.verified]),
            "charities": charity_stats,
            "generated_at": datetime.utcnow()
        }

    # ---------- Helper Methods ----------
    async def _get_date_range(self, filters: ReportFilter) -> Dict[str, datetime]:
        """تعیین بازه زمانی"""
        end = datetime.utcnow()

        if filters.date_range:
            start = filters.date_range.start_date
            end = filters.date_range.end_date
        elif filters.period:
            if filters.period == "daily":
                start = end - timedelta(days=1)
            elif filters.period == "weekly":
                start = end - timedelta(weeks=1)
            elif filters.period == "monthly":
                start = end - timedelta(days=30)
            elif filters.period == "quarterly":
                start = end - timedelta(days=90)
            elif filters.period == "yearly":
                start = end - timedelta(days=365)
            else:
                start = end - timedelta(days=30)
        else:
            start = end - timedelta(days=30)

        return {"start": start, "end": end}

    async def _group_by_period(self, items: List, period: str) -> List[Dict]:
        """گروه‌بندی سفارشات بر اساس دوره"""
        from collections import defaultdict

        grouped = defaultdict(lambda: {"count": 0, "total": 0, "charity": 0})

        for item in items:
            if period == "day":
                key = item.created_at.strftime("%Y-%m-%d")
            elif period == "month":
                key = item.created_at.strftime("%Y-%m")
            elif period == "year":
                key = item.created_at.strftime("%Y")
            else:
                key = item.created_at.strftime("%Y-%m-%d")

            grouped[key]["count"] += 1
            grouped[key]["total"] += item.grand_total or 0
            grouped[key]["charity"] += item.charity_amount or 0

        return [
            {
                "period": k,
                "order_count": v["count"],
                "revenue": round(v["total"], 0),
                "charity_amount": round(v["charity"], 0)
            }
            for k, v in sorted(grouped.items())
        ]

    async def _group_donations_by_period(self, items: List, period: str) -> List[Dict]:
        """گروه‌بندی کمک‌ها بر اساس دوره"""
        from collections import defaultdict

        grouped = defaultdict(lambda: {"count": 0, "total": 0})

        for item in items:
            if period == "day":
                key = item.created_at.strftime("%Y-%m-%d")
            elif period == "month":
                key = item.created_at.strftime("%Y-%m")
            else:
                key = item.created_at.strftime("%Y-%m-%d")

            grouped[key]["count"] += 1
            grouped[key]["total"] += item.amount or 0

        return [
            {
                "period": k,
                "donation_count": v["count"],
                "total_amount": round(v["total"], 0)
            }
            for k, v in sorted(grouped.items())
        ]

    async def _group_needs_by_period(self, items: List, period: str) -> List[Dict]:
        """گروه‌بندی نیازها بر اساس دوره"""
        from collections import defaultdict

        grouped = defaultdict(lambda: {"count": 0})

        for item in items:
            if period == "month":
                key = item.created_at.strftime("%Y-%m")
            else:
                key = item.created_at.strftime("%Y-%m")

            grouped[key]["count"] += 1

        return [
            {
                "period": k,
                "needs_count": v["count"]
            }
            for k, v in sorted(grouped.items())
        ]

    async def _enrich_sales_report(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """تکمیل گزارش فروش با اطلاعات اضافی"""

        # اضافه کردن نام محصولات
        for product in report.get("by_product", []):
            prod = await self.db.get(Product, product["product_id"])
            if prod:
                product["product_name"] = prod.name
                product["category"] = prod.category
                product["vendor_id"] = prod.vendor_id
                if prod.vendor:
                    product["vendor_name"] = prod.vendor.username

        # اضافه کردن نام خیریه‌ها
        for charity in report.get("by_charity", []):
            ch = await self.db.get(Charity, charity["charity_id"])
            if ch:
                charity["charity_name"] = ch.name

        return report

    def _order_to_dict(self, order: Order) -> Dict[str, Any]:
        return {
            "id": order.id,
            "order_number": order.order_number,
            "status": order.status,
            "payment_status": order.payment_status,
            "subtotal": order.subtotal,
            "shipping_cost": order.shipping_cost,
            "tax_amount": order.tax_amount,
            "discount_amount": order.discount_amount,
            "charity_amount": order.charity_amount,
            "grand_total": order.grand_total,
            "customer_id": order.customer_id,
            "charity_id": order.charity_id,
            "need_id": order.need_id,
            "created_at": order.created_at,
            "paid_at": order.paid_at
        }

    def _item_to_dict(self, item: OrderItem) -> Dict[str, Any]:
        return {
            "id": item.id,
            "order_id": item.order_id,
            "product_id": item.product_id,
            "product_name": item.product_name,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "subtotal": item.subtotal,
            "charity_total": item.charity_total
        }

    def _donation_to_dict(self, donation: Donation) -> Dict[str, Any]:
        return {
            "id": donation.id,
            "amount": donation.amount,
            "payment_method": donation.payment_method,
            "status": donation.status,
            "donor_id": donation.donor_id,
            "charity_id": donation.charity_id,
            "need_id": donation.need_id,
            "created_at": donation.created_at,
            "completed_at": donation.completed_at
        }

    def _need_to_dict(self, need: NeedAd) -> Dict[str, Any]:
        return {
            "id": need.id,
            "title": need.title,
            "category": need.category,
            "target_amount": need.target_amount,
            "collected_amount": need.collected_amount,
            "status": need.status,
            "is_urgent": need.is_urgent,
            "is_emergency": need.is_emergency,
            "charity_id": need.charity_id,
            "created_at": need.created_at
        }

    def _product_to_dict(self, product: Product) -> Dict[str, Any]:
        return {
            "id": product.id,
            "name": product.name,
            "category": product.category,
            "price": product.price,
            "stock_quantity": product.stock_quantity,
            "status": product.status,
            "vendor_id": product.vendor_id,
            "charity_percentage": product.charity_percentage,
            "charity_fixed_amount": product.charity_fixed_amount,
            "created_at": product.created_at
        }