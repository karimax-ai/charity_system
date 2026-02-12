# app/services/dashboard_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, case
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from fastapi import HTTPException

from models.user import User
from models.charity import Charity
from models.need_ad import NeedAd
from models.donation import Donation
from models.product import Product
from models.shop import Shop
from models.need_verification import NeedVerification
from models.association_tables import charity_followers


class DashboardService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------- 1️⃣ داشبورد ادمین ----------
    async def get_admin_dashboard(self, user: User) -> Dict[str, Any]:
        """داشبورد کامل ادمین"""

        # آمار کلی
        total_users = await self.db.scalar(select(func.count(User.id)))
        total_charities = await self.db.scalar(select(func.count(Charity.id)).where(Charity.active == True))
        total_needs = await self.db.scalar(select(func.count(NeedAd.id)))
        total_donations = await self.db.scalar(
            select(func.coalesce(func.sum(Donation.amount), 0))
            .where(Donation.status == "completed")
        )

        # نیازهای در انتظار تأیید
        pending_needs = await self.db.scalar(
            select(func.count(NeedAd.id)).where(NeedAd.status == "pending")
        )

        # خیریه‌های در انتظار تأیید
        pending_charities = await self.db.scalar(
            select(func.count(Charity.id)).where(Charity.verified == False)
        )

        # کمک‌های اخیر
        recent_donations_query = (
            select(Donation)
            .where(Donation.status == "completed")
            .order_by(Donation.created_at.desc())
            .limit(10)
        )
        recent_donations = await self.db.execute(recent_donations_query)
        recent_donations = recent_donations.scalars().all()

        # نیازهای اخیر
        recent_needs_query = (
            select(NeedAd)
            .order_by(NeedAd.created_at.desc())
            .limit(10)
        )
        recent_needs = await self.db.execute(recent_needs_query)
        recent_needs = recent_needs.scalars().all()

        # کاربران جدید
        recent_users_query = (
            select(User)
            .order_by(User.created_at.desc())
            .limit(10)
        )
        recent_users = await self.db.execute(recent_users_query)
        recent_users = recent_users.scalars().all()

        # آمار فروش محصولات
        product_stats = await self._get_product_stats()

        # آمار ماهانه
        monthly_stats = await self._get_monthly_stats()

        return {
            "summary": {
                "total_users": total_users or 0,
                "total_charities": total_charities or 0,
                "total_needs": total_needs or 0,
                "total_donations": float(total_donations or 0),
                "pending_needs": pending_needs or 0,
                "pending_charities": pending_charities or 0,
            },
            "recent_donations": [
                {
                    "id": d.id,
                    "amount": d.amount,
                    "donor_name": d.donor.username if d.donor else "ناشناس",
                    "charity_name": d.charity.name if d.charity else None,
                    "created_at": d.created_at,
                }
                for d in recent_donations
            ],
            "recent_needs": [
                {
                    "id": n.id,
                    "title": n.title,
                    "charity_name": n.charity.name if n.charity else None,
                    "status": n.status,
                    "created_at": n.created_at,
                }
                for n in recent_needs
            ],
            "recent_users": [
                {
                    "id": u.id,
                    "username": u.username or u.email.split("@")[0],
                    "email": u.email,
                    "created_at": u.created_at,
                }
                for u in recent_users[:5]
            ],
            "product_stats": product_stats,
            "monthly_stats": monthly_stats,
        }

    # ---------- 2️⃣ داشبورد مدیر خیریه ----------
    async def get_charity_manager_dashboard(self, user: User) -> Dict[str, Any]:
        """داشبورد مدیر خیریه‌ها"""

        # خیریه‌های تحت مدیریت
        charities_query = select(Charity).where(
            or_(
                Charity.manager_id == user.id,
                Charity.verified_by == user.id
            )
        )
        charities = await self.db.execute(charities_query)
        charities = charities.scalars().all()

        charity_list = []
        total_donations = 0
        total_needs = 0

        for charity in charities:
            # آمار هر خیریه
            needs_count = await self.db.scalar(
                select(func.count(NeedAd.id)).where(NeedAd.charity_id == charity.id)
            )
            active_needs = await self.db.scalar(
                select(func.count(NeedAd.id)).where(
                    and_(
                        NeedAd.charity_id == charity.id,
                        NeedAd.status == "active"
                    )
                )
            )
            donations = await self.db.scalar(
                select(func.coalesce(func.sum(Donation.amount), 0))
                .where(
                    and_(
                        Donation.charity_id == charity.id,
                        Donation.status == "completed"
                    )
                )
            )

            total_donations += donations or 0
            total_needs += needs_count or 0

            charity_list.append({
                "charity_id": charity.id,
                "name": charity.name,
                "logo_url": charity.logo_url,
                "verified": charity.verified,
                "needs_count": needs_count or 0,
                "active_needs": active_needs or 0,
                "total_donations": float(donations or 0),
                "last_activity": charity.updated_at,
            })

        # درخواست‌های تأیید نیازها
        pending_verifications = await self.db.scalar(
            select(func.count(NeedVerification.id))
            .where(NeedVerification.status == "pending")
        )

        return {
            "charities": charity_list,
            "summary": {
                "total_charities": len(charities),
                "total_donations": float(total_donations),
                "total_needs": total_needs,
                "pending_verifications": pending_verifications or 0,
            },
        }

    # ---------- 3️⃣ داشبورد خیریه ----------
    async def get_charity_dashboard(self, charity_id: int, user: Optional[User] = None) -> Dict[str, Any]:
        """داشبورد یک خیریه خاص"""

        charity = await self.db.get(Charity, charity_id)
        if not charity:
            raise HTTPException(status_code=404, detail="Charity not found")

        # آمار نیازها
        needs_stats = await self._get_charity_needs_stats(charity_id)

        # آمار کمک‌ها
        donations_stats = await self._get_charity_donations_stats(charity_id)

        # آمار دنبال‌کنندگان
        followers_count = await self.db.scalar(
            select(func.count())
            .select_from(charity_followers)
            .where(charity_followers.c.charity_id == charity_id)
        )

        # محصولات مرتبط
        products_count = await self.db.scalar(
            select(func.count(Product.id))
            .where(Product.charity_id == charity_id)
        )

        # کمک‌های اخیر
        recent_donations_query = (
            select(Donation)
            .where(
                and_(
                    Donation.charity_id == charity_id,
                    Donation.status == "completed"
                )
            )
            .order_by(Donation.created_at.desc())
            .limit(10)
        )
        recent_donations = await self.db.execute(recent_donations_query)
        recent_donations = recent_donations.scalars().all()

        # نیازهای محبوب
        popular_needs_query = (
            select(NeedAd)
            .where(
                and_(
                    NeedAd.charity_id == charity_id,
                    NeedAd.status.in_(["active", "completed"])
                )
            )
            .order_by(NeedAd.collected_amount.desc())
            .limit(5)
        )
        popular_needs = await self.db.execute(popular_needs_query)
        popular_needs = popular_needs.scalars().all()

        return {
            "charity_id": charity.id,
            "name": charity.name,
            "logo_url": charity.logo_url,
            "verified": charity.verified,
            "needs_stats": needs_stats,
            "donations_stats": donations_stats,
            "followers_count": followers_count or 0,
            "products_count": products_count or 0,
            "recent_donations": [
                {
                    "id": d.id,
                    "amount": d.amount,
                    "donor_name": d.donor.username if d.donor and not d.anonymous else "ناشناس",
                    "created_at": d.created_at,
                }
                for d in recent_donations
            ],
            "popular_needs": [
                {
                    "id": n.id,
                    "title": n.title,
                    "target_amount": n.target_amount,
                    "collected_amount": n.collected_amount,
                    "progress": (n.collected_amount / n.target_amount * 100) if n.target_amount > 0 else 0,
                }
                for n in popular_needs
            ],
        }

    # ---------- 4️⃣ داشبورد نیازمند ----------
    async def get_needy_dashboard(self, user_id: int) -> Dict[str, Any]:
        """داشبورد کاربر نیازمند"""

        # نیازهای کاربر
        needs_query = (
            select(NeedAd)
            .where(NeedAd.needy_user_id == user_id)
            .order_by(NeedAd.created_at.desc())
        )
        needs = await self.db.execute(needs_query)
        needs = needs.scalars().all()

        total_needs = len(needs)
        verified_needs = sum(1 for n in needs if n.status == "approved" or n.status == "active")
        completed_needs = sum(1 for n in needs if n.status == "completed")
        pending_needs = sum(1 for n in needs if n.status == "pending")
        rejected_needs = sum(1 for n in needs if n.status == "rejected")

        total_requested = sum(n.target_amount for n in needs)
        total_received = sum(n.collected_amount or 0 for n in needs)

        return {
            "user_id": user_id,
            "summary": {
                "total_needs": total_needs,
                "verified_needs": verified_needs,
                "completed_needs": completed_needs,
                "pending_needs": pending_needs,
                "rejected_needs": rejected_needs,
                "total_requested": float(total_requested),
                "total_received": float(total_received),
            },
            "needs": [
                {
                    "id": n.id,
                    "title": n.title,
                    "target_amount": n.target_amount,
                    "collected_amount": n.collected_amount or 0,
                    "progress": (n.collected_amount / n.target_amount * 100) if n.target_amount > 0 else 0,
                    "status": n.status,
                    "charity_name": n.charity.name if n.charity else None,
                    "created_at": n.created_at,
                    "days_remaining": (
                        (n.deadline - datetime.utcnow()).days
                        if n.deadline and n.deadline > datetime.utcnow()
                        else 0
                    ) if n.deadline else None,
                }
                for n in needs
            ],
        }

    # ---------- 5️⃣ داشبورد خیر کمک‌کننده ----------
    async def get_donor_dashboard(self, user_id: int) -> Dict[str, Any]:
        """داشبورد خیر کمک‌کننده"""

        # کمک‌های کاربر
        donations_query = (
            select(Donation)
            .where(
                and_(
                    Donation.donor_id == user_id,
                    Donation.status == "completed"
                )
            )
            .order_by(Donation.created_at.desc())
        )
        donations = await self.db.execute(donations_query)
        donations = donations.scalars().all()

        total_donated = sum(d.amount for d in donations)
        donations_count = len(donations)
        average_donation = total_donated / donations_count if donations_count > 0 else 0

        # خیریه‌های محبوب
        charity_stats = {}
        for donation in donations:
            if donation.charity_id:
                if donation.charity_id not in charity_stats:
                    charity_stats[donation.charity_id] = {
                        "count": 0,
                        "total": 0,
                        "name": donation.charity.name if donation.charity else None,
                    }
                charity_stats[donation.charity_id]["count"] += 1
                charity_stats[donation.charity_id]["total"] += donation.amount

        favorite_charities = sorted(
            [
                {
                    "charity_id": cid,
                    "name": stats["name"],
                    "donations_count": stats["count"],
                    "total_donated": stats["total"],
                }
                for cid, stats in charity_stats.items()
            ],
            key=lambda x: x["total_donated"],
            reverse=True
        )[:5]

        # کمک‌های ماهانه
        monthly = {}
        for donation in donations:
            month_key = donation.created_at.strftime("%Y-%m")
            if month_key not in monthly:
                monthly[month_key] = 0
            monthly[month_key] += donation.amount

        return {
            "user_id": user_id,
            "summary": {
                "total_donated": float(total_donated),
                "donations_count": donations_count,
                "average_donation": float(average_donation),
                "largest_donation": float(max([d.amount for d in donations], default=0)),
                "first_donation": donations[-1].created_at if donations else None,
                "last_donation": donations[0].created_at if donations else None,
            },
            "donations": [
                {
                    "id": d.id,
                    "amount": d.amount,
                    "charity_name": d.charity.name if d.charity else None,
                    "need_title": d.need.title if d.need else None,
                    "created_at": d.created_at,
                    "receipt_number": d.receipt_number,
                }
                for d in donations[:20]  # آخرین ۲۰ کمک
            ],
            "favorite_charities": favorite_charities,
            "monthly_donations": [
                {"month": k, "amount": v}
                for k, v in sorted(monthly.items())
            ],
            "impact": {
                "charities_supported": len(charity_stats),
                "needs_supported": len(set(d.need_id for d in donations if d.need_id)),
            },
        }

    # ---------- 6️⃣ داشبورد فروشنده ----------
    async def get_vendor_dashboard(self, user_id: int) -> Dict[str, Any]:
        """داشبورد فروشنده"""

        # محصولات فروشنده
        products_query = (
            select(Product)
            .where(Product.vendor_id == user_id)
            .order_by(Product.created_at.desc())
        )
        products = await self.db.execute(products_query)
        products = products.scalars().all()

        total_products = len(products)
        active_products = sum(1 for p in products if p.status == "active")

        # محاسبه فروش و کمک‌ها
        total_sales = 0
        total_charity = 0
        product_stats = []

        for product in products:
            # در حالت واقعی از Order و OrderItem باید خوانده شود
            product_charity = (
                    product.charity_fixed_amount +
                    (product.price * (product.charity_percentage / 100))
            )
            total_charity += product_charity * (product.stock_quantity or 0)

            product_stats.append({
                "id": product.id,
                "name": product.name,
                "price": product.price,
                "status": product.status,
                "stock": product.stock_quantity,
                "charity_percentage": product.charity_percentage,
                "charity_fixed": product.charity_fixed_amount,
                "charity_per_unit": product_charity,
            })

        return {
            "vendor_id": user_id,
            "summary": {
                "total_products": total_products,
                "active_products": active_products,
                "total_sales": float(total_sales),
                "total_charity_generated": float(total_charity),
            },
            "products": product_stats,
            "recent_activities": [],  # از Order و OrderItem پر می‌شود
        }

    # ---------- 7️⃣ داشبورد مدیر فروشگاه ----------
    async def get_shop_manager_dashboard(self, user_id: int) -> Dict[str, Any]:
        """داشبورد مدیر فروشگاه"""

        # فروشگاه‌های تحت مدیریت
        shops_query = select(Shop).where(Shop.manager_id == user_id)
        shops = await self.db.execute(shops_query)
        shops = shops.scalars().all()

        shop_list = []
        total_vendors = 0
        total_products = 0
        total_sales = 0
        total_charity = 0

        for shop in shops:
            # آمار فروشگاه
            vendors_count = len(shop.vendors)
            products_count = await self.db.scalar(
                select(func.count(Product.id)).where(Product.shop_id == shop.id)
            )

            total_vendors += vendors_count
            total_products += products_count or 0

            shop_list.append({
                "shop_id": shop.id,
                "name": shop.name,
                "verified": shop.verified,
                "vendors_count": vendors_count,
                "products_count": products_count or 0,
            })

        return {
            "shops": shop_list,
            "summary": {
                "total_shops": len(shops),
                "total_vendors": total_vendors,
                "total_products": total_products,
                "total_sales": float(total_sales),
                "total_charity_generated": float(total_charity),
            },
        }

    # ---------- 8️⃣ داشبورد داوطلب ----------
    async def get_volunteer_dashboard(self, user_id: int) -> Dict[str, Any]:
        """داشبورد داوطلب"""

        # در حالت واقعی، از مدل VolunteerTask باید استفاده شود
        # اینجا یک نمونه ساده برمی‌گردانیم

        return {
            "user_id": user_id,
            "summary": {
                "total_tasks": 0,
                "completed_tasks": 0,
                "pending_tasks": 0,
                "impact_hours": 0,
            },
            "tasks": [],
            "charities_helped": 0,
            "needs_helped": 0,
        }

    # ---------- متدهای کمکی ----------
    async def _get_product_stats(self) -> Dict[str, Any]:
        """آمار محصولات"""
        total_products = await self.db.scalar(select(func.count(Product.id)))
        active_products = await self.db.scalar(
            select(func.count(Product.id)).where(Product.status == "active")
        )

        return {
            "total_products": total_products or 0,
            "active_products": active_products or 0,
            "by_status": {
                "draft": await self.db.scalar(select(func.count(Product.id)).where(Product.status == "draft")),
                "pending": await self.db.scalar(select(func.count(Product.id)).where(Product.status == "pending")),
                "active": active_products or 0,
                "sold_out": await self.db.scalar(select(func.count(Product.id)).where(Product.status == "sold_out")),
                "archived": await self.db.scalar(select(func.count(Product.id)).where(Product.status == "archived")),
            }
        }

    async def _get_monthly_stats(self) -> Dict[str, Any]:
        """آمار ماهانه"""
        current_month = datetime.utcnow().replace(day=1)
        last_month = (current_month - timedelta(days=1)).replace(day=1)

        # کمک‌های ماه جاری
        current_month_donations = await self.db.scalar(
            select(func.coalesce(func.sum(Donation.amount), 0))
            .where(
                and_(
                    Donation.created_at >= current_month,
                    Donation.status == "completed"
                )
            )
        )

        # کمک‌های ماه قبل
        last_month_donations = await self.db.scalar(
            select(func.coalesce(func.sum(Donation.amount), 0))
            .where(
                and_(
                    Donation.created_at >= last_month,
                    Donation.created_at < current_month,
                    Donation.status == "completed"
                )
            )
        )

        # کاربران جدید ماه جاری
        current_month_users = await self.db.scalar(
            select(func.count(User.id))
            .where(User.created_at >= current_month)
        )

        # نیازهای جدید ماه جاری
        current_month_needs = await self.db.scalar(
            select(func.count(NeedAd.id))
            .where(NeedAd.created_at >= current_month)
        )

        growth_rate = 0
        if last_month_donations > 0:
            growth_rate = ((current_month_donations - last_month_donations) / last_month_donations) * 100

        return {
            "current_month": {
                "donations": float(current_month_donations or 0),
                "new_users": current_month_users or 0,
                "new_needs": current_month_needs or 0,
            },
            "previous_month": {
                "donations": float(last_month_donations or 0),
            },
            "growth_rate": float(growth_rate),
        }

    async def _get_charity_needs_stats(self, charity_id: int) -> Dict[str, Any]:
        """آمار نیازهای یک خیریه"""
        total = await self.db.scalar(
            select(func.count(NeedAd.id)).where(NeedAd.charity_id == charity_id)
        )
        active = await self.db.scalar(
            select(func.count(NeedAd.id)).where(
                and_(
                    NeedAd.charity_id == charity_id,
                    NeedAd.status == "active"
                )
            )
        )
        completed = await self.db.scalar(
            select(func.count(NeedAd.id)).where(
                and_(
                    NeedAd.charity_id == charity_id,
                    NeedAd.status == "completed"
                )
            )
        )
        pending = await self.db.scalar(
            select(func.count(NeedAd.id)).where(
                and_(
                    NeedAd.charity_id == charity_id,
                    NeedAd.status == "pending"
                )
            )
        )

        return {
            "total": total or 0,
            "active": active or 0,
            "completed": completed or 0,
            "pending": pending or 0,
            "completion_rate": (completed / total * 100) if total and total > 0 else 0,
        }

    async def _get_charity_donations_stats(self, charity_id: int) -> Dict[str, Any]:
        """آمار کمک‌های یک خیریه"""
        total = await self.db.scalar(
            select(func.coalesce(func.sum(Donation.amount), 0))
            .where(
                and_(
                    Donation.charity_id == charity_id,
                    Donation.status == "completed"
                )
            )
        )

        count = await self.db.scalar(
            select(func.count(Donation.id))
            .where(
                and_(
                    Donation.charity_id == charity_id,
                    Donation.status == "completed"
                )
            )
        )

        donors = await self.db.scalar(
            select(func.count(func.distinct(Donation.donor_id)))
            .where(
                and_(
                    Donation.charity_id == charity_id,
                    Donation.status == "completed"
                )
            )
        )

        return {
            "total_amount": float(total or 0),
            "total_count": count or 0,
            "total_donors": donors or 0,
            "average_donation": float(total / count) if count and count > 0 else 0,
        }