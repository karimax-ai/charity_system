# app/services/statistics_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, case, extract
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict

from models.donation import Donation
from models.need_ad import NeedAd
from models.user import User
from models.charity import Charity
from models.product import Product


class StatisticsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------- 1️⃣ آمار کمک‌ها ----------
    async def get_donation_statistics(
            self,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None,
            charity_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """آمار کامل کمک‌ها"""

        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=365)

        # آمار کلی
        query = select(
            func.count(Donation.id).label("total_count"),
            func.coalesce(func.sum(Donation.amount), 0).label("total_amount"),
            func.avg(Donation.amount).label("average_amount"),
            func.max(Donation.amount).label("max_amount"),
            func.min(Donation.amount).label("min_amount")
        ).where(
            and_(
                Donation.status == "completed",
                Donation.created_at.between(start_date, end_date)
            )
        )

        if charity_id:
            query = query.where(Donation.charity_id == charity_id)

        result = await self.db.execute(query)
        stats = result.first()

        # آمار روزانه
        daily = await self._get_daily_donations(start_date, end_date, charity_id)

        # آمار ماهانه
        monthly = await self._get_monthly_donations(start_date, end_date, charity_id)

        # روش‌های پرداخت
        payment_methods = await self._get_payment_method_stats(start_date, end_date, charity_id)

        return {
            "period": {
                "start_date": start_date,
                "end_date": end_date,
                "days": (end_date - start_date).days
            },
            "summary": {
                "total_donations": stats.total_count or 0,
                "total_amount": float(stats.total_amount or 0),
                "average_donation": float(stats.average_amount or 0),
                "largest_donation": float(stats.max_amount or 0),
                "smallest_donation": float(stats.min_amount or 0),
            },
            "daily": daily,
            "monthly": monthly,
            "payment_methods": payment_methods,
        }

    # ---------- 2️⃣ آمار نیازها ----------
    async def get_need_statistics(
            self,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None,
            charity_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """آمار نیازها"""

        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=365)

        query = select(NeedAd).where(
            NeedAd.created_at.between(start_date, end_date)
        )

        if charity_id:
            query = query.where(NeedAd.charity_id == charity_id)

        result = await self.db.execute(query)
        needs = result.scalars().all()

        total = len(needs)
        active = sum(1 for n in needs if n.status == "active")
        completed = sum(1 for n in needs if n.status == "completed")
        pending = sum(1 for n in needs if n.status == "pending")
        rejected = sum(1 for n in needs if n.status == "rejected")

        total_target = sum(n.target_amount for n in needs)
        total_collected = sum(n.collected_amount or 0 for n in needs)

        # دسته‌بندی نیازها
        categories = defaultdict(lambda: {"count": 0, "target": 0, "collected": 0})
        for need in needs:
            cat = need.category or "other"
            categories[cat]["count"] += 1
            categories[cat]["target"] += need.target_amount
            categories[cat]["collected"] += need.collected_amount or 0

        return {
            "period": {
                "start_date": start_date,
                "end_date": end_date,
            },
            "summary": {
                "total_needs": total,
                "active_needs": active,
                "completed_needs": completed,
                "pending_needs": pending,
                "rejected_needs": rejected,
                "completion_rate": (completed / total * 100) if total > 0 else 0,
                "total_target_amount": float(total_target),
                "total_collected_amount": float(total_collected),
                "overall_progress": (total_collected / total_target * 100) if total_target > 0 else 0,
            },
            "by_category": [
                {
                    "category": cat,
                    "count": data["count"],
                    "target_amount": float(data["target"]),
                    "collected_amount": float(data["collected"]),
                    "progress": (data["collected"] / data["target"] * 100) if data["target"] > 0 else 0,
                }
                for cat, data in categories.items()
            ],
        }

    # ---------- 3️⃣ آمار کاربران ----------
    async def get_user_statistics(
            self,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """آمار کاربران"""

        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=365)

        total_users = await self.db.scalar(select(func.count(User.id)))

        # کاربران جدید
        new_users = await self.db.scalar(
            select(func.count(User.id))
            .where(User.created_at.between(start_date, end_date))
        )

        # کاربران فعال (کمک کرده‌اند)
        active_donors = await self.db.scalar(
            select(func.count(func.distinct(Donation.donor_id)))
            .where(
                and_(
                    Donation.created_at.between(start_date, end_date),
                    Donation.status == "completed"
                )
            )
        )

        # رشد ماهانه
        monthly_growth = []
        current = start_date.replace(day=1)
        while current <= end_date:
            next_month = (current.replace(day=28) + timedelta(days=4)).replace(day=1)

            count = await self.db.scalar(
                select(func.count(User.id))
                .where(
                    and_(
                        User.created_at >= current,
                        User.created_at < next_month
                    )
                )
            )

            monthly_growth.append({
                "month": current.strftime("%Y-%m"),
                "new_users": count or 0
            })

            current = next_month

        return {
            "period": {
                "start_date": start_date,
                "end_date": end_date,
            },
            "summary": {
                "total_users": total_users or 0,
                "new_users": new_users or 0,
                "active_donors": active_donors or 0,
                "donor_conversion_rate": (active_donors / new_users * 100) if new_users and new_users > 0 else 0,
            },
            "monthly_growth": monthly_growth,
        }

    # ---------- 4️⃣ آمار جغرافیایی ----------
    async def get_geographical_statistics(
            self,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """آمار جغرافیایی کمک‌ها و نیازها"""

        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=365)

        # کمک‌ها بر اساس استان
        donations_by_province = {}
        needs_by_province = {}

        # نیازها
        needs_query = select(NeedAd).where(
            and_(
                NeedAd.created_at.between(start_date, end_date),
                NeedAd.status.in_(["active", "completed"])
            )
        )
        needs_result = await self.db.execute(needs_query)
        needs = needs_result.scalars().all()

        for need in needs:
            if need.province:
                if need.province not in needs_by_province:
                    needs_by_province[need.province] = {
                        "count": 0,
                        "target_amount": 0,
                        "collected_amount": 0,
                    }
                needs_by_province[need.province]["count"] += 1
                needs_by_province[need.province]["target_amount"] += need.target_amount
                needs_by_province[need.province]["collected_amount"] += need.collected_amount or 0

        # کمک‌ها
        donations_query = select(Donation).join(
            NeedAd, Donation.need_id == NeedAd.id, isouter=True
        ).where(
            and_(
                Donation.created_at.between(start_date, end_date),
                Donation.status == "completed"
            )
        )
        donations_result = await self.db.execute(donations_query)
        donations = donations_result.scalars().all()

        for donation in donations:
            if donation.need and donation.need.province:
                province = donation.need.province
                if province not in donations_by_province:
                    donations_by_province[province] = {
                        "count": 0,
                        "total_amount": 0,
                    }
                donations_by_province[province]["count"] += 1
                donations_by_province[province]["total_amount"] += donation.amount

        return {
            "needs_by_province": [
                {
                    "province": p,
                    "count": data["count"],
                    "target_amount": float(data["target_amount"]),
                    "collected_amount": float(data["collected_amount"]),
                    "progress": (data["collected_amount"] / data["target_amount"] * 100) if data[
                                                                                                "target_amount"] > 0 else 0,
                }
                for p, data in needs_by_province.items()
            ],
            "donations_by_province": [
                {
                    "province": p,
                    "donations_count": data["count"],
                    "total_amount": float(data["total_amount"]),
                }
                for p, data in donations_by_province.items()
            ],
        }

    # ---------- 5️⃣ آمار فروش محصولات ----------
    async def get_product_sales_statistics(
            self,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None,
            charity_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """آمار فروش محصولات و کمک‌های حاصل از آن"""

        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=365)

        query = select(Product).where(
            Product.created_at.between(start_date, end_date)
        )

        if charity_id:
            query = query.where(Product.charity_id == charity_id)

        result = await self.db.execute(query)
        products = result.scalars().all()

        total_products = len(products)
        active_products = sum(1 for p in products if p.status == "active")

        # محاسبه کمک‌های حاصل از فروش
        total_charity_generated = 0
        product_stats = []

        for product in products:
            charity_per_unit = (
                    product.charity_fixed_amount +
                    (product.price * (product.charity_percentage / 100))
            )
            total_charity_generated += charity_per_unit * (product.stock_quantity or 0)

            product_stats.append({
                "product_id": product.id,
                "name": product.name,
                "price": product.price,
                "charity_percentage": product.charity_percentage,
                "charity_fixed": product.charity_fixed_amount,
                "charity_per_unit": charity_per_unit,
                "stock": product.stock_quantity,
                "status": product.status,
            })

        return {
            "summary": {
                "total_products": total_products,
                "active_products": active_products,
                "total_charity_generated": float(total_charity_generated),
                "average_charity_per_product": float(
                    total_charity_generated / total_products) if total_products > 0 else 0,
            },
            "products": product_stats[:20],  # ۲۰ محصول اول
        }

    # ---------- متدهای کمکی ----------
    async def _get_daily_donations(
            self,
            start_date: datetime,
            end_date: datetime,
            charity_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """آمار روزانه کمک‌ها"""

        daily = []
        current = start_date

        while current <= end_date:
            next_day = current + timedelta(days=1)

            query = select(
                func.count(Donation.id),
                func.coalesce(func.sum(Donation.amount), 0)
            ).where(
                and_(
                    Donation.status == "completed",
                    Donation.created_at >= current,
                    Donation.created_at < next_day
                )
            )

            if charity_id:
                query = query.where(Donation.charity_id == charity_id)

            result = await self.db.execute(query)
            count, amount = result.first()

            daily.append({
                "date": current.date(),
                "donations_count": count or 0,
                "total_amount": float(amount or 0),
            })

            current = next_day

        return daily

    async def _get_monthly_donations(
            self,
            start_date: datetime,
            end_date: datetime,
            charity_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """آمار ماهانه کمک‌ها"""

        monthly = []
        current = start_date.replace(day=1)

        while current <= end_date:
            next_month = (current.replace(day=28) + timedelta(days=4)).replace(day=1)

            query = select(
                func.count(Donation.id),
                func.coalesce(func.sum(Donation.amount), 0)
            ).where(
                and_(
                    Donation.status == "completed",
                    Donation.created_at >= current,
                    Donation.created_at < next_month
                )
            )

            if charity_id:
                query = query.where(Donation.charity_id == charity_id)

            result = await self.db.execute(query)
            count, amount = result.first()

            monthly.append({
                "month": current.strftime("%Y-%m"),
                "month_name": current.strftime("%B %Y"),
                "donations_count": count or 0,
                "total_amount": float(amount or 0),
            })

            current = next_month

        return monthly

    async def _get_payment_method_stats(
            self,
            start_date: datetime,
            end_date: datetime,
            charity_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """آمار روش‌های پرداخت"""

        methods = ["direct_transfer", "court", "digital_wallet", "bank_gateway", "product_sale"]
        result = {}

        for method in methods:
            query = select(
                func.count(Donation.id),
                func.coalesce(func.sum(Donation.amount), 0)
            ).where(
                and_(
                    Donation.payment_method == method,
                    Donation.status == "completed",
                    Donation.created_at.between(start_date, end_date)
                )
            )

            if charity_id:
                query = query.where(Donation.charity_id == charity_id)

            res = await self.db.execute(query)
            count, amount = res.first()

            result[method] = {
                "count": count or 0,
                "total_amount": float(amount or 0),
            }

        # محاسبه درصدها
        total_amount = sum(m["total_amount"] for m in result.values())
        if total_amount > 0:
            for method in result:
                result[method]["percentage"] = (result[method]["total_amount"] / total_amount) * 100

        return result