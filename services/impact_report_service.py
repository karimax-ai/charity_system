# app/services/impact_report_service.py - فایل جدید

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict

from models.order import Order, OrderItem
from models.need_ad import NeedAd
from models.product import Product
from models.charity import Charity


class ImpactReportService:
    """سرویس گزارش تأثیر فروش محصولات بر آگهی‌های نیاز"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_impact_report(
            self,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None,
            charity_id: Optional[int] = None,
            need_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        گزارش تأثیر فروش محصولات بر آگهی‌های نیاز
        - هر محصول چقدر به تأمین کدام نیاز کمک کرده
        - چه درصدی از نیازها از طریق فروش محصولات تأمین شده
        - رتبه‌بندی محصولات بر اساس تأثیرگذاری
        """

        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        # ========== 1. دریافت سفارش‌هایی که به نیازها مرتبط هستند ==========
        orders_query = select(Order).where(
            and_(
                Order.created_at.between(start_date, end_date),
                Order.need_id.isnot(None),  # فقط سفارش‌های مرتبط با نیاز
                Order.status.in_(["delivered", "confirmed", "shipped"])
            )
        )

        if charity_id:
            orders_query = orders_query.where(Order.charity_id == charity_id)
        if need_id:
            orders_query = orders_query.where(Order.need_id == need_id)

        orders_result = await self.db.execute(orders_query)
        orders = orders_result.scalars().all()

        # ========== 2. گروه‌بندی بر اساس نیاز ==========
        need_orders = defaultdict(lambda: {
            "orders": [],
            "total_amount": 0,
            "charity_amount": 0,
            "products": defaultdict(lambda: {
                "quantity": 0,
                "amount": 0,
                "charity_amount": 0
            })
        })

        for order in orders:
            need_orders[order.need_id]["orders"].append(order)
            need_orders[order.need_id]["total_amount"] += order.grand_total or 0
            need_orders[order.need_id]["charity_amount"] += order.charity_amount or 0

            # دریافت آیتم‌های سفارش
            items_query = select(OrderItem).where(OrderItem.order_id == order.id)
            items_result = await self.db.execute(items_query)
            items = items_result.scalars().all()

            for item in items:
                product_id = item.product_id
                need_orders[order.need_id]["products"][product_id]["quantity"] += item.quantity
                need_orders[order.need_id]["products"][product_id]["amount"] += item.subtotal or 0
                need_orders[order.need_id]["products"][product_id]["charity_amount"] += item.charity_total or 0

        # ========== 3. دریافت اطلاعات کامل نیازها ==========
        need_ids = list(need_orders.keys())
        needs_data = {}

        if need_ids:
            needs_query = select(NeedAd).where(NeedAd.id.in_(need_ids))
            needs_result = await self.db.execute(needs_query)
            needs = needs_result.scalars().all()

            for need in needs:
                needs_data[need.id] = need

        # ========== 4. دریافت اطلاعات محصولات ==========
        all_product_ids = set()
        for need_data in need_orders.values():
            all_product_ids.update(need_data["products"].keys())

        products_data = {}
        if all_product_ids:
            products_query = select(Product).where(Product.id.in_(all_product_ids))
            products_result = await self.db.execute(products_query)
            products = products_result.scalars().all()

            for product in products:
                products_data[product.id] = product

        # ========== 5. ساخت خروجی ==========
        impact_by_need = []
        total_need_amount = 0
        total_covered_by_products = 0

        for need_id, need_info in need_orders.items():
            need = needs_data.get(need_id)
            if not need:
                continue

            # محاسبه درصد تأمین شده از طریق فروش محصولات
            covered_amount = need_info["total_amount"]
            target_amount = need.target_amount or 1
            coverage_percentage = (covered_amount / target_amount * 100) if target_amount > 0 else 0

            total_need_amount += target_amount
            total_covered_by_products += covered_amount

            # محصولات مؤثر در این نیاز
            top_products = []
            for product_id, product_stats in need_info["products"].items():
                product = products_data.get(product_id)
                if product:
                    top_products.append({
                        "product_id": product_id,
                        "product_name": product.name,
                        "vendor_id": product.vendor_id,
                        "quantity_sold": product_stats["quantity"],
                        "revenue": round(product_stats["amount"], 0),
                        "charity_contribution": round(product_stats["charity_amount"], 0),
                        "impact_percentage": round(
                            (product_stats["charity_amount"] / need_info["charity_amount"] * 100)
                            if need_info["charity_amount"] > 0 else 0, 1
                        )
                    })

            # مرتب‌سازی بر اساس بیشترین تأثیر
            top_products.sort(key=lambda x: x["charity_contribution"], reverse=True)

            impact_by_need.append({
                "need_id": need_id,
                "need_title": need.title,
                "need_category": need.category,
                "target_amount": round(target_amount, 0),
                "collected_amount": round(need.collected_amount or 0, 0),
                "covered_by_products": round(covered_amount, 0),
                "coverage_percentage": round(coverage_percentage, 1),
                "orders_count": len(need_info["orders"]),
                "top_products": top_products[:5],  # 5 محصول برتر
                "is_fully_funded": coverage_percentage >= 100
            })

        # ========== 6. رتبه‌بندی محصولات بر اساس تأثیرگذاری ==========
        product_impact = defaultdict(lambda: {
            "product_id": 0,
            "product_name": "",
            "vendor_id": 0,
            "vendor_name": "",
            "needs_helped": set(),
            "total_quantity": 0,
            "total_revenue": 0,
            "total_charity": 0,
            "needs_count": 0
        })

        for need_id, need_info in need_orders.items():
            for product_id, product_stats in need_info["products"].items():
                product = products_data.get(product_id)
                if product:
                    key = product_id
                    product_impact[key]["product_id"] = product_id
                    product_impact[key]["product_name"] = product.name
                    product_impact[key]["vendor_id"] = product.vendor_id
                    product_impact[key]["needs_helped"].add(need_id)
                    product_impact[key]["total_quantity"] += product_stats["quantity"]
                    product_impact[key]["total_revenue"] += product_stats["amount"]
                    product_impact[key]["total_charity"] += product_stats["charity_amount"]

        # تبدیل set به count و لیست
        top_products_list = []
        for product_id, stats in product_impact.items():
            top_products_list.append({
                "product_id": stats["product_id"],
                "product_name": stats["product_name"],
                "vendor_id": stats["vendor_id"],
                "needs_helped_count": len(stats["needs_helped"]),
                "total_quantity_sold": stats["total_quantity"],
                "total_revenue": round(stats["total_revenue"], 0),
                "total_charity_contribution": round(stats["total_charity"], 0),
                "impact_score": round(
                    stats["total_charity"] * 0.7 + len(stats["needs_helped"]) * 30, 1
                )
            })

        # مرتب‌سازی بر اساس امتیاز تأثیر
        top_products_list.sort(key=lambda x: x["impact_score"], reverse=True)

        # ========== 7. آمار کلی ==========
        summary = {
            "total_needs_analyzed": len(impact_by_need),
            "total_needs_amount": round(total_need_amount, 0),
            "total_covered_by_products": round(total_covered_by_products, 0),
            "overall_coverage_percentage": round(
                (total_covered_by_products / total_need_amount * 100) if total_need_amount > 0 else 0, 1
            ),
            "fully_funded_needs": len([n for n in impact_by_need if n["is_fully_funded"]]),
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            }
        }

        return {
            "summary": summary,
            "impact_by_need": impact_by_need,
            "top_impact_products": top_products_list[:10],  # 10 محصول برتر
            "generated_at": datetime.utcnow().isoformat()
        }

    async def generate_charity_impact_report(
            self,
            charity_id: int,
            year: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        گزارش تأثیر خیریه - چند درصد از نیازها از طریق فروش محصولات تأمین شده
        """
        if not year:
            year = datetime.utcnow().year

        start_date = datetime(year, 1, 1)
        end_date = datetime(year, 12, 31)

        # کل نیازهای خیریه
        needs_query = select(NeedAd).where(
            and_(
                NeedAd.charity_id == charity_id,
                NeedAd.created_at.between(start_date, end_date)
            )
        )
        needs_result = await self.db.execute(needs_query)
        needs = needs_result.scalars().all()

        # سفارش‌های مرتبط با نیازهای این خیریه
        orders_query = select(Order).where(
            and_(
                Order.charity_id == charity_id,
                Order.need_id.isnot(None),
                Order.created_at.between(start_date, end_date),
                Order.status.in_(["delivered", "confirmed"])
            )
        )
        orders_result = await self.db.execute(orders_query)
        orders = orders_result.scalars().all()

        total_needs_amount = sum((n.target_amount or 0) for n in needs)
        total_orders_amount = sum((o.charity_amount or 0) for o in orders)

        return {
            "charity_id": charity_id,
            "year": year,
            "total_needs": len(needs),
            "total_needs_amount": round(total_needs_amount, 0),
            "total_funded_by_products": round(total_orders_amount, 0),
            "products_funding_percentage": round(
                (total_orders_amount / total_needs_amount * 100) if total_needs_amount > 0 else 0, 1
            ),
            "needs_fully_funded_by_products": len([
                o for o in orders
                if o.need_id and any(
                    n.id == o.need_id and (n.collected_amount or 0) >= (n.target_amount or 0) for n in needs)
            ])
        }