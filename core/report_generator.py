# app/core/report_generator.py
from typing import Dict, Any, List
from datetime import datetime
from collections import defaultdict


class ReportGenerator:
    """موتور محاسبات گزارش - فقط داده، بدون گرافیک"""

    @staticmethod
    def generate_sales_report(orders: List[Dict], items: List[Dict]) -> Dict[str, Any]:
        """محاسبه آمار فروش"""

        total_orders = len(orders)
        total_revenue = sum(o.get("grand_total", 0) for o in orders)
        total_charity = sum(o.get("charity_amount", 0) for o in orders)
        unique_customers = len(set(o.get("customer_id") for o in orders if o.get("customer_id")))

        completed_orders = len([o for o in orders if o.get("status") == "delivered"])
        cancelled_orders = len([o for o in orders if o.get("status") == "cancelled"])

        # فروش بر اساس محصول
        product_sales = defaultdict(lambda: {"quantity": 0, "revenue": 0, "charity": 0})
        for item in items:
            pid = item.get("product_id")
            product_sales[pid]["quantity"] += item.get("quantity", 0)
            product_sales[pid]["revenue"] += item.get("subtotal", 0)
            product_sales[pid]["charity"] += item.get("charity_total", 0)

        # فروش بر اساس خیریه
        charity_sales = defaultdict(lambda: {"orders": 0, "revenue": 0, "charity": 0})
        for order in orders:
            cid = order.get("charity_id")
            if cid:
                charity_sales[cid]["orders"] += 1
                charity_sales[cid]["revenue"] += order.get("grand_total", 0)
                charity_sales[cid]["charity"] += order.get("charity_amount", 0)

        return {
            "summary": {
                "total_orders": total_orders,
                "total_revenue": round(total_revenue, 0),
                "average_order_value": round(total_revenue / total_orders, 0) if total_orders else 0,
                "total_items_sold": sum(item.get("quantity", 0) for item in items),
                "total_charity_amount": round(total_charity, 0),
                "charity_percentage": round((total_charity / total_revenue * 100), 2) if total_revenue else 0,
                "unique_customers": unique_customers,
                "completed_orders": completed_orders,
                "cancelled_orders": cancelled_orders
            },
            "by_product": [
                {
                    "product_id": pid,
                    "quantity_sold": stats["quantity"],
                    "revenue": round(stats["revenue"], 0),
                    "charity_amount": round(stats["charity"], 0)
                }
                for pid, stats in product_sales.items()
            ],
            "by_charity": [
                {
                    "charity_id": cid,
                    "order_count": stats["orders"],
                    "revenue": round(stats["revenue"], 0),
                    "charity_amount": round(stats["charity"], 0)
                }
                for cid, stats in charity_sales.items()
            ]
        }

    @staticmethod
    def generate_donations_report(donations: List[Dict]) -> Dict[str, Any]:
        """محاسبه آمار کمک‌ها"""

        total_donations = len(donations)
        total_amount = sum(d.get("amount", 0) for d in donations)

        completed = [d for d in donations if d.get("status") == "completed"]
        pending = [d for d in donations if d.get("status") == "pending"]

        # کمک‌ها بر اساس خیریه
        charity_donations = defaultdict(lambda: {"count": 0, "amount": 0})
        for d in donations:
            cid = d.get("charity_id")
            if cid:
                charity_donations[cid]["count"] += 1
                charity_donations[cid]["amount"] += d.get("amount", 0)

        # کمک‌ها بر اساس نیاز
        need_donations = defaultdict(lambda: {"count": 0, "amount": 0})
        for d in donations:
            nid = d.get("need_id")
            if nid:
                need_donations[nid]["count"] += 1
                need_donations[nid]["amount"] += d.get("amount", 0)

        return {
            "summary": {
                "total_donations": total_donations,
                "total_amount": round(total_amount, 0),
                "average_donation": round(total_amount / total_donations, 0) if total_donations else 0,
                "largest_donation": round(max((d.get("amount", 0) for d in donations), default=0), 0),
                "smallest_donation": round(min((d.get("amount", 0) for d in donations), default=0), 0),
                "unique_donors": len(set(d.get("donor_id") for d in donations if d.get("donor_id"))),
                "completed_donations": len(completed),
                "pending_donations": len(pending)
            },
            "by_charity": [
                {
                    "charity_id": cid,
                    "donation_count": stats["count"],
                    "total_amount": round(stats["amount"], 0)
                }
                for cid, stats in charity_donations.items()
            ],
            "by_need": [
                {
                    "need_id": nid,
                    "donation_count": stats["count"],
                    "total_amount": round(stats["amount"], 0)
                }
                for nid, stats in need_donations.items()
            ],
            "by_payment_method": dict(ReportGenerator._group_by_key(donations, "payment_method", "amount"))
        }

    @staticmethod
    def generate_needs_report(needs: List[Dict]) -> Dict[str, Any]:
        """محاسبه آمار نیازها"""

        total = len(needs)
        active = len([n for n in needs if n.get("status") == "active"])
        completed = len([n for n in needs if n.get("status") == "completed"])
        pending = len([n for n in needs if n.get("status") == "pending"])
        urgent = len([n for n in needs if n.get("is_urgent")])
        emergency = len([n for n in needs if n.get("is_emergency")])

        total_target = sum(n.get("target_amount", 0) for n in needs)
        total_collected = sum(n.get("collected_amount", 0) for n in needs)

        # دسته‌بندی
        by_category = defaultdict(lambda: {"count": 0, "target": 0, "collected": 0})
        for need in needs:
            cat = need.get("category", "other")
            by_category[cat]["count"] += 1
            by_category[cat]["target"] += need.get("target_amount", 0)
            by_category[cat]["collected"] += need.get("collected_amount", 0)

        return {
            "summary": {
                "total_needs": total,
                "active_needs": active,
                "completed_needs": completed,
                "pending_needs": pending,
                "total_target": round(total_target, 0),
                "total_collected": round(total_collected, 0),
                "overall_progress": round((total_collected / total_target * 100), 2) if total_target else 0,
                "urgent_needs": urgent,
                "emergency_needs": emergency
            },
            "by_category": [
                {
                    "category": cat,
                    "count": stats["count"],
                    "target_amount": round(stats["target"], 0),
                    "collected_amount": round(stats["collected"], 0),
                    "progress": round((stats["collected"] / stats["target"] * 100), 2) if stats["target"] else 0
                }
                for cat, stats in by_category.items()
            ],
            "by_status": dict(ReportGenerator._group_by_count(needs, "status")),
            "by_urgency": {
                "urgent": urgent,
                "emergency": emergency,
                "normal": total - urgent - emergency
            }
        }

    @staticmethod
    def generate_products_report(products: List[Dict], sales: List[Dict]) -> Dict[str, Any]:
        """محاسبه آمار محصولات"""

        total_products = len(products)
        active_products = len([p for p in products if p.get("status") == "active"])
        draft_products = len([p for p in products if p.get("status") == "draft"])
        sold_out = len([p for p in products if p.get("stock_quantity", 0) == 0])

        total_value = sum(p.get("price", 0) * p.get("stock_quantity", 0) for p in products)

        # فروش بر اساس فروشنده
        vendor_sales = defaultdict(lambda: {"products": 0, "active": 0, "value": 0})
        for product in products:
            vid = product.get("vendor_id")
            if vid:
                vendor_sales[vid]["products"] += 1
                if product.get("status") == "active":
                    vendor_sales[vid]["active"] += 1
                vendor_sales[vid]["value"] += product.get("price", 0) * product.get("stock_quantity", 0)

        # محصولات با موجودی کم
        low_stock = [
            {
                "product_id": p.get("id"),
                "product_name": p.get("name"),
                "stock_quantity": p.get("stock_quantity", 0),
                "threshold": 10
            }
            for p in products if p.get("stock_quantity", 0) < 10
        ]

        return {
            "summary": {
                "total_products": total_products,
                "active_products": active_products,
                "draft_products": draft_products,
                "sold_out_products": sold_out,
                "total_inventory_value": round(total_value, 0),
                "avg_price": round(sum(p.get("price", 0) for p in products) / total_products,
                                   0) if total_products else 0
            },
            "by_vendor": [
                {
                    "vendor_id": vid,
                    "products_count": stats["products"],
                    "active_products": stats["active"],
                    "total_value": round(stats["value"], 0)
                }
                for vid, stats in vendor_sales.items()
            ],
            "by_category": dict(ReportGenerator._group_by_count(products, "category")),
            "low_stock": low_stock[:20]
        }

    @staticmethod
    def generate_financial_report(orders: List[Dict], donations: List[Dict]) -> Dict[str, Any]:
        """محاسبه آمار مالی"""

        total_revenue = sum(o.get("grand_total", 0) for o in orders)
        total_charity = sum(o.get("charity_amount", 0) for o in orders) + \
                        sum(d.get("amount", 0) for d in donations)
        total_tax = sum(o.get("tax_amount", 0) for o in orders)
        total_shipping = sum(o.get("shipping_cost", 0) for o in orders)
        total_discount = sum(o.get("discount_amount", 0) for o in orders)

        net_revenue = total_revenue - total_tax - total_shipping

        return {
            "summary": {
                "total_revenue": round(total_revenue, 0),
                "total_charity": round(total_charity, 0),
                "total_tax": round(total_tax, 0),
                "total_shipping": round(total_shipping, 0),
                "total_discount": round(total_discount, 0),
                "net_revenue": round(net_revenue, 0),
                "charity_percentage": round((total_charity / total_revenue * 100), 2) if total_revenue else 0,
                "order_count": len(orders)
            },
            "by_payment_method": dict(ReportGenerator._group_by_key(orders, "payment_method", "grand_total"))
        }

    # ---------- Helper Methods ----------
    @staticmethod
    def _group_by_key(items: List[Dict], key: str, value_key: str = None) -> Dict:
        """گروه‌بندی بر اساس کلید"""
        grouped = defaultdict(lambda: {"count": 0, "total": 0})

        for item in items:
            k = item.get(key, "unknown")
            grouped[k]["count"] += 1
            if value_key:
                grouped[k]["total"] += item.get(value_key, 0)

        if value_key:
            return {
                k: {
                    "count": v["count"],
                    "total": round(v["total"], 0)
                }
                for k, v in grouped.items()
            }
        return {k: v["count"] for k, v in grouped.items()}

    @staticmethod
    def _group_by_count(items: List[Dict], key: str) -> Dict:
        """گروه‌بندی و شمارش"""
        grouped = defaultdict(int)
        for item in items:
            k = item.get(key, "unknown")
            grouped[k] += 1
        return dict(grouped)