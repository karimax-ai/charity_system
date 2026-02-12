# app/api/v1/endpoints/order.py
from fastapi import APIRouter, Depends, HTTPException, Query, status, Body
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import math

from core.database import get_db
from core.permissions import get_current_user, require_roles
from models import Charity, Order
from models.order import Coupon, Cart
from models.user import User
from schemas.order import (
    CartCreate, CartUpdate, CartItemCreate, CartItemUpdate, CartRead,
    OrderCreate, OrderUpdate, OrderStatusUpdate, PaymentStatusUpdate,
    OrderRead, OrderDetail, OrderFilter, InventoryUpdate,
    ReturnRequestCreate, ReturnRequestUpdate, CouponCreate, CouponValidate,
    ShopSettings
)
from services.order_management import OrderService

router = APIRouter()


# --------------------------
# 1️⃣ مدیریت سبد خرید
# --------------------------

@router.post("/cart", response_model=Dict[str, Any])
async def create_cart(
        cart_data: CartCreate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """ایجاد سبد خرید جدید"""
    service = OrderService(db)
    cart = await service.create_cart(current_user, cart_data)
    return await service.get_cart(cart.uuid, current_user)


@router.get("/cart/{cart_id}", response_model=Dict[str, Any])
async def get_cart(
        cart_id: str,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """دریافت سبد خرید"""
    service = OrderService(db)
    return await service.get_cart(cart_id, current_user)


@router.put("/cart/{cart_id}", response_model=Dict[str, Any])
async def update_cart(
        cart_id: str,
        cart_data: CartUpdate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """ویرایش سبد خرید"""
    service = OrderService(db)
    cart = await service.update_cart(cart_id, cart_data, current_user)
    return await service.get_cart(cart.uuid, current_user)


@router.post("/cart/{cart_id}/items", response_model=Dict[str, Any])
async def add_cart_item(
        cart_id: str,
        item_data: CartItemCreate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """اضافه کردن آیتم به سبد خرید"""
    service = OrderService(db)
    return await service.add_cart_item(cart_id, item_data, current_user)


@router.put("/cart/{cart_id}/items/{item_id}", response_model=Dict[str, Any])
async def update_cart_item(
        cart_id: str,
        item_id: int,
        item_data: CartItemUpdate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """ویرایش آیتم سبد خرید"""
    service = OrderService(db)
    return await service.update_cart_item(cart_id, item_id, item_data, current_user)


@router.delete("/cart/{cart_id}/items/{item_id}", response_model=Dict[str, Any])
async def remove_cart_item(
        cart_id: str,
        item_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """حذف آیتم از سبد خرید"""
    service = OrderService(db)
    return await service.remove_cart_item(cart_id, item_id, current_user)


@router.delete("/cart/{cart_id}/clear", response_model=Dict[str, Any])
async def clear_cart(
        cart_id: str,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """پاک کردن کامل سبد خرید"""
    service = OrderService(db)
    return await service.clear_cart(cart_id, current_user)


@router.post("/cart/{cart_id}/apply-coupon")
async def apply_coupon(
        cart_id: str,
        coupon_code: str = Body(..., embed=True),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """اعمال کد تخفیف به سبد خرید"""
    service = OrderService(db)
    return await service.apply_coupon(cart_id, coupon_code, current_user)


@router.delete("/cart/{cart_id}/remove-coupon")
async def remove_coupon(
        cart_id: str,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """حذف کد تخفیف از سبد خرید"""
    service = OrderService(db)
    return await service.remove_coupon(cart_id, current_user)


# --------------------------
# 2️⃣ سفارشات
# --------------------------

@router.post("/orders", response_model=OrderDetail)
async def create_order(
        order_data: OrderCreate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """ایجاد سفارش جدید"""
    service = OrderService(db)
    order = await service.create_order(order_data.cart_id, order_data, current_user)
    return await service.get_order(order.id, current_user)


@router.get("/orders", response_model=Dict[str, Any])
async def list_orders(
        customer_id: Optional[int] = Query(None),
        status: Optional[str] = Query(None),
        payment_status: Optional[str] = Query(None),
        shipping_method: Optional[str] = Query(None),
        charity_id: Optional[int] = Query(None),
        need_id: Optional[int] = Query(None),
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
    """لیست سفارشات با فیلتر"""
    filters = OrderFilter(
        customer_id=customer_id,
        status=status,
        payment_status=payment_status,
        shipping_method=shipping_method,
        charity_id=charity_id,
        need_id=need_id,
        min_amount=min_amount,
        max_amount=max_amount,
        start_date=start_date,
        end_date=end_date,
        search_text=search_text,
        sort_by=sort_by,
        sort_order=sort_order
    )

    service = OrderService(db)
    return await service.list_orders(filters, current_user, page, limit)


@router.get("/orders/{order_id}", response_model=OrderDetail)
async def get_order(
        order_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """دریافت اطلاعات یک سفارش"""
    service = OrderService(db)
    return await service.get_order(order_id, current_user)


@router.put("/orders/{order_id}", response_model=OrderDetail)
async def update_order(
        order_id: int,
        order_data: OrderUpdate,
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER")),
        db: AsyncSession = Depends(get_db)
):
    """ویرایش سفارش (ادمین/مدیر)"""
    service = OrderService(db)
    order = await service.update_order(order_id, order_data, current_user)
    return await service.get_order(order.id, current_user)


@router.patch("/orders/{order_id}/status", response_model=OrderDetail)
async def update_order_status(
        order_id: int,
        status_data: OrderStatusUpdate,
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER")),
        db: AsyncSession = Depends(get_db)
):
    """تغییر وضعیت سفارش"""
    service = OrderService(db)
    order = await service.update_order_status(order_id, status_data, current_user)
    return await service.get_order(order.id, current_user)


@router.patch("/orders/{order_id}/payment-status", response_model=OrderDetail)
async def update_payment_status(
        order_id: int,
        status_data: PaymentStatusUpdate,
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER")),
        db: AsyncSession = Depends(get_db)
):
    """تغییر وضعیت پرداخت"""
    service = OrderService(db)
    order = await service.update_payment_status(order_id, status_data, current_user)
    return await service.get_order(order.id, current_user)


@router.post("/orders/{order_id}/cancel")
async def cancel_order(
        order_id: int,
        reason: Optional[str] = Body(None),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """لغو سفارش"""
    service = OrderService(db)
    order = await service.cancel_order(order_id, current_user, reason)
    return {
        "success": True,
        "order_id": order.id,
        "status": order.status,
        "message": "Order cancelled successfully"
    }


# --------------------------
# 3️⃣ سفارشات من (کاربر)
# --------------------------

@router.get("/user/orders", response_model=Dict[str, Any])
async def get_user_orders(
        status: Optional[str] = Query(None),
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """سفارشات کاربر جاری"""
    service = OrderService(db)

    filters = OrderFilter(
        customer_id=current_user.id,
        status=status,
        sort_by="created_at",
        sort_order="desc"
    )

    return await service.list_orders(filters, current_user, page, limit)


@router.get("/user/orders/stats")
async def get_user_order_stats(
        period_days: int = Query(365, ge=1, le=3650),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """آمار سفارشات کاربر"""
    from sqlalchemy import select, func, and_
    from models.order import Order

    start_date = datetime.utcnow() - timedelta(days=period_days)

    # آمار کلی
    total_query = select(
        func.count(Order.id).label("total_orders"),
        func.sum(Order.grand_total).label("total_spent"),
        func.avg(Order.grand_total).label("average_order"),
        func.max(Order.grand_total).label("largest_order"),
        func.min(Order.grand_total).label("smallest_order")
    ).where(
        and_(
            Order.customer_id == current_user.id,
            Order.status != "cancelled",
            Order.created_at >= start_date
        )
    )

    result = await db.execute(total_query)
    stats = result.first()

    # بر اساس وضعیت
    status_query = select(
        Order.status,
        func.count(Order.id).label("count"),
        func.sum(Order.grand_total).label("total")
    ).where(
        and_(
            Order.customer_id == current_user.id,
            Order.created_at >= start_date
        )
    ).group_by(Order.status)

    status_result = await db.execute(status_query)

    by_status = {}
    for row in status_result.all():
        by_status[row.status] = {
            "count": row.count,
            "total_amount": float(row.total or 0)
        }

    # بر اساس ماه
    monthly_query = select(
        func.extract('year', Order.created_at).label("year"),
        func.extract('month', Order.created_at).label("month"),
        func.count(Order.id).label("count"),
        func.sum(Order.grand_total).label("total")
    ).where(
        and_(
            Order.customer_id == current_user.id,
            Order.status != "cancelled",
            Order.created_at >= start_date
        )
    ).group_by(
        func.extract('year', Order.created_at),
        func.extract('month', Order.created_at)
    ).order_by(
        func.extract('year', Order.created_at).desc(),
        func.extract('month', Order.created_at).desc()
    )

    monthly_result = await db.execute(monthly_query)

    by_month = []
    for row in monthly_result.all():
        by_month.append({
            "year": int(row.year),
            "month": int(row.month),
            "order_count": row.count,
            "total_spent": float(row.total or 0)
        })

    # تأثیر خیریه
    charity_query = select(
        Order.charity_id,
        func.count(Order.id).label("order_count"),
        func.sum(Order.charity_amount).label("charity_total")
    ).where(
        and_(
            Order.customer_id == current_user.id,
            Order.status != "cancelled",
            Order.charity_amount > 0,
            Order.created_at >= start_date
        )
    ).group_by(Order.charity_id).order_by(func.sum(Order.charity_amount).desc())

    charity_result = await db.execute(charity_query)

    charity_impact = []
    for row in charity_result.all():
        charity = await db.get(Charity, row.charity_id)
        if charity:
            charity_impact.append({
                "charity_id": row.charity_id,
                "charity_name": charity.name,
                "order_count": row.order_count,
                "charity_total": float(row.charity_total or 0)
            })

    return {
        "user_id": current_user.id,
        "period_days": period_days,
        "total_stats": {
            "order_count": stats.total_orders or 0,
            "total_spent": float(stats.total_spent or 0),
            "average_order": float(stats.average_order or 0),
            "largest_order": float(stats.largest_order or 0),
            "smallest_order": float(stats.smallest_order or 0)
        },
        "by_status": by_status,
        "by_month": by_month,
        "charity_impact": charity_impact
    }


# --------------------------
# 4️⃣ مدیریت موجودی
# --------------------------

@router.post("/inventory/update")
async def update_inventory(
        update_data: InventoryUpdate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """به‌روزرسانی موجودی محصول"""
    service = OrderService(db)
    return await service.update_inventory(update_data, current_user)


@router.get("/inventory/history")
async def get_inventory_history(
        product_id: Optional[int] = Query(None),
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """تاریخچه موجودی"""
    service = OrderService(db)
    return await service.get_inventory_history(product_id, page, limit, current_user)


@router.get("/inventory/low-stock")
async def get_low_stock_products(
        threshold: Optional[int] = Query(None),
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER", "VENDOR")),
        db: AsyncSession = Depends(get_db)
):
    """محصولات با موجودی کم"""
    from sqlalchemy import select, or_
    from models.product import Product

    # تعیین آستانه
    service = OrderService(db)
    low_stock_threshold = threshold or service.settings.low_stock_threshold

    # ساخت کوئری
    query = select(Product).where(
        Product.stock_quantity <= low_stock_threshold
    )

    # اگر فروشنده است، فقط محصولات خودش
    user_roles = [r.key for r in current_user.roles]
    if "VENDOR" in user_roles and "ADMIN" not in user_roles:
        query = query.where(Product.vendor_id == current_user.id)

    # شمارش کل
    total_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(total_query)

    # صفحه‌بندی
    offset = (page - 1) * limit
    query = query.order_by(Product.stock_quantity.asc())
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    products = result.scalars().all()

    # تبدیل به فرمت خروجی
    product_list = []
    for product in products:
        product_list.append({
            "id": product.id,
            "name": product.name,
            "sku": product.sku,
            "stock_quantity": product.stock_quantity,
            "low_stock_threshold": low_stock_threshold,
            "status": product.status,
            "vendor_id": product.vendor_id,
            "vendor_name": product.vendor.username if product.vendor else None,
            "shop_id": product.shop_id,
            "shop_name": product.shop.name if product.shop else None
        })

    return {
        "low_stock_threshold": low_stock_threshold,
        "items": product_list,
        "total": total or 0,
        "page": page,
        "limit": limit,
        "total_pages": math.ceil(total / limit) if total and total > 0 else 0
    }


# --------------------------
# 5️⃣ مدیریت برگشت کالا
# --------------------------

@router.post("/returns")
async def create_return_request(
        return_data: ReturnRequestCreate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """ایجاد درخواست برگشت کالا"""
    service = OrderService(db)
    return_request = await service.create_return_request(return_data, current_user)

    return {
        "success": True,
        "return_id": return_request.id,
        "order_id": return_request.order_id,
        "status": return_request.status,
        "message": "Return request created successfully"
    }


@router.get("/returns")
async def list_return_requests(
        status: Optional[str] = Query(None),
        customer_id: Optional[int] = Query(None),
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """لیست درخواست‌های برگشت"""
    from sqlalchemy import select
    from models.order import ReturnRequest

    query = select(ReturnRequest)

    # اعمال فیلترها
    if status:
        query = query.where(ReturnRequest.status == status)

    if customer_id:
        query = query.where(ReturnRequest.customer_id == customer_id)

    # بررسی دسترسی
    user_roles = [r.key for r in current_user.roles]
    if "ADMIN" not in user_roles and "CHARITY_MANAGER" not in user_roles:
        # کاربر عادی فقط درخواست‌های خودش را می‌بیند
        query = query.where(ReturnRequest.customer_id == current_user.id)

    # شمارش کل
    total_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(total_query)

    # صفحه‌بندی
    offset = (page - 1) * limit
    query = query.order_by(ReturnRequest.created_at.desc())
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    returns = result.scalars().all()

    # تبدیل به فرمت خروجی
    return_list = []
    for return_request in returns:
        customer = await db.get(User, return_request.customer_id)
        order = await db.get(Order, return_request.order_id)

        return_list.append({
            "id": return_request.id,
            "order_id": return_request.order_id,
            "order_number": order.order_number if order else None,
            "customer_id": return_request.customer_id,
            "customer_name": customer.username if customer else None,
            "status": return_request.status,
            "reason": return_request.reason,
            "refund_amount": return_request.refund_amount,
            "refund_method": return_request.refund_method,
            "created_at": return_request.created_at,
            "processed_at": return_request.processed_at
        })

    return {
        "items": return_list,
        "total": total or 0,
        "page": page,
        "limit": limit,
        "total_pages": math.ceil(total / limit) if total and total > 0 else 0
    }


@router.put("/returns/{return_id}")
async def update_return_request(
        return_id: int,
        update_data: ReturnRequestUpdate,
        current_user: User = Depends(require_roles("ADMIN")),
        db: AsyncSession = Depends(get_db)
):
    """ویرایش درخواست برگشت (ادمین)"""
    service = OrderService(db)
    return_request = await service.update_return_request(return_id, update_data, current_user)

    return {
        "success": True,
        "return_id": return_request.id,
        "status": return_request.status,
        "message": "Return request updated successfully"
    }


# --------------------------
# 6️⃣ مدیریت کوپن‌های تخفیف
# --------------------------

@router.post("/coupons", response_model=Dict[str, Any])
async def create_coupon(
        coupon_data: CouponCreate,
        current_user: User = Depends(require_roles("ADMIN")),
        db: AsyncSession = Depends(get_db)
):
    """ایجاد کد تخفیف"""
    service = OrderService(db)
    coupon = await service.create_coupon(coupon_data, current_user)

    return {
        "success": True,
        "coupon": {
            "id": coupon.id,
            "code": coupon.code,
            "discount_type": coupon.discount_type,
            "discount_value": coupon.discount_value,
            "min_order_amount": coupon.min_order_amount,
            "max_discount": coupon.max_discount,
            "usage_limit": coupon.usage_limit,
            "valid_from": coupon.valid_from,
            "valid_until": coupon.valid_until,
            "charity_id": coupon.charity_id,
            "active": coupon.active
        },
        "message": "Coupon created successfully"
    }


@router.post("/coupons/validate")
async def validate_coupon(
        validate_data: CouponValidate,
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """اعتبارسنجی کد تخفیف"""
    service = OrderService(db)
    return await service.validate_coupon(validate_data, current_user)


@router.get("/coupons")
async def list_coupons(
        active_only: bool = Query(True),
        charity_id: Optional[int] = Query(None),
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        current_user: User = Depends(require_roles("ADMIN")),
        db: AsyncSession = Depends(get_db)
):
    """لیست کوپن‌های تخفیف"""
    from sqlalchemy import select
    from models.order import Coupon

    query = select(Coupon)

    if active_only:
        query = query.where(Coupon.active == True)

    if charity_id:
        query = query.where(Coupon.charity_id == charity_id)

    # شمارش کل
    total_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(total_query)

    # صفحه‌بندی
    offset = (page - 1) * limit
    query = query.order_by(Coupon.created_at.desc())
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    coupons = result.scalars().all()

    # تبدیل به فرمت خروجی
    coupon_list = []
    for coupon in coupons:
        charity = await db.get(Charity, coupon.charity_id) if coupon.charity_id else None

        coupon_list.append({
            "id": coupon.id,
            "code": coupon.code,
            "discount_type": coupon.discount_type,
            "discount_value": coupon.discount_value,
            "min_order_amount": coupon.min_order_amount,
            "max_discount": coupon.max_discount,
            "usage_limit": coupon.usage_limit,
            "usage_count": coupon.usage_count,
            "valid_from": coupon.valid_from,
            "valid_until": coupon.valid_until,
            "charity_id": coupon.charity_id,
            "charity_name": charity.name if charity else None,
            "active": coupon.active,
            "created_at": coupon.created_at
        })

    return {
        "items": coupon_list,
        "total": total or 0,
        "page": page,
        "limit": limit,
        "total_pages": math.ceil(total / limit) if total and total > 0 else 0
    }


@router.patch("/coupons/{coupon_id}/activate")
async def activate_coupon(
        coupon_id: int,
        active: bool = Body(..., embed=True),
        current_user: User = Depends(require_roles("ADMIN")),
        db: AsyncSession = Depends(get_db)
):
    """فعال/غیرفعال کردن کوپن"""
    from sqlalchemy import update

    await db.execute(
        update(Coupon)
        .where(Coupon.id == coupon_id)
        .values(active=active, updated_at=datetime.utcnow())
    )
    await db.commit()

    return {
        "success": True,
        "message": f"Coupon {'activated' if active else 'deactivated'} successfully"
    }


# --------------------------
# 7️⃣ آمار و گزارش‌های سفارشات
# --------------------------

@router.get("/stats/summary")
async def get_order_stats_summary(
        start_date: Optional[datetime] = Query(None),
        end_date: Optional[datetime] = Query(None),
        charity_id: Optional[int] = Query(None),
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER")),
        db: AsyncSession = Depends(get_db)
):
    """آمار کلی سفارشات"""
    from sqlalchemy import select, func, and_
    from models.order import Order

    # تنظیم تاریخ‌ها
    if not end_date:
        end_date = datetime.utcnow()
    if not start_date:
        start_date = end_date - timedelta(days=30)

    # شرایط
    conditions = [
        Order.created_at.between(start_date, end_date),
        Order.status != "cancelled"
    ]

    if charity_id:
        conditions.append(Order.charity_id == charity_id)

    # آمار کلی
    stats_query = select(
        func.count(Order.id).label("total_orders"),
        func.sum(Order.grand_total).label("total_revenue"),
        func.avg(Order.grand_total).label("average_order_value"),
        func.sum(Order.charity_amount).label("total_charity"),
        func.count(func.distinct(Order.customer_id)).label("unique_customers")
    ).where(and_(*conditions))

    result = await db.execute(stats_query)
    stats = result.first()

    # آمار بر اساس وضعیت
    status_query = select(
        Order.status,
        func.count(Order.id).label("count"),
        func.sum(Order.grand_total).label("revenue")
    ).where(and_(*conditions)).group_by(Order.status)

    status_result = await db.execute(status_query)

    by_status = {}
    for row in status_result.all():
        by_status[row.status] = {
            "count": row.count,
            "revenue": float(row.revenue or 0),
            "percentage": (row.count / (stats.total_orders or 1)) * 100
        }

    # آمار بر اساس روش ارسال
    shipping_query = select(
        Order.shipping_method,
        func.count(Order.id).label("count")
    ).where(and_(*conditions)).group_by(Order.shipping_method)

    shipping_result = await db.execute(shipping_query)

    by_shipping = {}
    for row in shipping_result.all():
        by_shipping[row.shipping_method] = row.count

    # آمار بر اساس خیریه
    charity_query = select(
        Order.charity_id,
        func.count(Order.id).label("order_count"),
        func.sum(Order.grand_total).label("total_revenue"),
        func.sum(Order.charity_amount).label("charity_amount")
    ).where(
        and_(
            Order.created_at.between(start_date, end_date),
            Order.status != "cancelled",
            Order.charity_id.is_not(None)
        )
    ).group_by(Order.charity_id).order_by(func.sum(Order.charity_amount).desc())

    charity_result = await db.execute(charity_query)

    by_charity = []
    for row in charity_result.all():
        charity = await db.get(Charity, row.charity_id)
        if charity:
            by_charity.append({
                "charity_id": row.charity_id,
                "charity_name": charity.name,
                "order_count": row.order_count,
                "total_revenue": float(row.total_revenue or 0),
                "charity_amount": float(row.charity_amount or 0),
                "charity_percentage": (
                    (row.charity_amount / row.total_revenue * 100)
                    if row.total_revenue and row.total_revenue > 0 else 0
                )
            })

    return {
        "period": {
            "start_date": start_date,
            "end_date": end_date
        },
        "summary": {
            "total_orders": stats.total_orders or 0,
            "total_revenue": float(stats.total_revenue or 0),
            "average_order_value": float(stats.average_order_value or 0),
            "total_charity": float(stats.total_charity or 0),
            "unique_customers": stats.unique_customers or 0,
            "charity_percentage": (
                (stats.total_charity / stats.total_revenue * 100)
                if stats.total_revenue and stats.total_revenue > 0 else 0
            )
        },
        "by_status": by_status,
        "by_shipping_method": by_shipping,
        "by_charity": by_charity
    }


@router.get("/stats/daily")
async def get_daily_order_stats(
        days: int = Query(30, ge=1, le=365),
        charity_id: Optional[int] = Query(None),
        current_user: User = Depends(require_roles("ADMIN", "CHARITY_MANAGER")),
        db: AsyncSession = Depends(get_db)
):
    """آمار روزانه سفارشات"""
    from sqlalchemy import select, func, and_, cast, Date

    start_date = datetime.utcnow() - timedelta(days=days)

    conditions = [
        Order.created_at >= start_date,
        Order.status != "cancelled"
    ]

    if charity_id:
        conditions.append(Order.charity_id == charity_id)

    # گروه‌بندی بر اساس روز
    daily_query = select(
        cast(Order.created_at, Date).label("date"),
        func.count(Order.id).label("order_count"),
        func.sum(Order.grand_total).label("total_revenue"),
        func.sum(Order.charity_amount).label("charity_amount"),
        func.avg(Order.grand_total).label("average_order")
    ).where(and_(*conditions)).group_by(
        cast(Order.created_at, Date)
    ).order_by(cast(Order.created_at, Date))

    result = await db.execute(daily_query)

    daily_stats = []
    for row in result.all():
        daily_stats.append({
            "date": row.date,
            "order_count": row.order_count,
            "total_revenue": float(row.total_revenue or 0),
            "charity_amount": float(row.charity_amount or 0),
            "average_order": float(row.average_order or 0),
            "charity_percentage": (
                (row.charity_amount / row.total_revenue * 100)
                if row.total_revenue and row.total_revenue > 0 else 0
            )
        })

    # پر کردن روزهای بدون سفارش
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
                "order_count": 0,
                "total_revenue": 0,
                "charity_amount": 0,
                "average_order": 0,
                "charity_percentage": 0
            })

        current_date += timedelta(days=1)

    return {
        "period_days": days,
        "start_date": start_date,
        "end_date": datetime.utcnow(),
        "charity_id": charity_id,
        "daily_stats": complete_stats[-days:]  # فقط روزهای درخواستی
    }


@router.get("/stats/conversion")
async def get_conversion_stats(
        days: int = Query(7, ge=1, le=30),
        current_user: User = Depends(require_roles("ADMIN")),
        db: AsyncSession = Depends(get_db)
):
    """آمار تبدیل سبد به سفارش"""
    from sqlalchemy import select, func, and_, cast, Date

    start_date = datetime.utcnow() - timedelta(days=days)

    # تعداد سبدهای ایجاد شده
    carts_query = select(
        cast(Cart.created_at, Date).label("date"),
        func.count(Cart.id).label("carts_created")
    ).where(
        Cart.created_at >= start_date
    ).group_by(
        cast(Cart.created_at, Date)
    ).order_by(cast(Cart.created_at, Date))

    carts_result = await db.execute(carts_query)
    carts_by_date = {row.date: row.carts_created for row in carts_result.all()}

    # تعداد سفارشات ایجاد شده
    orders_query = select(
        cast(Order.created_at, Date).label("date"),
        func.count(Order.id).label("orders_created")
    ).where(
        Order.created_at >= start_date
    ).group_by(
        cast(Order.created_at, Date)
    ).order_by(cast(Order.created_at, Date))

    orders_result = await db.execute(orders_query)
    orders_by_date = {row.date: row.orders_created for row in orders_result.all()}

    # سبدهای تبدیل شده
    converted_query = select(
        cast(Cart.updated_at, Date).label("date"),
        func.count(Cart.id).label("carts_converted")
    ).where(
        and_(
            Cart.updated_at >= start_date,
            Cart.status == "converted"
        )
    ).group_by(
        cast(Cart.updated_at, Date)
    ).order_by(cast(Cart.updated_at, Date))

    converted_result = await db.execute(converted_query)
    converted_by_date = {row.date: row.carts_converted for row in converted_result.all()}

    # محاسبه نرخ تبدیل
    conversion_stats = []
    current_date = start_date.date()
    end_date = datetime.utcnow().date()

    while current_date <= end_date:
        carts = carts_by_date.get(current_date, 0)
        orders = orders_by_date.get(current_date, 0)
        converted = converted_by_date.get(current_date, 0)

        cart_to_order_rate = (converted / carts * 100) if carts > 0 else 0

        conversion_stats.append({
            "date": current_date,
            "carts_created": carts,
            "orders_created": orders,
            "carts_converted": converted,
            "cart_to_order_rate": round(cart_to_order_rate, 2),
            "abandoned_carts": carts - converted
        })

        current_date += timedelta(days=1)

    # آمار کلی
    total_carts = sum(carts_by_date.values())
    total_orders = sum(orders_by_date.values())
    total_converted = sum(converted_by_date.values())

    overall_rate = (total_converted / total_carts * 100) if total_carts > 0 else 0

    return {
        "period_days": days,
        "summary": {
            "total_carts_created": total_carts,
            "total_orders_created": total_orders,
            "total_carts_converted": total_converted,
            "overall_conversion_rate": round(overall_rate, 2),
            "abandoned_carts": total_carts - total_converted,
            "abandonment_rate": round(((total_carts - total_converted) / total_carts * 100) if total_carts > 0 else 0,
                                      2)
        },
        "daily_stats": conversion_stats[-days:]
    }


# --------------------------
# 8️⃣ تنظیمات فروشگاه
# --------------------------

@router.get("/settings")
async def get_shop_settings(
        current_user: User = Depends(require_roles("ADMIN")),
        db: AsyncSession = Depends(get_db)
):
    """دریافت تنظیمات فروشگاه"""
    service = OrderService(db)
    return {
        "success": True,
        "settings": service.settings.dict(),
        "message": "Shop settings retrieved successfully"
    }


@router.put("/settings")
async def update_shop_settings(
        settings: ShopSettings,
        current_user: User = Depends(require_roles("ADMIN")),
        db: AsyncSession = Depends(get_db)
):
    """به‌روزرسانی تنظیمات فروشگاه"""
    # در حالت واقعی در دیتابیس ذخیره می‌شود
    # اینجا فقط نمونه برمی‌گردانیم

    return {
        "success": True,
        "settings": settings.dict(),
        "message": "Shop settings updated successfully"
    }