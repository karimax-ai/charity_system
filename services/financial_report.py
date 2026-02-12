# app/services/financial_report.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from models.order import Order
from models.donation import Donation
from models.charity import Charity


class FinancialReportService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_income_statement(
            self,
            year: int,
            charity_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """صورت سود و زیان سالانه"""

        start_date = datetime(year, 1, 1)
        end_date = datetime(year, 12, 31, 23, 59, 59)

        monthly_data = []

        for month in range(1, 13):
            month_start = datetime(year, month, 1)
            month_end = datetime(year, month, 1)
            if month == 12:
                month_end = datetime(year, 12, 31, 23, 59, 59)
            else:
                month_end = datetime(year, month + 1, 1) - timedelta(seconds=1)

            revenue = await self._get_monthly_revenue(month_start, month_end, charity_id)
            donations = await self._get_monthly_donations(month_start, month_end, charity_id)

            monthly_data.append({
                "month": month,
                "month_name": self._get_month_name(month),
                "revenue": float(revenue),
                "donations": float(donations),
                "total_income": float(revenue + donations)
            })

        total_revenue = sum(m["revenue"] for m in monthly_data)
        total_donations = sum(m["donations"] for m in monthly_data)

        return {
            "year": year,
            "charity_id": charity_id,
            "monthly": monthly_data,
            "summary": {
                "total_revenue": total_revenue,
                "total_donations": total_donations,
                "total_income": total_revenue + total_donations
            }
        }

    async def generate_charity_financials(
            self,
            charity_id: int,
            year: int
    ) -> Dict[str, Any]:
        """گزارش مالی خیریه"""

        charity = await self.db.get(Charity, charity_id)
        if not charity:
            return {"error": "Charity not found"}

        start_date = datetime(year, 1, 1)
        end_date = datetime(year, 12, 31, 23, 59, 59)

        donations = await self.db.execute(
            select(
                func.count(Donation.id).label("count"),
                func.sum(Donation.amount).label("total")
            ).where(
                and_(
                    Donation.charity_id == charity_id,
                    Donation.status == "completed",
                    Donation.created_at.between(start_date, end_date)
                )
            )
        )
        donation_stats = donations.first()

        orders = await self.db.execute(
            select(
                func.count(Order.id).label("count"),
                func.sum(Order.charity_amount).label("total")
            ).where(
                and_(
                    Order.charity_id == charity_id,
                    Order.status.in_(["delivered", "confirmed"]),
                    Order.created_at.between(start_date, end_date)
                )
            )
        )
        order_stats = orders.first()

        monthly = []
        for month in range(1, 13):
            month_start = datetime(year, month, 1)
            month_end = datetime(year, month, 1)
            if month == 12:
                month_end = datetime(year, 12, 31, 23, 59, 59)
            else:
                month_end = datetime(year, month + 1, 1) - timedelta(seconds=1)

            month_donations = await self.db.scalar(
                select(func.coalesce(func.sum(Donation.amount), 0))
                .where(
                    and_(
                        Donation.charity_id == charity_id,
                        Donation.status == "completed",
                        Donation.created_at.between(month_start, month_end)
                    )
                )
            )

            month_orders = await self.db.scalar(
                select(func.coalesce(func.sum(Order.charity_amount), 0))
                .where(
                    and_(
                        Order.charity_id == charity_id,
                        Order.status.in_(["delivered", "confirmed"]),
                        Order.created_at.between(month_start, month_end)
                    )
                )
            )

            monthly.append({
                "month": month,
                "month_name": self._get_month_name(month),
                "donations": float(month_donations or 0),
                "product_sales": float(month_orders or 0),
                "total": float((month_donations or 0) + (month_orders or 0))
            })

        return {
            "charity_id": charity_id,
            "charity_name": charity.name,
            "year": year,
            "summary": {
                "total_donations_count": donation_stats.count or 0,
                "total_donations_amount": float(donation_stats.total or 0),
                "total_orders_count": order_stats.count or 0,
                "total_product_sales": float(order_stats.total or 0),
                "total_received": float((donation_stats.total or 0) + (order_stats.total or 0))
            },
            "monthly_breakdown": monthly
        }

    def _get_month_name(self, month: int) -> str:
        months = {
            1: "فروردین", 2: "اردیبهشت", 3: "خرداد", 4: "تیر",
            5: "مرداد", 6: "شهریور", 7: "مهر", 8: "آبان",
            9: "آذر", 10: "دی", 11: "بهمن", 12: "اسفند"
        }
        return months.get(month, f"ماه {month}")

    async def _get_monthly_revenue(self, start: datetime, end: datetime, charity_id: Optional[int]) -> float:
        query = select(func.coalesce(func.sum(Order.grand_total), 0)).where(
            and_(
                Order.created_at.between(start, end),
                Order.status.in_(["delivered", "confirmed"])
            )
        )
        if charity_id:
            query = query.where(Order.charity_id == charity_id)
        result = await self.db.scalar(query)
        return float(result or 0)

    async def _get_monthly_donations(self, start: datetime, end: datetime, charity_id: Optional[int]) -> float:
        query = select(func.coalesce(func.sum(Donation.amount), 0)).where(
            and_(
                Donation.created_at.between(start, end),
                Donation.status == "completed"
            )
        )
        if charity_id:
            query = query.where(Donation.charity_id == charity_id)
        result = await self.db.scalar(query)
        return float(result or 0)