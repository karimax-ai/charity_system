# app/api/v1/endpoints/donation.py
import self
from fastapi import APIRouter, Depends, HTTPException, Query, status, Body, Request
from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import math
import uuid

from core.database import get_db
from core.permissions import get_current_user, require_roles
from models import Charity
from models.user import User
from models.donation import Donation
from services.donation_service import DonationService
from schemas.donation import (
    DonationCreate, DonationUpdate, DonationStatusUpdate, DonationRead, DonationDetail,
    DonationFilter, PaymentInitiate, PaymentVerify, DirectTransferCreate,
    CourtPaymentCreate, RecurringDonationCreate, RecurringDonationUpdate,
    CartCreate, CartRead, DonationReport, TaxReceipt
)

router = APIRouter()


# --------------------------
# 1️⃣ CRUD اصلی کمک‌ها
# --------------------------

@router.post("/", response_model=DonationDetail)
async def create_donation(
        donation_data: DonationCreate,
        request: Request,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """ایجاد کمک جدید"""
    service = DonationService(db)

    # ثبت IP و User-Agent
    donation_data.donor_ip = request.client.host if request.client else "0.0.0.0"
    donation_data.donor_user_agent = request.headers.get("user-agent", "")

    donation = await service.create_donation(donation_data, current_user)
    return await service.get_donation(donation.id, current_user)


@router.get("/", response_model=Dict[str, Any])
async def list_donations(
        donor_id: Optional[int] = Query(None),
        need_id: Optional[int] = Query(None),
        charity_id: Optional[int] = Query(None),
        product_id: Optional[int] = Query(None),
        status: Optional[str] = Query(None),
        payment_method: Optional[str] = Query(None),
        payment_status: Optional[str] = Query(None),
        min_amount: Optional[float] = Query(None),
        max_amount: Optional[float] = Query(None),
        start_date: Optional[datetime] = Query(None),
        end_date: Optional[datetime] = Query(None),
        search_text: Optional[str] = Query(None),
        sort_by: str = Query("created_at"),
        sort_order: str = Query("desc"),
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """لیست کمک‌ها با فیلتر و صفحه‌بندی"""
    filters = DonationFilter(
        donor_id=donor_id,
        need_id=need_id,
        charity_id=charity_id,
        product_id=product_id,
        status=status,
        payment_method=payment_method,
        payment_status=payment_status,
        min_amount=min_amount,
        max_amount=max_amount,
        start_date=start_date,
        end_date=end_date,
        search_text=search_text,
        sort_by=sort_by,
        sort_order=sort_order
    )

    service = DonationService(db)
    return await service.list_donations(filters, current_user, page, limit)


@router.get("/{donation_id}", response_model=DonationDetail)
async def get_donation(
        donation_id: int,
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """دریافت اطلاعات یک کمک"""
    service = DonationService(db)
    return await service.get_donation(donation_id, current_user)


@router.put("/{donation_id}", response_model=DonationDetail)
async def update_donation(
        donation_id: int,
        donation_data: DonationUpdate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """ویرایش اطلاعات کمک"""
    service = DonationService(db)
    donation = await service.update_donation(donation_id, donation_data, current_user)
    return await service.get_donation(donation.id, current_user)


@router.delete("/{donation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_donation(
        donation_id: int,
        current_user: User = Depends(require_roles("ADMIN")),
        db: AsyncSession = Depends(get_db)
):
    """حذف کمک (فقط ادمین)"""
    from sqlalchemy import delete

    service = DonationService(db)
    donation = await service._get_donation(donation_id)

    # فقط کمک‌های در وضعیت pending قابل حذف هستند
    if donation.status != "pending":
        raise HTTPException(
            status_code=400,
            detail="Can only delete donations in pending status"
        )

    await db.delete(donation)
    await db.commit()

    return None


# --------------------------
# 2️⃣ مدیریت وضعیت کمک‌ها
# --------------------------

@router.patch("/{donation_id}/status", response_model=DonationDetail)
async def update_donation_status(
        donation_id: int,
        status_data: DonationStatusUpdate,
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER")),
        db: AsyncSession = Depends(get_db)
):
    """تغییر وضعیت کمک"""
    service = DonationService(db)
    donation = await service.update_donation_status(donation_id, status_data, current_user)
    return await service.get_donation(donation.id, current_user)


# --------------------------
# 3️⃣ سیستم پرداخت درگاه بانکی
# --------------------------

@router.post("/{donation_id}/pay")
async def initiate_payment(
        donation_id: int,
        payment_data: PaymentInitiate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """آغاز پرداخت از طریق درگاه بانکی"""
    service = DonationService(db)
    result = await service.initiate_payment(payment_data, current_user)

    return {
        "donation_id": donation_id,
        "authority": result["authority"],
        "payment_url": result["payment_url"],
        "amount": result["amount"],
        "currency": result["currency"],
        "gateway_type": payment_data.gateway_type,
        "message": "Payment initiated successfully"
    }


@router.post("/verify")
async def verify_payment(
        verify_data: PaymentVerify,
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """تأیید پرداخت درگاه بانکی"""
    service = DonationService(db)
    donation = await service.verify_payment(verify_data, current_user)

    result = {
        "success": donation.status == "completed",
        "donation_id": donation.id,
        "status": donation.status,
        "payment_status": donation.payment_status,
        "tracking_code": donation.tracking_code,
        "receipt_number": donation.receipt_number,
        "message": "Payment verified successfully" if donation.status == "completed" else "Payment verification failed"
    }

    # اگر پرداخت موفق بود، جزئیات بیشتر برگردان
    if donation.status == "completed":
        result.update({
            "amount": donation.amount,
            "currency": donation.currency,
            "completed_at": donation.completed_at,
            "need_title": donation.need.title if donation.need else None,
            "charity_name": donation.charity.name if donation.charity else None
        })

    return result


@router.post("/callback/{gateway}")
async def payment_callback(
        gateway: str,
        request: Request,
        db: AsyncSession = Depends(get_db)
):
    """Callback از درگاه پرداخت (برای Webhook)"""
    # دریافت پارامترها از درگاه
    form_data = await request.form()
    query_params = dict(request.query_params)

    # لاگ کردن درخواست
    print(f"[Payment Callback] Gateway: {gateway}, Data: {form_data}, Query: {query_params}")

    # پردازش callback بر اساس درگاه
    if gateway == "zarinpal":
        authority = form_data.get("Authority")
        status = form_data.get("Status")
    elif gateway == "idpay":
        authority = form_data.get("id")
        status = form_data.get("status")
    else:
        authority = form_data.get("authority") or form_data.get("ref_id")
        status = form_data.get("status") or form_data.get("code")

    # یافتن کمک بر اساس authority
    if authority:
        service = DonationService(db)

        # جستجوی کمک
        from sqlalchemy import select
        result = await db.execute(
            select(Donation).where(Donation.transaction_id == authority)
        )
        donation = result.scalar_one_or_none()

        if donation:
            # تأیید پرداخت
            verify_data = PaymentVerify(
                donation_id=donation.id,
                authority=authority,
                status=status
            )

            try:
                donation = await service.verify_payment(verify_data, None)
                return {"success": True, "message": "Payment processed"}
            except Exception as e:
                return {"success": False, "error": str(e)}

    return {"success": False, "error": "Invalid callback"}


# --------------------------
# 4️⃣ پرداخت مستقیم (واریز بانکی)
# --------------------------

@router.post("/{donation_id}/direct-transfer")
async def record_direct_transfer(
        donation_id: int,
        transfer_data: DirectTransferCreate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """ثبت پرداخت مستقیم (واریز بانکی)"""
    service = DonationService(db)
    donation = await service.record_direct_transfer(transfer_data, current_user)

    return {
        "donation_id": donation.id,
        "status": donation.status,
        "message": "Direct transfer recorded successfully. Awaiting verification.",
        "reference_number": transfer_data.reference_number,
        "bank_name": transfer_data.bank_name
    }


@router.post("/{donation_id}/verify-transfer")
async def verify_direct_transfer(
        donation_id: int,
        verified: bool = Body(..., embed=True),
        notes: Optional[str] = Body(None),
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER")),
        db: AsyncSession = Depends(get_db)
):
    """تأیید پرداخت مستقیم (توسط ادمین/مدیر)"""
    service = DonationService(db)
    donation = await service._get_donation_with_permission(donation_id, current_user, require_admin=True)

    if donation.payment_method != "direct_transfer":
        raise HTTPException(status_code=400, detail="Not a direct transfer donation")

    if donation.status != "processing":
        raise HTTPException(status_code=400, detail="Donation is not in processing status")

    if verified:
        donation.status = "completed"
        donation.payment_status = "paid"
        donation.completed_at = datetime.utcnow()
        donation.tracking_code = service._generate_tracking_code()
        donation.receipt_number = service._generate_receipt_number()

        # به‌روزرسانی مبلغ جمع‌آوری شده نیاز
        if donation.need:
            donation.need.collected_amount = (donation.need.collected_amount or 0) + donation.amount
            db.add(donation.need)
    else:
        donation.status = "failed"
        donation.payment_status = "failed"

    # افزودن یادداشت
    if notes:
        if not donation.notes:
            donation.notes = ""
        donation.notes += f"\n[Transfer Verification]: {notes}"

    db.add(donation)
    await db.commit()

    return {
        "donation_id": donation.id,
        "status": donation.status,
        "verified": verified,
        "message": "Direct transfer verified" if verified else "Direct transfer rejected"
    }


# --------------------------
# 5️⃣ پرداخت از طریق دادگاه
# --------------------------

@router.post("/{donation_id}/court-payment")
async def record_court_payment(
        donation_id: int,
        court_data: CourtPaymentCreate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """ثبت پرداخت از طریق دادگاه"""
    service = DonationService(db)
    donation = await service.record_court_payment(court_data, current_user)

    return {
        "donation_id": donation.id,
        "status": donation.status,
        "message": "Court payment recorded successfully",
        "court_name": court_data.court_name,
        "case_number": court_data.case_number,
        "receipt_number": court_data.receipt_number
    }


# --------------------------
# 6️⃣ رسید مالیاتی
# --------------------------

@router.post("/{donation_id}/tax-receipt")
async def generate_tax_receipt(
        donation_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """تولید رسید مالیاتی"""
    service = DonationService(db)
    receipt = await service.generate_tax_receipt(donation_id, current_user)

    return {
        "receipt": receipt,
        "message": "Tax receipt generated successfully",
        "download_url": f"/api/receipts/{receipt['receipt_number']}.pdf"  # در حالت واقعی URL دانلود
    }


@router.get("/receipt/{receipt_number}")
async def get_tax_receipt(
        receipt_number: str,
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """دریافت رسید مالیاتی"""
    from sqlalchemy import select

    # یافتن کمک بر اساس شماره رسید
    result = await db.execute(
        select(Donation).where(Donation.receipt_number == receipt_number)
    )
    donation = result.scalar_one_or_none()

    if not donation:
        raise HTTPException(status_code=404, detail="Receipt not found")

    # بررسی دسترسی
    service = DonationService(db)
    if not service._can_view_donation(donation, current_user):
        raise HTTPException(status_code=403, detail="Not authorized")

    # تولید رسید
    receipt = {
        "receipt_number": donation.receipt_number,
        "donation_id": donation.id,
        "donor_id": donation.donor_id,
        "donor_name": donation.donor.username if donation.donor and not donation.anonymous else "ناشناس",
        "amount": donation.amount,
        "currency": donation.currency,
        "payment_date": donation.completed_at or donation.created_at,
        "charity_id": donation.charity_id,
        "charity_name": donation.charity.name if donation.charity else None,
        "charity_registration_number": donation.charity.registration_number if donation.charity else None,
        "tax_deductible": True,
        "issued_at": donation.tax_receipt_generated_at or datetime.utcnow(),
        "issued_by": "سیستم خیریه",
        "payment_method": donation.payment_method,
        "tracking_code": donation.tracking_code
    }

    return {"receipt": receipt}


# --------------------------
# 7️⃣ آمار و گزارش‌ها
# --------------------------

@router.get("/stats/summary")
async def get_donation_stats_summary(
        start_date: Optional[datetime] = Query(None),
        end_date: Optional[datetime] = Query(None),
        charity_id: Optional[int] = Query(None),
        need_id: Optional[int] = Query(None),
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """آمار کلی کمک‌ها"""
    from sqlalchemy import select, func, and_
    from models.donation import Donation

    # ساخت شرایط
    conditions = [Donation.status == "completed", Donation.payment_status == "paid"]

    if start_date:
        conditions.append(Donation.completed_at >= start_date)
    if end_date:
        conditions.append(Donation.completed_at <= end_date)
    if charity_id:
        conditions.append(Donation.charity_id == charity_id)
    if need_id:
        conditions.append(Donation.need_id == need_id)

    # محاسبه آمار
    stats_query = select(
        func.count(Donation.id).label("total_donations"),
        func.sum(Donation.amount).label("total_amount"),
        func.avg(Donation.amount).label("average_donation"),
        func.max(Donation.amount).label("largest_donation"),
        func.min(Donation.amount).label("smallest_donation")
    ).where(and_(*conditions))

    result = await db.execute(stats_query)
    stats = result.first()

    # آمار بر اساس روش پرداخت
    method_query = select(
        Donation.payment_method,
        func.count(Donation.id).label("count"),
        func.sum(Donation.amount).label("total_amount")
    ).where(and_(*conditions)).group_by(Donation.payment_method)

    method_result = await db.execute(method_query)
    by_method = {}
    for row in method_result.all():
        by_method[row.payment_method] = {
            "count": row.count,
            "total_amount": float(row.total_amount or 0),
            "percentage": 0  # بعداً محاسبه می‌شود
        }

    # محاسبه درصد
    total = stats.total_amount or 1
    for method in by_method:
        by_method[method]["percentage"] = (by_method[method]["total_amount"] / total) * 100

    return {
        "period": {
            "start_date": start_date,
            "end_date": end_date or datetime.utcnow()
        },
        "summary": {
            "total_donations": stats.total_donations or 0,
            "total_amount": float(stats.total_amount or 0),
            "average_donation": float(stats.average_donation or 0),
            "largest_donation": float(stats.largest_donation or 0),
            "smallest_donation": float(stats.smallest_donation or 0)
        },
        "by_payment_method": by_method
    }


@router.get("/stats/daily")
async def get_daily_donation_stats(
        days: int = Query(30, ge=1, le=365),
        charity_id: Optional[int] = Query(None),
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """آمار روزانه کمک‌ها"""
    from sqlalchemy import select, func, and_, cast, Date
    from sqlalchemy.sql import label
    from models.donation import Donation

    start_date = datetime.utcnow() - timedelta(days=days)

    conditions = [
        Donation.status == "completed",
        Donation.payment_status == "paid",
        Donation.completed_at >= start_date
    ]

    if charity_id:
        conditions.append(Donation.charity_id == charity_id)

    # گروه‌بندی بر اساس روز
    daily_query = select(
        cast(Donation.completed_at, Date).label("date"),
        func.count(Donation.id).label("donation_count"),
        func.sum(Donation.amount).label("total_amount"),
        func.avg(Donation.amount).label("average_amount")
    ).where(and_(*conditions)).group_by(
        cast(Donation.completed_at, Date)
    ).order_by(cast(Donation.completed_at, Date))

    result = await db.execute(daily_query)

    daily_stats = []
    for row in result.all():
        daily_stats.append({
            "date": row.date,
            "donation_count": row.donation_count,
            "total_amount": float(row.total_amount or 0),
            "average_amount": float(row.average_amount or 0)
        })

    # پر کردن روزهای بدون کمک
    complete_stats = []
    current_date = start_date.date()
    end_date = datetime.utcnow().date()

    while current_date <= end_date:
        found = False
        for stat in daily_stats:
            if stat["date"] == current_date:
                complete_stats.append(stat)
                found = True
                break

        if not found:
            complete_stats.append({
                "date": current_date,
                "donation_count": 0,
                "total_amount": 0,
                "average_amount": 0
            })

        current_date += timedelta(days=1)

    return {
        "period_days": days,
        "start_date": start_date,
        "end_date": datetime.utcnow(),
        "daily_stats": complete_stats[-days:]  # فقط روزهای درخواستی
    }


@router.get("/stats/top-donors")
async def get_top_donors(
        limit: int = Query(10, ge=1, le=100),
        period_days: Optional[int] = Query(30),
        charity_id: Optional[int] = Query(None),
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER")),
        db: AsyncSession = Depends(get_db)
):
    """برترین اهداکنندگان"""
    from sqlalchemy import select, func, and_
    from models.donation import Donation
    from models.user import User

    start_date = datetime.utcnow() - timedelta(days=period_days) if period_days else None

    conditions = [
        Donation.status == "completed",
        Donation.payment_status == "paid",
        Donation.anonymous == False  # فقط اهداکنندگان شناخته شده
    ]

    if start_date:
        conditions.append(Donation.completed_at >= start_date)
    if charity_id:
        conditions.append(Donation.charity_id == charity_id)

    top_donors_query = select(
        Donation.donor_id,
        User.username,
        User.email,
        func.count(Donation.id).label("donation_count"),
        func.sum(Donation.amount).label("total_donated")
    ).join(
        User, Donation.donor_id == User.id
    ).where(
        and_(*conditions)
    ).group_by(
        Donation.donor_id, User.username, User.email
    ).order_by(
        func.sum(Donation.amount).desc()
    ).limit(limit)

    result = await db.execute(top_donors_query)

    top_donors = []
    for row in result.all():
        top_donors.append({
            "donor_id": row.donor_id,
            "username": row.username,
            "email": row.email,
            "donation_count": row.donation_count,
            "total_donated": float(row.total_donated or 0)
        })

    return {
        "period_days": period_days,
        "charity_id": charity_id,
        "top_donors": top_donors
    }


# --------------------------
# 8️⃣ سبد خرید
# --------------------------

@router.post("/cart", response_model=Dict[str, Any])
async def create_cart(
        cart_data: CartCreate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """ایجاد سبد خرید"""
    service = DonationService(db)
    cart = await service.create_cart(cart_data, current_user)

    return {
        "cart": cart,
        "message": "Cart created successfully",
        "checkout_url": f"/api/donations/cart/{cart['cart_id']}/checkout"
    }


@router.get("/cart/{cart_id}")
async def get_cart(
        cart_id: str,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """دریافت اطلاعات سبد خرید"""
    # در حالت واقعی از Redis یا دیتابیس خوانده می‌شود
    # اینجا نمونه برمی‌گردانیم

    return {
        "cart_id": cart_id,
        "status": "active",
        "message": "Cart retrieved successfully",
        "checkout_url": f"/api/donations/cart/{cart_id}/checkout"
    }


@router.post("/cart/{cart_id}/checkout")
async def checkout_cart(
        cart_id: str,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """تسویه حساب سبد خرید"""
    service = DonationService(db)
    result = await service.checkout_cart(cart_id, current_user)

    return {
        "success": True,
        "order": result,
        "message": "Checkout completed successfully"
    }


# --------------------------
# 9️⃣ کمک‌های من
# --------------------------

@router.get("/user/my-donations")
async def get_my_donations(
        status: Optional[str] = Query(None),
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """کمک‌های اهدا شده توسط کاربر"""
    service = DonationService(db)

    filters = DonationFilter(
        donor_id=current_user.id,
        status=status,
        sort_by="created_at",
        sort_order="desc"
    )

    return await service.list_donations(filters, current_user, page, limit)


@router.get("/user/donation-stats")
async def get_my_donation_stats(
        period_days: int = Query(365, ge=1, le=3650),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """آمار کمک‌های کاربر"""
    from sqlalchemy import select, func, and_
    from models.donation import Donation

    start_date = datetime.utcnow() - timedelta(days=period_days)

    # آمار کلی
    total_query = select(
        func.count(Donation.id).label("total_count"),
        func.sum(Donation.amount).label("total_amount"),
        func.avg(Donation.amount).label("average_amount")
    ).where(
        and_(
            Donation.donor_id == current_user.id,
            Donation.status == "completed",
            Donation.completed_at >= start_date
        )
    )

    result = await db.execute(total_query)
    total_stats = result.first()

    # آمار بر اساس خیریه
    charity_query = select(
        Donation.charity_id,
        func.count(Donation.id).label("count"),
        func.sum(Donation.amount).label("amount")
    ).where(
        and_(
            Donation.donor_id == current_user.id,
            Donation.status == "completed",
            Donation.completed_at >= start_date,
            Donation.charity_id.is_not(None)
        )
    ).group_by(Donation.charity_id).order_by(func.sum(Donation.amount).desc()).limit(10)

    charity_result = await db.execute(charity_query)

    by_charity = []
    for row in charity_result.all():
        charity = await db.get(Charity, row.charity_id)
        if charity:
            by_charity.append({
                "charity_id": row.charity_id,
                "charity_name": charity.name,
                "donation_count": row.count,
                "total_amount": float(row.amount or 0)
            })

    # آمار بر اساس ماه
    monthly_query = select(
        func.extract('year', Donation.completed_at).label("year"),
        func.extract('month', Donation.completed_at).label("month"),
        func.count(Donation.id).label("count"),
        func.sum(Donation.amount).label("amount")
    ).where(
        and_(
            Donation.donor_id == current_user.id,
            Donation.status == "completed",
            Donation.completed_at >= start_date
        )
    ).group_by(
        func.extract('year', Donation.completed_at),
        func.extract('month', Donation.completed_at)
    ).order_by(
        func.extract('year', Donation.completed_at).desc(),
        func.extract('month', Donation.completed_at).desc()
    )

    monthly_result = await db.execute(monthly_query)

    by_month = []
    for row in monthly_result.all():
        by_month.append({
            "year": int(row.year),
            "month": int(row.month),
            "donation_count": row.count,
            "total_amount": float(row.amount or 0)
        })

    return {
        "user_id": current_user.id,
        "period_days": period_days,
        "total_stats": {
            "donation_count": total_stats.total_count or 0,
            "total_amount": float(total_stats.total_amount or 0),
            "average_donation": float(total_stats.average_amount or 0)
        },
        "by_charity": by_charity,
        "by_month": by_month,
        "impact": {
            "needs_supported": await self._count_needs_supported(current_user.id, db),
            "charities_supported": len(by_charity),
            "estimated_lives_impacted": int((total_stats.total_amount or 0) / 1000000)  # تخمین
        }
    }


async def _count_needs_supported(user_id: int, db: AsyncSession) -> int:
    """شمارش نیازهای پشتیبانی شده توسط کاربر"""
    from sqlalchemy import select, func, distinct
    from models.donation import Donation

    query = select(func.count(distinct(Donation.need_id))).where(
        and_(
            Donation.donor_id == user_id,
            Donation.status == "completed",
            Donation.need_id.is_not(None)
        )
    )

    result = await db.execute(query)
    return result.scalar() or 0


# --------------------------
# 🔟 گزارش‌گیری
# --------------------------

@router.get("/reports/generate")
async def generate_donation_report(
        report_type: str = Query("summary", regex="^(summary|detailed|charity|needs)$"),
        format: str = Query("json", regex="^(json|csv|pdf)$"),
        start_date: Optional[datetime] = Query(None),
        end_date: Optional[datetime] = Query(None),
        charity_id: Optional[int] = Query(None),
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER")),
        db: AsyncSession = Depends(get_db)
):
    """تولید گزارش کمک‌ها"""
    service = DonationService(db)

    filters = DonationFilter(
        start_date=start_date,
        end_date=end_date,
        charity_id=charity_id
    )

    if report_type == "summary":
        report = await service.get_donation_stats(filters, current_user)
    else:
        # برای انواع دیگر گزارش‌ها
        report = {"type": report_type, "message": "Report generation not yet implemented"}

    # تبدیل به فرمت درخواستی
    if format == "csv":
        # تولید CSV
        csv_content = self._convert_to_csv(report)
        return {
            "format": "csv",
            "content": csv_content,
            "filename": f"donation_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        }
    elif format == "pdf":
        # تولید PDF
        return {
            "format": "pdf",
            "url": f"/api/reports/donations/{uuid.uuid4()}.pdf",
            "filename": f"donation_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
        }
    else:
        return {
            "format": "json",
            "report": report,
            "generated_at": datetime.utcnow()
        }


def _convert_to_csv(self, data: Dict[str, Any]) -> str:
    """تبدیل داده‌ها به فرمت CSV"""
    # این تابع ساده‌ای است، در حالت واقعی کامل‌تر است
    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output)

    if "summary" in data:
        writer.writerow(["Metric", "Value"])
        writer.writerow(["Total Donations", data["summary"].get("total_donations", 0)])
        writer.writerow(["Total Amount", data["summary"].get("total_amount", 0)])
        writer.writerow(["Average Donation", data["summary"].get("average_donation", 0)])

    return output.getvalue()


# --------------------------
# تنظیمات درگاه پرداخت
# --------------------------

@router.get("/gateways")
async def get_payment_gateways(
        enabled_only: bool = Query(True),
        current_user: User = Depends(require_roles("ADMIN")),
        db: AsyncSession = Depends(get_db)
):
    """لیست درگاه‌های پرداخت"""
    # در حالت واقعی از دیتابیس خوانده می‌شود
    gateways = [
        {
            "id": "zarinpal",
            "name": "درگاه زرین‌پال",
            "enabled": True,
            "sandbox": True,
            "merchant_id": "test",
            "supported_currencies": ["IRR"],
            "transaction_fee": "2.5%",
            "min_amount": 1000,
            "max_amount": 500000000,
            "logo_url": "/static/gateways/zarinpal.png"
        },
        {
            "id": "idpay",
            "name": "درگاه آیدی پی",
            "enabled": True,
            "sandbox": True,
            "merchant_id": "test",
            "supported_currencies": ["IRR"],
            "transaction_fee": "2%",
            "min_amount": 1000,
            "max_amount": 500000000,
            "logo_url": "/static/gateways/idpay.png"
        },
        {
            "id": "mellat",
            "name": "درگاه ملت",
            "enabled": False,
            "sandbox": False,
            "merchant_id": None,
            "supported_currencies": ["IRR"],
            "transaction_fee": "2.5%",
            "min_amount": 1000,
            "max_amount": 500000000,
            "logo_url": "/static/gateways/mellat.png"
        }
    ]

    if enabled_only:
        gateways = [g for g in gateways if g["enabled"]]

    return {"gateways": gateways}