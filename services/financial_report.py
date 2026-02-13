# app/services/financial_report.py - فایل کامل

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict

from models.order import Order
from models.donation import Donation
from models.charity import Charity
from models.need_ad import NeedAd


class FinancialReportService:
    """سرویس گزارش‌های مالی پیشرفته"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_income_statement(
            self,
            year: int,
            charity_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        صورت سود و زیان سالانه
        - درآمدها: کمک‌های مستقیم، فروش محصولات، مشارکت‌ها
        - هزینه‌ها: کمک به نیازمندان، هزینه‌های عملیاتی (در صورت وجود)
        """

        start_date = datetime(year, 1, 1)
        end_date = datetime(year, 12, 31)

        # ========== 1. درآمدها ==========

        # کمک‌های مستقیم
        donations_query = select(func.coalesce(func.sum(Donation.amount), 0)).where(
            and_(
                Donation.created_at.between(start_date, end_date),
                Donation.status == "completed"
            )
        )
        if charity_id:
            donations_query = donations_query.where(Donation.charity_id == charity_id)
        total_donations = await self.db.scalar(donations_query) or 0

        # فروش محصولات (سهم خیریه)
        orders_query = select(func.coalesce(func.sum(Order.charity_amount), 0)).where(
            and_(
                Order.created_at.between(start_date, end_date),
                Order.status.in_(["delivered", "confirmed"])
            )
        )
        if charity_id:
            orders_query = orders_query.where(Order.charity_id == charity_id)
        total_sales_charity = await self.db.scalar(orders_query) or 0

        # ========== 2. هزینه‌ها ==========
        # مبلغ پرداخت شده به نیازمندان
        needs_paid_query = select(func.coalesce(func.sum(NeedAd.collected_amount), 0)).where(
            and_(
                NeedAd.updated_at.between(start_date, end_date),
                NeedAd.status == "completed"
            )
        )
        if charity_id:
            needs_paid_query = needs_paid_query.where(NeedAd.charity_id == charity_id)
        total_needs_paid = await self.db.scalar(needs_paid_query) or 0

        # ========== 3. آمار ماهانه ==========
        monthly_stats = []
        for month in range(1, 13):
            month_start = datetime(year, month, 1)
            if month == 12:
                month_end = datetime(year, 12, 31)
            else:
                month_end = datetime(year, month + 1, 1) - timedelta(days=1)

            # درآمد ماه
            month_donations = await self.db.scalar(
                select(func.coalesce(func.sum(Donation.amount), 0)).where(
                    and_(
                        Donation.created_at.between(month_start, month_end),
                        Donation.status == "completed"
                    )
                )
            ) or 0

            month_sales = await self.db.scalar(
                select(func.coalesce(func.sum(Order.charity_amount), 0)).where(
                    and_(
                        Order.created_at.between(month_start, month_end),
                        Order.status.in_(["delivered", "confirmed"])
                    )
                )
            ) or 0

            # هزینه ماه
            month_expenses = await self.db.scalar(
                select(func.coalesce(func.sum(NeedAd.collected_amount), 0)).where(
                    and_(
                        NeedAd.updated_at.between(month_start, month_end),
                        NeedAd.status == "completed"
                    )
                )
            ) or 0

            monthly_stats.append({
                "month": month,
                "donations": float(month_donations),
                "sales_charity": float(month_sales),
                "total_income": float(month_donations + month_sales),
                "expenses": float(month_expenses),
                "net_profit": float(month_donations + month_sales - month_expenses)
            })

        # ========== 4. محاسبه شاخص‌ها ==========
        total_income = float(total_donations + total_sales_charity)
        total_expenses = float(total_needs_paid)
        net_profit = total_income - total_expenses

        # درصد هزینه‌ها از درآمد
        expense_ratio = (total_expenses / total_income * 100) if total_income > 0 else 0

        return {
            "year": year,
            "charity_id": charity_id,
            "income": {
                "direct_donations": float(total_donations),
                "sales_contributions": float(total_sales_charity),
                "total_income": total_income
            },
            "expenses": {
                "needs_payments": float(total_needs_paid),
                "total_expenses": total_expenses
            },
            "net_profit": net_profit,
            "profit_margin": round((net_profit / total_income * 100) if total_income > 0 else 0, 1),
            "expense_ratio": round(expense_ratio, 1),
            "monthly": monthly_stats,
            "generated_at": datetime.utcnow().isoformat()
        }

    async def generate_charity_financials(
            self,
            charity_id: int,
            year: int
    ) -> Dict[str, Any]:
        """گزارش مالی یک خیریه خاص"""

        # دریافت اطلاعات خیریه
        charity = await self.db.get(Charity, charity_id)
        if not charity:
            raise HTTPException(status_code=404, detail="خیریه یافت نشد")

        # صورت سود و زیان
        income_statement = await self.generate_income_statement(year, charity_id)

        # آمار نیازها
        needs_stats = await self._get_charity_needs_stats(charity_id, year)

        # آمار کمک‌کنندگان
        donors_stats = await self._get_charity_donors_stats(charity_id, year)

        return {
            "charity_id": charity_id,
            "charity_name": charity.name,
            "year": year,
            "income_statement": income_statement,
            "needs_statistics": needs_stats,
            "donors_statistics": donors_stats,
            "generated_at": datetime.utcnow().isoformat()
        }

    async def generate_public_financial_report(
            self,
            period: str = "monthly"  # monthly, quarterly, yearly
    ) -> Dict[str, Any]:
        """
        گزارش مالی عمومی - بدون اطلاعات محرمانه
        قابل انتشار برای همه کاربران
        """

        end_date = datetime.utcnow()

        if period == "monthly":
            start_date = end_date - timedelta(days=30)
        elif period == "quarterly":
            start_date = end_date - timedelta(days=90)
        elif period == "yearly":
            start_date = end_date - timedelta(days=365)
        else:
            start_date = end_date - timedelta(days=30)

        # ========== آمار کلی ==========

        # کل کمک‌ها
        total_donations = await self.db.scalar(
            select(func.coalesce(func.sum(Donation.amount), 0)).where(
                and_(
                    Donation.created_at.between(start_date, end_date),
                    Donation.status == "completed"
                )
            )
        ) or 0

        # کل کمک از فروش محصولات
        total_sales_contribution = await self.db.scalar(
            select(func.coalesce(func.sum(Order.charity_amount), 0)).where(
                and_(
                    Order.created_at.between(start_date, end_date),
                    Order.status.in_(["delivered", "confirmed"])
                )
            )
        ) or 0

        # تعداد نیازهای تأمین شده
        completed_needs = await self.db.scalar(
            select(func.count(NeedAd.id)).where(
                and_(
                    NeedAd.updated_at.between(start_date, end_date),
                    NeedAd.status == "completed"
                )
            )
        ) or 0

        # تعداد خیریه‌های فعال
        active_charities = await self.db.scalar(
            select(func.count(Charity.id)).where(Charity.is_active == True)
        ) or 0

        # ========== روند ماهانه ==========
        monthly_trend = []
        for i in range(6):  # 6 ماه اخیر
            month_end = end_date - timedelta(days=30 * i)
            month_start = month_end - timedelta(days=30)

            month_donations = await self.db.scalar(
                select(func.coalesce(func.sum(Donation.amount), 0)).where(
                    and_(
                        Donation.created_at.between(month_start, month_end),
                        Donation.status == "completed"
                    )
                )
            ) or 0

            month_sales = await self.db.scalar(
                select(func.coalesce(func.sum(Order.charity_amount), 0)).where(
                    and_(
                        Order.created_at.between(month_start, month_end),
                        Order.status.in_(["delivered", "confirmed"])
                    )
                )
            ) or 0

            monthly_trend.append({
                "period": month_start.strftime("%Y-%m"),
                "donations": float(month_donations),
                "sales_contribution": float(month_sales),
                "total": float(month_donations + month_sales)
            })

        monthly_trend.reverse()  # از قدیم به جدید

        # ========== خیریه‌های برتر ==========
        top_charities_query = (
            select(
                Charity.id,
                Charity.name,
                func.coalesce(func.sum(Donation.amount), 0).label("donations"),
                func.coalesce(func.sum(Order.charity_amount), 0).label("sales")
            )
            .join(Donation, Donation.charity_id == Charity.id, isouter=True)
            .join(Order, Order.charity_id == Charity.id, isouter=True)
            .where(
                and_(
                    Donation.created_at.between(start_date, end_date),
                    Donation.status == "completed"
                )
            )
            .group_by(Charity.id, Charity.name)
            .order_by(desc("donations"))
            .limit(5)
        )

        top_charities_result = await self.db.execute(top_charities_query)
        top_charities = []
        for row in top_charities_result:
            top_charities.append({
                "id": row.id,
                "name": row.name,
                "total_received": float(row.donations + row.sales)
            })

        return {
            "period": period,
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "summary": {
                "total_donations": float(total_donations),
                "total_sales_contribution": float(total_sales_contribution),
                "total_funds": float(total_donations + total_sales_contribution),
                "completed_needs": completed_needs,
                "active_charities": active_charities
            },
            "monthly_trend": monthly_trend,
            "top_charities": top_charities,
            "generated_at": datetime.utcnow().isoformat()
        }

    async def _get_charity_needs_stats(self, charity_id: int, year: int) -> Dict[str, Any]:
        """آمار نیازهای یک خیریه"""

        start_date = datetime(year, 1, 1)
        end_date = datetime(year, 12, 31)

        query = select(NeedAd).where(
            and_(
                NeedAd.charity_id == charity_id,
                NeedAd.created_at.between(start_date, end_date)
            )
        )
        result = await self.db.execute(query)
        needs = result.scalars().all()

        total_needs = len(needs)
        completed_needs = len([n for n in needs if n.status == "completed"])
        active_needs = len([n for n in needs if n.status in ["pending", "active"]])

        total_target = sum((n.target_amount or 0) for n in needs)
        total_collected = sum((n.collected_amount or 0) for n in needs)

        return {
            "total_needs": total_needs,
            "completed_needs": completed_needs,
            "active_needs": active_needs,
            "completion_rate": round((completed_needs / total_needs * 100) if total_needs > 0 else 0, 1),
            "total_target_amount": float(total_target),
            "total_collected_amount": float(total_collected),
            "funding_rate": round((total_collected / total_target * 100) if total_target > 0 else 0, 1)
        }

    async def _get_charity_donors_stats(self, charity_id: int, year: int) -> Dict[str, Any]:
        """آمار کمک‌کنندگان یک خیریه"""

        start_date = datetime(year, 1, 1)
        end_date = datetime(year, 12, 31)

        # تعداد کمک‌کنندگان منحصر به فرد
        unique_donors_query = select(func.count(func.distinct(Donation.donor_id))).where(
            and_(
                Donation.charity_id == charity_id,
                Donation.created_at.between(start_date, end_date),
                Donation.status == "completed"
            )
        )
        unique_donors = await self.db.scalar(unique_donors_query) or 0

        # میانگین کمک
        avg_donation_query = select(func.coalesce(func.avg(Donation.amount), 0)).where(
            and_(
                Donation.charity_id == charity_id,
                Donation.created_at.between(start_date, end_date),
                Donation.status == "completed"
            )
        )
        avg_donation = await self.db.scalar(avg_donation_query) or 0

        return {
            "unique_donors": unique_donors,
            "average_donation": float(avg_donation),
            "year": year
        }