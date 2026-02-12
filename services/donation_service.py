# app/services/donation_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, asc, update, case
from fastapi import HTTPException, status
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
import math
import uuid
import hashlib

from models.donation import Donation
from models.user import User
from models.need_ad import NeedAd
from models.charity import Charity
from models.product import Product
from models.order import Order
from schemas.donation import (
    DonationCreate, DonationUpdate, DonationStatusUpdate,
    DonationFilter, PaymentInitiate, PaymentVerify,
    DirectTransferCreate, CourtPaymentCreate,
    RecurringDonationCreate, RecurringDonationUpdate,
    CartCreate, CartItem
)


class DonationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_donation(self, donation_data: DonationCreate, donor: User) -> Donation:
        """ایجاد کمک جدید"""
        # اعتبارسنجی داده‌ها
        await self._validate_donation_data(donation_data, donor)

        # محاسبه مبلغ نهایی
        final_amount = donation_data.amount

        # اگر کمک به یک نیاز خاص است، بررسی موجودیت
        need = None
        if donation_data.need_id:
            need = await self.db.get(NeedAd, donation_data.need_id)
            if not need:
                raise HTTPException(status_code=404, detail="Need not found")

            # بررسی وضعیت نیاز
            if need.status not in ["active", "pending", "approved"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot donate to need with status: {need.status}"
                )

            # بررسی اینکه مبلغ از مبلغ باقی‌مانده بیشتر نباشد
            remaining = need.target_amount - need.collected_amount
            if donation_data.amount > remaining:
                raise HTTPException(
                    status_code=400,
                    detail=f"Donation amount ({donation_data.amount}) exceeds remaining amount ({remaining})"
                )

        # اگر کمک به یک خیریه است
        charity = None
        if donation_data.charity_id:
            charity = await self.db.get(Charity, donation_data.charity_id)
            if not charity or not charity.active or not charity.verified:
                raise HTTPException(status_code=404, detail="Charity not found or not active")

        # اگر کمک از طریق محصول است
        product = None
        if donation_data.product_id:
            product = await self.db.get(Product, donation_data.product_id)
            if not product or product.status != "active":
                raise HTTPException(status_code=404, detail="Product not found or not active")

            # محاسبه مبلغ کمک از محصول
            product_donation = (
                    product.charity_fixed_amount +
                    (product.price * (product.charity_percentage / 100))
            )
            final_amount = product_donation

        # ایجاد کمک
        donation = Donation(
            amount=final_amount,
            currency=donation_data.currency,
            payment_method=donation_data.payment_method,
            status="pending",
            donor_id=donor.id,
            need_id=donation_data.need_id,
            charity_id=donation_data.charity_id or (need.charity_id if need else None),
            product_id=donation_data.product_id,
            dedication_name=donation_data.dedication_name,
            dedication_message=donation_data.dedication_message,
            anonymous=donation_data.anonymous,
            donor_ip="0.0.0.0",  # از request می‌آید
            donor_user_agent=""  # از request می‌آید
        )

        self.db.add(donation)
        await self.db.commit()
        await self.db.refresh(donation)

        # ثبت لاگ
        await self._log_donation_action(donation.id, "created", donor.id, {
            "amount": final_amount,
            "payment_method": donation_data.payment_method
        })

        return donation

    async def update_donation(self, donation_id: int, update_data: DonationUpdate, user: User) -> Donation:
        """ویرایش اطلاعات کمک"""
        donation = await self._get_donation_with_permission(donation_id, user)

        # فقط کمک‌های در وضعیت pending قابل ویرایش هستند
        if donation.status != "pending" and donation.payment_status != "pending":
            raise HTTPException(
                status_code=400,
                detail="Cannot edit donation that is not in pending status"
            )

        # به‌روزرسانی فیلدها
        for key, value in update_data.dict(exclude_unset=True).items():
            if value is not None:
                setattr(donation, key, value)

        self.db.add(donation)
        await self.db.commit()
        await self.db.refresh(donation)

        # ثبت لاگ
        await self._log_donation_action(donation.id, "updated", user.id, update_data.dict())

        return donation

    async def update_donation_status(
            self, donation_id: int, status_data: DonationStatusUpdate, user: User
    ) -> Donation:
        """تغییر وضعیت کمک (ادمین/مدیر)"""
        donation = await self._get_donation_with_permission(donation_id, user, require_admin=True)

        # بررسی انتقال وضعیت مجاز
        allowed_transitions = {
            "pending": ["processing", "cancelled"],
            "processing": ["completed", "failed"],
            "completed": ["refunded"],
            "failed": ["pending", "cancelled"],
        }

        if status_data.status not in allowed_transitions.get(donation.status, []):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot change status from {donation.status} to {status_data.status}"
            )

        old_status = donation.status
        donation.status = status_data.status

        # اگر تکمیل شد
        if status_data.status == "completed":
            donation.payment_status = "paid"
            donation.completed_at = datetime.utcnow()

            # به‌روزرسانی مبلغ جمع‌آوری شده نیاز
            if donation.need:
                donation.need.collected_amount = (donation.need.collected_amount or 0) + donation.amount
                self.db.add(donation.need)

                # بررسی تکمیل شدن نیاز
                if donation.need.collected_amount >= donation.need.target_amount:
                    donation.need.status = "completed"

            # تولید کد رهگیری
            donation.tracking_code = self._generate_tracking_code()

        # اگر بازپرداخت شد
        elif status_data.status == "refunded":
            donation.payment_status = "refunded"

            # کاهش مبلغ جمع‌آوری شده نیاز
            if donation.need:
                donation.need.collected_amount = max(0, (donation.need.collected_amount or 0) - donation.amount)
                self.db.add(donation.need)

        self.db.add(donation)
        await self.db.commit()
        await self.db.refresh(donation)

        # ثبت لاگ
        await self._log_donation_action(
            donation.id, "status_changed", user.id,
            {"from": old_status, "to": status_data.status, "notes": status_data.notes}
        )

        return donation

    async def initiate_payment(self, payment_data: PaymentInitiate, user: User) -> Dict[str, Any]:
        """آغاز پرداخت از طریق درگاه"""
        donation = await self._get_donation_with_permission(payment_data.donation_id, user)

        # بررسی اینکه کمک در وضعیت pending باشد
        if donation.status != "pending":
            raise HTTPException(
                status_code=400,
                detail=f"Cannot initiate payment for donation with status: {donation.status}"
            )

        # بررسی روش پرداخت
        if donation.payment_method != "bank_gateway":
            raise HTTPException(
                status_code=400,
                detail=f"Payment method must be bank_gateway, not {donation.payment_method}"
            )

        # ایجاد درخواست پرداخت
        authority = self._generate_authority_code()

        # ذخیره اطلاعات درگاه
        donation.gateway_type = payment_data.gateway_type
        donation.transaction_id = authority
        donation.payment_details = {
            "gateway_type": payment_data.gateway_type,
            "authority": authority,
            "return_url": payment_data.return_url,
            "initiated_at": datetime.utcnow().isoformat()
        }

        self.db.add(donation)
        await self.db.commit()

        # ثبت لاگ
        await self._log_donation_action(
            donation.id, "payment_initiated", user.id,
            {"gateway": payment_data.gateway_type, "authority": authority}
        )

        # در اینجا باید به درگاه پرداخت واقعی متصل شویم
        # برای نمونه، URL درگاه را برمی‌گردانیم
        payment_url = await self._get_gateway_payment_url(
            payment_data.gateway_type, authority, donation.amount
        )

        return {
            "authority": authority,
            "payment_url": payment_url,
            "donation_id": donation.id,
            "amount": donation.amount,
            "currency": donation.currency
        }

    async def verify_payment(self, verify_data: PaymentVerify, user: Optional[User] = None) -> Donation:
        """تأیید پرداخت درگاه"""
        donation = await self._get_donation(verify_data.donation_id)

        # بررسی authority
        if donation.transaction_id != verify_data.authority:
            raise HTTPException(status_code=400, detail="Invalid authority code")

        # بررسی وضعیت
        if donation.status != "pending" and donation.payment_status != "pending":
            raise HTTPException(
                status_code=400,
                detail=f"Cannot verify payment for donation with status: {donation.status}"
            )

        # تأیید با درگاه پرداخت
        verification_result = await self._verify_with_gateway(
            donation.gateway_type, verify_data.authority, verify_data.status
        )

        if verification_result["success"]:
            donation.status = "completed"
            donation.payment_status = "paid"
            donation.completed_at = datetime.utcnow()
            donation.tracking_code = self._generate_tracking_code()
            donation.receipt_number = self._generate_receipt_number()

            # به‌روزرسانی مبلغ جمع‌آوری شده نیاز
            if donation.need:
                donation.need.collected_amount = (donation.need.collected_amount or 0) + donation.amount
                self.db.add(donation.need)

                # بررسی تکمیل شدن نیاز
                if donation.need.collected_amount >= donation.need.target_amount:
                    donation.need.status = "completed"

            # ثبت جزئیات پرداخت
            donation.payment_details.update({
                "verified_at": datetime.utcnow().isoformat(),
                "gateway_status": verify_data.status,
                "gateway_ref_id": verification_result.get("ref_id"),
                "gateway_card_hash": verification_result.get("card_hash")
            })
        else:
            donation.status = "failed"
            donation.payment_status = "failed"
            donation.payment_details.update({
                "verification_failed_at": datetime.utcnow().isoformat(),
                "failure_reason": verification_result.get("message")
            })

        self.db.add(donation)
        await self.db.commit()
        await self.db.refresh(donation)

        # ثبت لاگ
        await self._log_donation_action(
            donation.id, "payment_verified", user.id if user else None,
            {
                "success": verification_result["success"],
                "gateway_status": verify_data.status,
                "message": verification_result.get("message")
            }
        )

        # اگر پرداخت موفق بود، رسید مالیاتی ایجاد کن
        if verification_result["success"]:
            await self._generate_tax_receipt(donation)

        return donation

    async def record_direct_transfer(
            self, transfer_data: DirectTransferCreate, user: User
    ) -> Donation:
        """ثبت پرداخت مستقیم (واریز بانکی)"""
        donation = await self._get_donation_with_permission(transfer_data.donation_id, user)

        # بررسی روش پرداخت
        if donation.payment_method != "direct_transfer":
            raise HTTPException(
                status_code=400,
                detail=f"Payment method must be direct_transfer, not {donation.payment_method}"
            )

        # ذخیره اطلاعات واریز
        donation.bank_transfer_details = {
            "bank_name": transfer_data.bank_name,
            "account_number": transfer_data.account_number,
            "reference_number": transfer_data.reference_number,
            "transfer_date": transfer_data.transfer_date.isoformat(),
            "receipt_image_url": transfer_data.receipt_image_url,
            "recorded_by": user.id,
            "recorded_at": datetime.utcnow().isoformat()
        }

        donation.status = "processing"

        self.db.add(donation)
        await self.db.commit()

        # ثبت لاگ
        await self._log_donation_action(
            donation.id, "direct_transfer_recorded", user.id,
            transfer_data.dict()
        )

        return donation

    async def record_court_payment(
            self, court_data: CourtPaymentCreate, user: User
    ) -> Donation:
        """ثبت پرداخت از طریق دادگاه"""
        donation = await self._get_donation_with_permission(court_data.donation_id, user)

        # بررسی روش پرداخت
        if donation.payment_method != "court":
            raise HTTPException(
                status_code=400,
                detail=f"Payment method must be court, not {donation.payment_method}"
            )

        # ذخیره اطلاعات دادگاه
        donation.court_payment_details = {
            "court_name": court_data.court_name,
            "case_number": court_data.case_number,
            "payment_date": court_data.payment_date.isoformat(),
            "receipt_number": court_data.receipt_number,
            "documents": court_data.documents,
            "recorded_by": user.id,
            "recorded_at": datetime.utcnow().isoformat()
        }

        donation.status = "processing"
        donation.receipt_number = court_data.receipt_number

        self.db.add(donation)
        await self.db.commit()

        # ثبت لاگ
        await self._log_donation_action(
            donation.id, "court_payment_recorded", user.id,
            court_data.dict()
        )

        return donation

    async def get_donation(self, donation_id: int, user: Optional[User] = None) -> Dict[str, Any]:
        """دریافت اطلاعات کمک"""
        donation = await self._get_donation(donation_id)

        # بررسی دسترسی
        if not self._can_view_donation(donation, user):
            raise HTTPException(status_code=403, detail="Not authorized")

        # آماده‌سازی اطلاعات
        data = {
            "id": donation.id,
            "uuid": donation.uuid,
            "amount": donation.amount,
            "currency": donation.currency,
            "payment_method": donation.payment_method,
            "status": donation.status,
            "payment_status": donation.payment_status,

            # اطلاعات مرتبط
            "donor_id": donation.donor_id,
            "need_id": donation.need_id,
            "charity_id": donation.charity_id,
            "product_id": donation.product_id,

            # اطلاعات پرداخت
            "transaction_id": donation.transaction_id,
            "tracking_code": donation.tracking_code,
            "receipt_number": donation.receipt_number,
            "gateway_type": donation.gateway_type,

            # اطلاعات هدیه
            "dedication_name": donation.dedication_name,
            "dedication_message": donation.dedication_message,
            "anonymous": donation.anonymous,

            # زمان‌ها
            "created_at": donation.created_at,
            "completed_at": donation.completed_at,
            "updated_at": donation.updated_at
        }

        # اضافه کردن نام‌ها اگر کاربر مجاز است
        if self._can_view_donation_details(donation, user):
            if donation.donor and not donation.anonymous:
                data["donor_name"] = donation.donor.username or donation.donor.email
                if self._can_view_sensitive_details(user):
                    data["donor_email"] = donation.donor.email
                    data["donor_phone"] = donation.donor.phone

            if donation.need:
                data["need_title"] = donation.need.title

            if donation.charity:
                data["charity_name"] = donation.charity.name

            if donation.product:
                data["product_name"] = donation.product.name

            # جزئیات پرداخت
            data["payment_details"] = donation.payment_details or {}
            data["bank_transfer_details"] = donation.bank_transfer_details
            data["court_payment_details"] = donation.court_payment_details

            # اطلاعات اضافی
            data["donor_ip"] = donation.donor_ip
            data["donor_user_agent"] = donation.donor_user_agent

            # تاریخچه وضعیت
            data["status_history"] = await self._get_donation_status_history(donation_id)

        return data

    async def list_donations(
            self, filters: DonationFilter, user: Optional[User] = None, page: int = 1, limit: int = 20
    ) -> Dict[str, Any]:
        """لیست کمک‌ها با فیلتر و صفحه‌بندی"""
        # شروع کوئری
        query = select(Donation)

        # اعمال فیلترها
        conditions = []

        if filters.donor_id:
            conditions.append(Donation.donor_id == filters.donor_id)

        if filters.need_id:
            conditions.append(Donation.need_id == filters.need_id)

        if filters.charity_id:
            conditions.append(Donation.charity_id == filters.charity_id)

        if filters.product_id:
            conditions.append(Donation.product_id == filters.product_id)

        if filters.status:
            conditions.append(Donation.status == filters.status)

        if filters.payment_method:
            conditions.append(Donation.payment_method == filters.payment_method)

        if filters.payment_status:
            conditions.append(Donation.payment_status == filters.payment_status)

        if filters.min_amount:
            conditions.append(Donation.amount >= filters.min_amount)

        if filters.max_amount:
            conditions.append(Donation.amount <= filters.max_amount)

        if filters.start_date:
            conditions.append(Donation.created_at >= filters.start_date)

        if filters.end_date:
            conditions.append(Donation.created_at <= filters.end_date)

        if filters.search_text:
            # جستجو در کد رهگیری یا شماره رسید
            conditions.append(
                or_(
                    Donation.tracking_code.ilike(f"%{filters.search_text}%"),
                    Donation.receipt_number.ilike(f"%{filters.search_text}%"),
                    Donation.transaction_id.ilike(f"%{filters.search_text}%")
                )
            )

        # اگر کاربر مشخص شده، بررسی دسترسی
        if user:
            user_roles = [r.key for r in user.roles]
            if "ADMIN" not in user_roles and "CHARITY_MANAGER" not in user_roles:
                # کاربر عادی فقط کمک‌های خودش را می‌بیند
                conditions.append(Donation.donor_id == user.id)

        if conditions:
            query = query.where(and_(*conditions))

        # مرتب‌سازی
        sort_column = getattr(Donation, filters.sort_by, Donation.created_at)
        if filters.sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # شمارش کل
        total_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(total_query)

        # صفحه‌بندی
        offset = (page - 1) * limit
        query = query.offset(offset).limit(limit)

        # اجرای کوئری
        result = await self.db.execute(query)
        donations = result.scalars().all()

        # تبدیل به فرمت خروجی
        donation_list = []
        for donation in donations:
            donation_data = await self.get_donation(donation.id, user)
            donation_list.append(donation_data)

        return {
            "items": donation_list,
            "total": total or 0,
            "page": page,
            "limit": limit,
            "total_pages": math.ceil(total / limit) if total and total > 0 else 0
        }

    async def get_donation_stats(
            self, filters: DonationFilter, user: Optional[User] = None
    ) -> Dict[str, Any]:
        """آمار کمک‌ها"""
        # استفاده از متد list_donations برای فیلتر کردن
        all_donations = await self.list_donations(filters, user, page=1, limit=1000000)

        donations = all_donations["items"]

        if not donations:
            return {
                "total_donations": 0,
                "total_amount": 0,
                "average_donation": 0,
                "by_payment_method": {},
                "by_status": {},
                "by_charity": {},
                "by_need": {}
            }

        # محاسبات
        total_amount = sum(d["amount"] for d in donations)
        total_donations = len(donations)
        average_donation = total_amount / total_donations if total_donations > 0 else 0

        # گروه‌بندی بر اساس روش پرداخت
        by_payment_method = {}
        for donation in donations:
            method = donation["payment_method"]
            if method not in by_payment_method:
                by_payment_method[method] = {
                    "count": 0,
                    "total_amount": 0,
                    "average_amount": 0
                }
            by_payment_method[method]["count"] += 1
            by_payment_method[method]["total_amount"] += donation["amount"]

        # محاسبه میانگین
        for method in by_payment_method:
            by_payment_method[method]["average_amount"] = (
                    by_payment_method[method]["total_amount"] / by_payment_method[method]["count"]
            )

        # گروه‌بندی بر اساس وضعیت
        by_status = {}
        for donation in donations:
            status = donation["status"]
            if status not in by_status:
                by_status[status] = 0
            by_status[status] += 1

        # گروه‌بندی بر اساس خیریه
        by_charity = {}
        for donation in donations:
            charity_id = donation.get("charity_id")
            charity_name = donation.get("charity_name", "Unknown")

            if charity_id:
                key = f"{charity_id}:{charity_name}"
                if key not in by_charity:
                    by_charity[key] = {
                        "charity_id": charity_id,
                        "charity_name": charity_name,
                        "count": 0,
                        "total_amount": 0
                    }
                by_charity[key]["count"] += 1
                by_charity[key]["total_amount"] += donation["amount"]

        # گروه‌بندی بر اساس نیاز
        by_need = {}
        for donation in donations:
            need_id = donation.get("need_id")
            need_title = donation.get("need_title", "Unknown")

            if need_id:
                key = f"{need_id}:{need_title}"
                if key not in by_need:
                    by_need[key] = {
                        "need_id": need_id,
                        "need_title": need_title,
                        "count": 0,
                        "total_amount": 0
                    }
                by_need[key]["count"] += 1
                by_need[key]["total_amount"] += donation["amount"]

        return {
            "total_donations": total_donations,
            "total_amount": total_amount,
            "average_donation": average_donation,
            "by_payment_method": by_payment_method,
            "by_status": by_status,
            "by_charity": list(by_charity.values()),
            "by_need": list(by_need.values())
        }

    async def generate_tax_receipt(self, donation_id: int, user: User) -> Dict[str, Any]:
        """تولید رسید مالیاتی"""
        donation = await self._get_donation(donation_id)

        # بررسی دسترسی
        if not self._can_view_donation(donation, user):
            raise HTTPException(status_code=403, detail="Not authorized")

        # فقط کمک‌های تکمیل شده
        if donation.status != "completed" or donation.payment_status != "paid":
            raise HTTPException(
                status_code=400,
                detail="Tax receipt can only be generated for completed donations"
            )

        # اگر قبلاً رسید تولید شده
        if donation.receipt_number and donation.tax_receipt_generated:
            # رسید موجود را برگردان
            return await self._get_existing_tax_receipt(donation)

        # تولید رسید جدید
        receipt_number = self._generate_receipt_number()
        donation.receipt_number = receipt_number
        donation.tax_receipt_generated = True
        donation.tax_receipt_generated_at = datetime.utcnow()

        self.db.add(donation)
        await self.db.commit()

        # ساخت رسید
        receipt = {
            "receipt_number": receipt_number,
            "donation_id": donation.id,
            "donor_id": donation.donor_id,
            "donor_name": donation.donor.username if donation.donor and not donation.anonymous else "ناشناس",
            "amount": donation.amount,
            "currency": donation.currency,
            "payment_date": donation.completed_at or donation.created_at,
            "charity_id": donation.charity_id,
            "charity_name": donation.charity.name if donation.charity else None,
            "charity_registration_number": donation.charity.registration_number if donation.charity else None,
            "tax_deductible": True,  # طبق قوانین ایران
            "issued_at": datetime.utcnow(),
            "issued_by": "سیستم خیریه",
            "payment_method": donation.payment_method,
            "tracking_code": donation.tracking_code
        }

        # ثبت لاگ
        await self._log_donation_action(
            donation.id, "tax_receipt_generated", user.id,
            {"receipt_number": receipt_number}
        )

        return receipt

    async def create_cart(self, cart_data: CartCreate, user: User) -> Dict[str, Any]:
        """ایجاد سبد خرید"""
        cart_id = str(uuid.uuid4())
        items = []
        subtotal = 0
        charity_amount = 0

        # پردازش هر آیتم
        for item in cart_data.items:
            product = await self.db.get(Product, item.product_id)
            if not product or product.status != "active":
                raise HTTPException(
                    status_code=404,
                    detail=f"Product {item.product_id} not found or not active"
                )

            # بررسی موجودی
            if product.stock_quantity < item.quantity:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient stock for product {product.name}"
                )

            # محاسبه قیمت
            item_total = product.price * item.quantity
            item_charity = (
                    product.charity_fixed_amount * item.quantity +
                    (item_total * (product.charity_percentage / 100))
            )

            items.append({
                "product_id": product.id,
                "product_name": product.name,
                "quantity": item.quantity,
                "unit_price": product.price,
                "total_price": item_total,
                "charity_amount": item_charity,
                "charity_percentage": product.charity_percentage,
                "charity_fixed_amount": product.charity_fixed_amount
            })

            subtotal += item_total
            charity_amount += item_charity

        # اضافه کردن کمک مستقیم اگر وجود دارد
        direct_donation = 0
        for item in cart_data.items:
            if item.donation_amount:
                direct_donation += item.donation_amount

        charity_amount += direct_donation
        total = subtotal

        # ذخیره سبد خرید (در حالت واقعی در Redis یا دیتابیس)
        cart = {
            "cart_id": cart_id,
            "user_id": user.id,
            "items": items,
            "subtotal": subtotal,
            "charity_amount": charity_amount,
            "direct_donation": direct_donation,
            "total": total,
            "currency": "IRR",
            "charity_id": cart_data.charity_id,
            "need_id": cart_data.need_id,
            "notes": cart_data.notes,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(hours=24)  # 24 ساعت اعتبار
        }

        return cart

    async def checkout_cart(self, cart_id: str, user: User) -> Dict[str, Any]:
        """تسویه حساب سبد خرید"""
        # در حالت واقعی، سبد خرید از حافظه موقت خوانده می‌شود
        # اینجا برای نمونه یک سبد ساختگی برمی‌گردانیم

        # ایجاد سفارش
        order = Order(
            order_number=self._generate_order_number(),
            total_amount=100000,  # مقدار نمونه
            charity_amount=10000,  # مقدار نمونه
            status="pending",
            customer_id=user.id,
            customer_name=user.username or user.email,
            customer_email=user.email,
            payment_status="pending"
        )

        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)

        # ایجاد کمک برای مبلغ خیریه
        if order.charity_amount > 0:
            donation = Donation(
                amount=order.charity_amount,
                currency="IRR",
                payment_method="product_sale",
                status="completed",
                payment_status="paid",
                donor_id=user.id,
                tracking_code=self._generate_tracking_code(),
                completed_at=datetime.utcnow()
            )

            self.db.add(donation)
            await self.db.commit()

        return {
            "order_id": order.id,
            "order_number": order.order_number,
            "total_amount": order.total_amount,
            "charity_amount": order.charity_amount,
            "status": order.status,
            "payment_url": f"/payment/initiate/{order.id}"  # در حالت واقعی URL درگاه
        }

    # ---------- Helper Methods ----------
    async def _validate_donation_data(self, donation_data: DonationCreate, donor: User):
        """اعتبارسنجی داده‌های کمک"""
        # حداقل مبلغ
        if donation_data.amount < 1000:  # حداقل 1000 تومان
            raise HTTPException(status_code=400, detail="Minimum donation amount is 1000")

        # اگر کمک به نیاز است، بررسی کن
        if donation_data.need_id:
            need = await self.db.get(NeedAd, donation_data.need_id)
            if not need:
                raise HTTPException(status_code=404, detail="Need not found")

            # بررسی وضعیت نیاز
            if need.status not in ["active", "pending", "approved"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot donate to need with status: {need.status}"
                )

        # اگر کمک به خیریه است، بررسی کن
        if donation_data.charity_id:
            charity = await self.db.get(Charity, donation_data.charity_id)
            if not charity or not charity.active:
                raise HTTPException(status_code=404, detail="Charity not found or not active")

        # اگر کمک از طریق محصول است، بررسی کن
        if donation_data.product_id:
            product = await self.db.get(Product, donation_data.product_id)
            if not product or product.status != "active":
                raise HTTPException(status_code=404, detail="Product not found or not active")

    async def _get_donation(self, donation_id: int) -> Donation:
        """دریافت کمک با بررسی وجود"""
        donation = await self.db.get(Donation, donation_id)
        if not donation:
            raise HTTPException(status_code=404, detail="Donation not found")
        return donation

    async def _get_donation_with_permission(
            self, donation_id: int, user: User, require_admin: bool = False
    ) -> Donation:
        """دریافت کمک با بررسی مجوز"""
        donation = await self._get_donation(donation_id)

        user_roles = [r.key for r in user.roles]

        if require_admin:
            # فقط ادمین یا مدیر خیریه مربوطه
            if "ADMIN" not in user_roles and "CHARITY_MANAGER" not in user_roles:
                if donation.charity and donation.charity.manager_id != user.id:
                    raise HTTPException(status_code=403, detail="Not authorized")
        else:
            # اهداکننده یا مدیر/ادمین می‌توانند ویرایش کنند
            if donation.donor_id != user.id and \
                    "ADMIN" not in user_roles and \
                    "CHARITY_MANAGER" not in user_roles:
                if donation.charity and donation.charity.manager_id != user.id:
                    raise HTTPException(status_code=403, detail="Not authorized")

        return donation

    def _can_view_donation(self, donation: Donation, user: Optional[User]) -> bool:
        """بررسی مجوز مشاهده کمک"""
        if not user:
            return False  # کمک‌ها عمومی نیستند

        user_roles = [r.key for r in user.roles]

        # ادمین یا مدیر همیشه دسترسی دارد
        if "ADMIN" in user_roles or "CHARITY_MANAGER" in user_roles:
            return True

        # اهداکننده خودش
        if donation.donor_id == user.id:
            return True

        # مدیر خیریه مربوطه
        if donation.charity and donation.charity.manager_id == user.id:
            return True

        return False

    def _can_view_donation_details(self, donation: Donation, user: Optional[User]) -> bool:
        """بررسی مجوز مشاهده جزئیات کمک"""
        if not user:
            return False

        user_roles = [r.key for r in user.roles]

        # ادمین یا مدیر
        if "ADMIN" in user_roles or "CHARITY_MANAGER" in user_roles:
            return True

        # اهداکننده خودش (اگر ناشناس نباشد)
        if donation.donor_id == user.id and not donation.anonymous:
            return True

        return False

    def _can_view_sensitive_details(self, user: Optional[User]) -> bool:
        """بررسی مجوز مشاهده اطلاعات حساس"""
        if not user:
            return False

        user_roles = [r.key for r in user.roles]
        return "ADMIN" in user_roles

    def _generate_tracking_code(self) -> str:
        """تولید کد رهگیری"""
        timestamp = int(datetime.utcnow().timestamp())
        random_part = uuid.uuid4().hex[:6].upper()
        return f"DON-{timestamp}-{random_part}"

    def _generate_receipt_number(self) -> str:
        """تولید شماره رسید"""
        timestamp = int(datetime.utcnow().timestamp())
        random_part = uuid.uuid4().hex[:4].upper()
        return f"REC-{timestamp}-{random_part}"

    def _generate_order_number(self) -> str:
        """تولید شماره سفارش"""
        timestamp = int(datetime.utcnow().timestamp())
        random_part = uuid.uuid4().hex[:4].upper()
        return f"ORD-{timestamp}-{random_part}"

    def _generate_authority_code(self) -> str:
        """تولید کد مرجع پرداخت"""
        timestamp = int(datetime.utcnow().timestamp())
        random_part = uuid.uuid4().hex[:8].upper()
        return f"AUTH-{timestamp}-{random_part}"

    async def _get_gateway_payment_url(
            self, gateway_type: str, authority: str, amount: float
    ) -> str:
        """دریافت URL پرداخت از درگاه"""
        # در حالت واقعی، این تابع به درگاه پرداخت متصل می‌شود
        # اینجا یک URL نمونه برمی‌گردانیم

        base_urls = {
            "zarinpal": "https://sandbox.zarinpal.com/pg/StartPay/",
            "idpay": "https://idpay.ir/p/",
            "mellat": "https://bpm.shaparak.ir/pgwchannel/startpay.mellat",
            "sadad": "https://sadad.shaparak.ir/Purchase",
            "saman": "https://sep.shaparak.ir/Payment.aspx"
        }

        base_url = base_urls.get(gateway_type, "https://sandbox.zarinpal.com/pg/StartPay/")
        return f"{base_url}{authority}"

    async def _verify_with_gateway(
            self, gateway_type: str, authority: str, status: str
    ) -> Dict[str, Any]:
        """تأیید پرداخت با درگاه"""
        # در حالت واقعی، این تابع به درگاه پرداخت متصل می‌شود
        # اینجا یک پاسخ نمونه برمی‌گردانیم

        if status == "OK":
            return {
                "success": True,
                "ref_id": str(uuid.uuid4().int)[:10],
                "card_hash": "621986******1234",
                "message": "Payment verified successfully"
            }
        else:
            return {
                "success": False,
                "message": "Payment verification failed",
                "error_code": "VERIFICATION_FAILED"
            }

    async def _log_donation_action(
            self, donation_id: int, action: str, user_id: Optional[int], details: Dict[str, Any]
    ):
        """ثبت لاگ برای عمل روی کمک"""
        # در حالت واقعی، در AuditLog ذخیره می‌شود
        # اینجا فقط لاگ کنسول می‌دهیم
        print(f"[Donation Log] {action} - Donation: {donation_id}, User: {user_id}, Details: {details}")

    async def _get_donation_status_history(self, donation_id: int) -> List[Dict[str, Any]]:
        """دریافت تاریخچه وضعیت کمک"""
        # در حالت واقعی، از AuditLog خوانده می‌شود
        # اینجا یک لیست نمونه برمی‌گردانیم
        return [
            {
                "status": "pending",
                "changed_at": datetime.utcnow() - timedelta(hours=2),
                "changed_by": "system"
            }
        ]

    async def _generate_tax_receipt(self, donation: Donation):
        """تولید رسید مالیاتی"""
        # در حالت واقعی، رسید PDF تولید و ذخیره می‌شود
        # اینجا فقط فیلدها را پر می‌کنیم
        donation.tax_receipt_generated = True
        donation.tax_receipt_generated_at = datetime.utcnow()

        if not donation.receipt_number:
            donation.receipt_number = self._generate_receipt_number()

        self.db.add(donation)

    async def _get_existing_tax_receipt(self, donation: Donation) -> Dict[str, Any]:
        """دریافت رسید مالیاتی موجود"""
        return {
            "receipt_number": donation.receipt_number,
            "donation_id": donation.id,
            "donor_id": donation.donor_id,
            "donor_name": donation.donor.username if donation.donor and not donation.anonymous else "ناشناس",
            "amount": donation.amount,
            "currency": donation.currency,
            "payment_date": donation.completed_at or donation.created_at,
            "charity_id": donation.charity_id,
            "charity_name": donation.charity.name if donation.charity else None,
            "issued_at": donation.tax_receipt_generated_at,
            "issued_by": "سیستم خیریه"
        }