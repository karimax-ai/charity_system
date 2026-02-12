# app/services/order_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, asc, update, case
from fastapi import HTTPException, status
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
import math
import uuid

from models.order import Cart, CartItem, Order, OrderItem, InventoryHistory, ReturnRequest, Coupon
from models.product import Product
from models.user import User
from models.charity import Charity
from models.need_ad import NeedAd
from schemas.order import (
    CartCreate, CartUpdate, CartItemCreate, CartItemUpdate, OrderCreate,
    OrderUpdate, OrderStatusUpdate, PaymentStatusUpdate, OrderFilter,
    InventoryUpdate, ReturnRequestCreate, ReturnRequestUpdate,
    CouponCreate, CouponValidate, ShopSettings
)


class OrderService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = self._get_default_settings()

    # ---------- Cart Management ----------

    async def create_cart(self, user: User, cart_data: CartCreate) -> Cart:
        """ایجاد سبد خرید جدید"""
        # بررسی وجود سبد فعال
        existing_cart = await self.db.execute(
            select(Cart).where(
                and_(
                    Cart.user_id == user.id,
                    Cart.status == "active"
                )
            )
        )
        existing = existing_cart.scalar_one_or_none()

        if existing:
            # به‌روزرسانی سبد موجود
            return await self.update_cart(existing.uuid, cart_data, user)

        # ایجاد سبد جدید
        cart = Cart(
            user_id=user.id,
            status="active",
            expires_at=datetime.utcnow() + timedelta(minutes=self.settings.cart_expiry_minutes)
        )

        self.db.add(cart)
        await self.db.commit()
        await self.db.refresh(cart)

        # اضافه کردن آیتم‌ها
        if cart_data.items:
            for item_data in cart_data.items:
                await self._add_cart_item(cart.id, item_data, user)

        # به‌روزرسانی اطلاعات سبد
        cart.charity_id = cart_data.charity_id
        cart.need_id = cart_data.need_id
        cart.notes = cart_data.notes

        await self._recalculate_cart(cart.id)

        return cart

    async def get_cart(self, cart_id: str, user: User) -> Dict[str, Any]:
        """دریافت سبد خرید"""
        cart = await self._get_cart_with_permission(cart_id, user)
        return await self._prepare_cart_data(cart)

    async def update_cart(self, cart_id: str, cart_data: CartUpdate, user: User) -> Cart:
        """ویرایش سبد خرید"""
        cart = await self._get_cart_with_permission(cart_id, user)

        # به‌روزرسانی فیلدها
        if cart_data.charity_id is not None:
            cart.charity_id = cart_data.charity_id
        if cart_data.need_id is not None:
            cart.need_id = cart_data.need_id
        if cart_data.notes is not None:
            cart.notes = cart_data.notes

        await self._recalculate_cart(cart.id)
        return cart

    async def add_cart_item(self, cart_id: str, item_data: CartItemCreate, user: User) -> Dict[str, Any]:
        """اضافه کردن آیتم به سبد خرید"""
        cart = await self._get_cart_with_permission(cart_id, user)

        # بررسی وجود محصول
        product = await self.db.get(Product, item_data.product_id)
        if not product or product.status != "active":
            raise HTTPException(status_code=404, detail="Product not found or not active")

        # بررسی موجودی
        if product.stock_quantity < item_data.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock. Available: {product.stock_quantity}"
            )

        # بررسی وجود آیتم مشابه در سبد
        existing_item = await self.db.execute(
            select(CartItem).where(
                and_(
                    CartItem.cart_id == cart.id,
                    CartItem.product_id == item_data.product_id
                )
            )
        )
        existing = existing_item.scalar_one_or_none()

        if existing:
            # به‌روزرسانی مقدار موجود
            existing.quantity += item_data.quantity
            existing.donation_amount = item_data.donation_amount or existing.donation_amount
            self.db.add(existing)
        else:
            # ایجاد آیتم جدید
            cart_item = CartItem(
                cart_id=cart.id,
                product_id=item_data.product_id,
                quantity=item_data.quantity,
                unit_price=product.price,
                subtotal=product.price * item_data.quantity,
                charity_percentage=product.charity_percentage,
                charity_fixed_amount=product.charity_fixed_amount,
                charity_total=(
                        product.charity_fixed_amount * item_data.quantity +
                        (product.price * item_data.quantity * (product.charity_percentage / 100))
                ),
                donation_amount=item_data.donation_amount or 0.0
            )
            self.db.add(cart_item)

        await self.db.commit()
        await self._recalculate_cart(cart.id)

        return await self.get_cart(cart_id, user)

    async def update_cart_item(self, cart_id: str, item_id: int, item_data: CartItemUpdate, user: User) -> Dict[
        str, Any]:
        """ویرایش آیتم سبد خرید"""
        cart = await self._get_cart_with_permission(cart_id, user)

        # یافتن آیتم
        item = await self.db.get(CartItem, item_id)
        if not item or item.cart_id != cart.id:
            raise HTTPException(status_code=404, detail="Cart item not found")

        product = await self.db.get(Product, item.product_id)

        # به‌روزرسانی مقدار
        if item_data.quantity is not None:
            if item_data.quantity < 1:
                # حذف آیتم اگر مقدار صفر شد
                await self.db.delete(item)
            else:
                # بررسی موجودی
                if product.stock_quantity < item_data.quantity:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Insufficient stock. Available: {product.stock_quantity}"
                    )

                item.quantity = item_data.quantity
                item.subtotal = product.price * item_data.quantity
                item.charity_total = (
                        product.charity_fixed_amount * item_data.quantity +
                        (product.price * item_data.quantity * (product.charity_percentage / 100))
                )

        # به‌روزرسانی مبلغ کمک
        if item_data.donation_amount is not None:
            item.donation_amount = item_data.donation_amount

        self.db.add(item)
        await self.db.commit()
        await self._recalculate_cart(cart.id)

        return await self.get_cart(cart_id, user)

    async def remove_cart_item(self, cart_id: str, item_id: int, user: User) -> Dict[str, Any]:
        """حذف آیتم از سبد خرید"""
        cart = await self._get_cart_with_permission(cart_id, user)

        # یافتن و حذف آیتم
        item = await self.db.get(CartItem, item_id)
        if item and item.cart_id == cart.id:
            await self.db.delete(item)
            await self.db.commit()
            await self._recalculate_cart(cart.id)

        return await self.get_cart(cart_id, user)

    async def clear_cart(self, cart_id: str, user: User) -> Dict[str, Any]:
        """پاک کردن کامل سبد خرید"""
        cart = await self._get_cart_with_permission(cart_id, user)

        # حذف تمام آیتم‌ها
        items = await self.db.execute(
            select(CartItem).where(CartItem.cart_id == cart.id)
        )
        for item in items.scalars().all():
            await self.db.delete(item)

        await self.db.commit()
        await self._recalculate_cart(cart.id)

        return await self.get_cart(cart_id, user)

    async def apply_coupon(self, cart_id: str, coupon_code: str, user: User) -> Dict[str, Any]:
        """اعمال کد تخفیف"""
        cart = await self._get_cart_with_permission(cart_id, user)

        # بررسی کوپن
        coupon = await self._validate_coupon(coupon_code, cart, user)
        if not coupon:
            raise HTTPException(status_code=400, detail="Invalid coupon")

        # اعمال تخفیف
        discount = await self._calculate_discount(cart, coupon)
        cart.discount_amount = discount
        cart.coupon_id = coupon.id

        await self._recalculate_cart(cart.id)

        return {
            "success": True,
            "discount": discount,
            "message": f"Coupon applied successfully. Discount: {discount} {cart.currency}"
        }

    async def remove_coupon(self, cart_id: str, user: User) -> Dict[str, Any]:
        """حذف کد تخفیف"""
        cart = await self._get_cart_with_permission(cart_id, user)

        cart.discount_amount = 0
        cart.coupon_id = None

        await self._recalculate_cart(cart.id)

        return {
            "success": True,
            "message": "Coupon removed successfully"
        }

    # ---------- Order Management ----------

    async def create_order(self, cart_id: str, order_data: OrderCreate, user: User) -> Order:
        """ایجاد سفارش از سبد خرید"""
        cart = await self._get_cart_with_permission(cart_id, user)

        # بررسی سبد خالی نباشد
        if cart.subtotal <= 0:
            raise HTTPException(status_code=400, detail="Cart is empty")

        # بررسی انقضای سبد
        if cart.expires_at < datetime.utcnow():
            cart.status = "expired"
            self.db.add(cart)
            await self.db.commit()
            raise HTTPException(status_code=400, detail="Cart has expired")

        # بررسی موجودی محصولات
        await self._validate_cart_inventory(cart)

        # ایجاد شماره سفارش
        order_number = self._generate_order_number()

        # تنظیم اطلاعات مشتری
        customer_name = order_data.customer_name or user.username or user.email
        customer_email = order_data.customer_email or user.email

        # ایجاد سفارش
        order = Order(
            order_number=order_number,
            status="pending",
            payment_status="pending",

            # اطلاعات مالی
            subtotal=cart.subtotal,
            shipping_cost=cart.shipping_cost,
            tax_amount=cart.tax_amount,
            discount_amount=cart.discount_amount,
            charity_amount=cart.charity_amount + cart.donation_amount,
            grand_total=cart.grand_total,
            currency=cart.currency,

            # اطلاعات مشتری
            customer_id=user.id,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=order_data.customer_phone or user.phone,

            # اطلاعات ارسال
            shipping_method=order_data.shipping_method,
            shipping_address=order_data.shipping_address,
            shipping_city=order_data.shipping_city,
            shipping_province=order_data.shipping_province,
            shipping_postal_code=order_data.shipping_postal_code,
            shipping_notes=order_data.shipping_notes,

            # اطلاعات صورتحساب
            billing_address=(
                order_data.billing_address
                if not order_data.billing_same_as_shipping
                else order_data.shipping_address
            ),
            billing_city=(
                order_data.billing_city
                if not order_data.billing_same_as_shipping
                else order_data.shipping_city
            ),
            billing_province=(
                order_data.billing_province
                if not order_data.billing_same_as_shipping
                else order_data.shipping_province
            ),

            # اطلاعات پرداخت
            payment_method=order_data.payment_method,

            # اطلاعات مرتبط
            charity_id=cart.charity_id,
            need_id=cart.need_id,
            coupon_id=cart.coupon_id
        )

        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)

        # ایجاد آیتم‌های سفارش از سبد
        await self._create_order_items(order.id, cart.id)

        # کاهش موجودی محصولات
        await self._update_inventory_from_cart(cart.id, "order", user.id)

        # تغییر وضعیت سبد
        cart.status = "converted"
        cart.updated_at = datetime.utcnow()
        self.db.add(cart)

        # ایجاد کمک از مبلغ خیریه
        if order.charity_amount > 0:
            await self._create_charity_donation(order, user)

        await self.db.commit()

        # ثبت لاگ
        await self._log_order_action(order.id, "created", user.id, {"cart_id": cart_id})

        return order

    async def get_order(self, order_id: int, user: User) -> Dict[str, Any]:
        """دریافت سفارش"""
        order = await self._get_order_with_permission(order_id, user)
        return await self._prepare_order_data(order, user)

    async def update_order(self, order_id: int, update_data: OrderUpdate, user: User) -> Order:
        """ویرایش سفارش (ادمین/مدیر)"""
        order = await self._get_order_with_permission(order_id, user, require_admin=True)

        old_status = order.status

        # به‌روزرسانی فیلدها
        for key, value in update_data.dict(exclude_unset=True).items():
            if value is not None:
                setattr(order, key, value)

        # اگر وضعیت تغییر کرد
        if update_data.status and update_data.status != old_status:
            order = await self._handle_status_change(order, update_data.status, user)

        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)

        # ثبت لاگ
        await self._log_order_action(
            order.id, "updated", user.id,
            {"changes": update_data.dict(exclude_unset=True)}
        )

        return order

    async def update_order_status(self, order_id: int, status_data: OrderStatusUpdate, user: User) -> Order:
        """تغییر وضعیت سفارش"""
        order = await self._get_order_with_permission(order_id, user, require_admin=True)

        old_status = order.status
        order.status = status_data.status

        # مدیریت تغییر وضعیت
        order = await self._handle_status_change(order, status_data.status, user)

        # افزودن یادداشت
        if status_data.notes:
            if not order.internal_notes:
                order.internal_notes = ""
            order.internal_notes += f"\n[Status Change to {status_data.status}]: {status_data.notes}"

        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)

        # ثبت لاگ
        await self._log_order_action(
            order.id, "status_changed", user.id,
            {"from": old_status, "to": status_data.status, "notes": status_data.notes}
        )

        return order

    async def update_payment_status(self, order_id: int, status_data: PaymentStatusUpdate, user: User) -> Order:
        """تغییر وضعیت پرداخت"""
        order = await self._get_order_with_permission(order_id, user, require_admin=True)

        old_status = order.payment_status
        order.payment_status = status_data.status

        # اگر پرداخت شد
        if status_data.status == "paid":
            order.paid_at = datetime.utcnow()
            order.status = "confirmed"  # تأیید سفارش بعد از پرداخت
        elif status_data.status == "refunded":
            order.refunded_at = datetime.utcnow()
            # برگشت موجودی
            await self._restore_inventory_from_order(order.id, "refund", user.id)

        # ذخیره شماره تراکنش
        if status_data.transaction_id:
            order.transaction_id = status_data.transaction_id

        # افزودن یادداشت
        if status_data.notes:
            if not order.internal_notes:
                order.internal_notes = ""
            order.internal_notes += f"\n[Payment Status Change to {status_data.status}]: {status_data.notes}"

        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)

        # ثبت لاگ
        await self._log_order_action(
            order.id, "payment_status_changed", user.id,
            {"from": old_status, "to": status_data.status, "transaction_id": status_data.transaction_id}
        )

        return order

    async def cancel_order(self, order_id: int, user: User, reason: Optional[str] = None) -> Order:
        """لغو سفارش"""
        order = await self._get_order_with_permission(order_id, user)

        # بررسی مجاز بودن لغو
        if order.status not in ["pending", "confirmed"]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel order in {order.status} status"
            )

        old_status = order.status
        order.status = "cancelled"
        order.cancelled_at = datetime.utcnow()

        # برگشت موجودی
        await self._restore_inventory_from_order(order.id, "cancellation", user.id)

        # افزودن دلیل
        if reason:
            if not order.internal_notes:
                order.internal_notes = ""
            order.internal_notes += f"\n[Cancellation Reason]: {reason}"

        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)

        # ثبت لاگ
        await self._log_order_action(
            order.id, "cancelled", user.id,
            {"reason": reason, "previous_status": old_status}
        )

        return order

    async def list_orders(
            self, filters: OrderFilter, user: Optional[User] = None, page: int = 1, limit: int = 20
    ) -> Dict[str, Any]:
        """لیست سفارشات با فیلتر"""
        query = select(Order)

        # اعمال فیلترها
        conditions = []

        if filters.customer_id:
            conditions.append(Order.customer_id == filters.customer_id)

        if filters.status:
            conditions.append(Order.status == filters.status)

        if filters.payment_status:
            conditions.append(Order.payment_status == filters.payment_status)

        if filters.shipping_method:
            conditions.append(Order.shipping_method == filters.shipping_method)

        if filters.charity_id:
            conditions.append(Order.charity_id == filters.charity_id)

        if filters.need_id:
            conditions.append(Order.need_id == filters.need_id)

        if filters.min_amount:
            conditions.append(Order.grand_total >= filters.min_amount)

        if filters.max_amount:
            conditions.append(Order.grand_total <= filters.max_amount)

        if filters.start_date:
            conditions.append(Order.created_at >= filters.start_date)

        if filters.end_date:
            conditions.append(Order.created_at <= filters.end_date)

        if filters.search_text:
            conditions.append(
                or_(
                    Order.order_number.ilike(f"%{filters.search_text}%"),
                    Order.customer_name.ilike(f"%{filters.search_text}%"),
                    Order.customer_email.ilike(f"%{filters.search_text}%"),
                    Order.shipping_tracking_code.ilike(f"%{filters.search_text}%")
                )
            )

        # اگر کاربر مشخص شده، بررسی دسترسی
        if user:
            user_roles = [r.key for r in user.roles]
            if "ADMIN" not in user_roles and "CHARITY_MANAGER" not in user_roles:
                # کاربر عادی فقط سفارشات خودش را می‌بیند
                conditions.append(Order.customer_id == user.id)

        if conditions:
            query = query.where(and_(*conditions))

        # مرتب‌سازی
        sort_column = getattr(Order, filters.sort_by, Order.created_at)
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
        orders = result.scalars().all()

        # تبدیل به فرمت خروجی
        order_list = []
        for order in orders:
            order_data = await self._prepare_order_data(order, user)
            order_list.append(order_data)

        return {
            "items": order_list,
            "total": total or 0,
            "page": page,
            "limit": limit,
            "total_pages": math.ceil(total / limit) if total and total > 0 else 0
        }

    # ---------- Inventory Management ----------

    async def update_inventory(self, update_data: InventoryUpdate, user: User) -> Dict[str, Any]:
        """به‌روزرسانی موجودی محصول"""
        product = await self.db.get(Product, update_data.product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        # بررسی مجوز
        user_roles = [r.key for r in user.roles]
        if "ADMIN" not in user_roles and "CHARITY_MANAGER" not in user_roles:
            if product.vendor_id != user.id:
                raise HTTPException(status_code=403, detail="Not authorized to update inventory")

        old_quantity = product.stock_quantity
        new_quantity = old_quantity + update_data.adjustment

        if new_quantity < 0:
            raise HTTPException(status_code=400, detail="Inventory cannot be negative")

        # به‌روزرسانی موجودی
        product.stock_quantity = new_quantity

        # ثبت تاریخچه
        history = InventoryHistory(
            product_id=product.id,
            previous_quantity=old_quantity,
            new_quantity=new_quantity,
            adjustment=update_data.adjustment,
            reason=update_data.reason,
            notes=update_data.notes,
            created_by=user.id
        )

        self.db.add(product)
        self.db.add(history)
        await self.db.commit()

        return {
            "product_id": product.id,
            "product_name": product.name,
            "old_quantity": old_quantity,
            "new_quantity": new_quantity,
            "adjustment": update_data.adjustment,
            "message": "Inventory updated successfully"
        }

    async def get_inventory_history(
            self, product_id: Optional[int] = None, page: int = 1, limit: int = 20, user: Optional[User] = None
    ) -> Dict[str, Any]:
        """تاریخچه موجودی"""
        query = select(InventoryHistory)

        if product_id:
            query = query.where(InventoryHistory.product_id == product_id)

        # بررسی دسترسی
        if user:
            user_roles = [r.key for r in user.roles]
            if "ADMIN" not in user_roles and "CHARITY_MANAGER" not in user_roles:
                # فقط محصولات خود کاربر
                product_query = select(Product.id).where(Product.vendor_id == user.id)
                query = query.where(InventoryHistory.product_id.in_(product_query))

        # شمارش کل
        total_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(total_query)

        # صفحه‌بندی
        offset = (page - 1) * limit
        query = query.order_by(InventoryHistory.created_at.desc())
        query = query.offset(offset).limit(limit)

        result = await self.db.execute(query)
        history = result.scalars().all()

        # تبدیل به فرمت خروجی
        history_list = []
        for record in history:
            product = await self.db.get(Product, record.product_id)
            creator = await self.db.get(User, record.created_by) if record.created_by else None

            history_list.append({
                "id": record.id,
                "product_id": record.product_id,
                "product_name": product.name if product else "Unknown",
                "previous_quantity": record.previous_quantity,
                "new_quantity": record.new_quantity,
                "adjustment": record.adjustment,
                "reason": record.reason,
                "notes": record.notes,
                "created_by": record.created_by,
                "created_by_name": creator.username if creator else "System",
                "created_at": record.created_at
            })

        return {
            "items": history_list,
            "total": total or 0,
            "page": page,
            "limit": limit,
            "total_pages": math.ceil(total / limit) if total and total > 0 else 0
        }

    # ---------- Return Management ----------

    async def create_return_request(self, return_data: ReturnRequestCreate, user: User) -> ReturnRequest:
        """ایجاد درخواست برگشت"""
        order = await self._get_order_with_permission(return_data.order_id, user)

        # بررسی مجاز بودن برگشت
        if order.status != "delivered":
            raise HTTPException(status_code=400, detail="Only delivered orders can be returned")

        if order.created_at < datetime.utcnow() - timedelta(days=self.settings.return_policy_days):
            raise HTTPException(
                status_code=400,
                detail=f"Return period expired. Policy allows returns within {self.settings.return_policy_days} days"
            )

        # ایجاد درخواست
        return_request = ReturnRequest(
            order_id=order.id,
            customer_id=user.id,
            status="pending",
            items=return_data.items,
            reason=return_data.reason,
            description=return_data.description,
            refund_amount=return_data.refund_amount,
            refund_method=return_data.preferred_method
        )

        self.db.add(return_request)
        await self.db.commit()
        await self.db.refresh(return_request)

        return return_request

    async def update_return_request(
            self, return_id: int, update_data: ReturnRequestUpdate, user: User
    ) -> ReturnRequest:
        """ویرایش درخواست برگشت (ادمین)"""
        return_request = await self._get_return_request(return_id)

        # بررسی مجوز
        user_roles = [r.key for r in user.roles]
        if "ADMIN" not in user_roles:
            raise HTTPException(status_code=403, detail="Only admins can process returns")

        # به‌روزرسانی
        if update_data.status:
            old_status = return_request.status
            return_request.status = update_data.status

            if update_data.status == "processed":
                return_request.processed_at = datetime.utcnow()
                return_request.processed_by = user.id

                # اگر بازپرداخت است
                if update_data.refund_amount:
                    return_request.refund_amount = update_data.refund_amount

                if update_data.refund_method:
                    return_request.refund_method = update_data.refund_method

                # برگشت موجودی
                await self._restore_inventory_from_return(return_request)

        if update_data.admin_notes:
            return_request.admin_notes = update_data.admin_notes

        self.db.add(return_request)
        await self.db.commit()
        await self.db.refresh(return_request)

        return return_request

    # ---------- Coupon Management ----------

    async def create_coupon(self, coupon_data: CouponCreate, user: User) -> Coupon:
        """ایجاد کد تخفیف"""
        # بررسی مجوز
        user_roles = [r.key for r in user.roles]
        if "ADMIN" not in user_roles:
            raise HTTPException(status_code=403, detail="Only admins can create coupons")

        # بررسی کد تکراری
        existing = await self.db.execute(
            select(Coupon).where(Coupon.code == coupon_data.code.upper())
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Coupon code already exists")

        # ایجاد کوپن
        coupon = Coupon(
            code=coupon_data.code.upper(),
            discount_type=coupon_data.discount_type,
            discount_value=coupon_data.discount_value,
            min_order_amount=coupon_data.min_order_amount,
            max_discount=coupon_data.max_discount,
            usage_limit=coupon_data.usage_limit,
            valid_from=coupon_data.valid_from,
            valid_until=coupon_data.valid_until,
            charity_id=coupon_data.charity_id,
            product_ids=coupon_data.products,
            active=True
        )

        self.db.add(coupon)
        await self.db.commit()
        await self.db.refresh(coupon)

        return coupon

    async def validate_coupon(self, validate_data: CouponValidate, user: Optional[User] = None) -> Dict[str, Any]:
        """اعتبارسنجی کد تخفیف"""
        cart = await self._get_cart(validate_data.cart_id)

        if not cart:
            raise HTTPException(status_code=404, detail="Cart not found")

        # بررسی دسترسی به سبد
        if user and cart.user_id != user.id:
            raise HTTPException(status_code=403, detail="Not authorized")

        # اعتبارسنجی کوپن
        coupon = await self._validate_coupon(validate_data.code, cart, validate_data.customer_id)

        if not coupon:
            return {"valid": False, "message": "Invalid coupon code"}

        # محاسبه تخفیف
        discount = await self._calculate_discount(cart, coupon)

        return {
            "valid": True,
            "coupon": {
                "code": coupon.code,
                "discount_type": coupon.discount_type,
                "discount_value": coupon.discount_value,
                "max_discount": coupon.max_discount
            },
            "discount_amount": discount,
            "message": f"Valid coupon. Discount: {discount} {cart.currency}"
        }

    # ---------- Helper Methods ----------

    async def _get_cart(self, cart_id: str) -> Optional[Cart]:
        """دریافت سبد خرید"""
        result = await self.db.execute(
            select(Cart).where(Cart.uuid == cart_id)
        )
        return result.scalar_one_or_none()

    async def _get_cart_with_permission(self, cart_id: str, user: User) -> Cart:
        """دریافت سبد خرید با بررسی مجوز"""
        cart = await self._get_cart(cart_id)
        if not cart:
            raise HTTPException(status_code=404, detail="Cart not found")

        if cart.user_id != user.id:
            raise HTTPException(status_code=403, detail="Not authorized")

        return cart

    async def _get_order(self, order_id: int) -> Optional[Order]:
        """دریافت سفارش"""
        return await self.db.get(Order, order_id)

    async def _get_order_with_permission(self, order_id: int, user: User, require_admin: bool = False) -> Order:
        """دریافت سفارش با بررسی مجوز"""
        order = await self._get_order(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        user_roles = [r.key for r in user.roles]

        if require_admin:
            if "ADMIN" not in user_roles:
                raise HTTPException(status_code=403, detail="Not authorized")
        else:
            # مشتری خودش یا ادمین
            if order.customer_id != user.id and "ADMIN" not in user_roles:
                raise HTTPException(status_code=403, detail="Not authorized")

        return order

    async def _get_return_request(self, return_id: int) -> ReturnRequest:
        """دریافت درخواست برگشت"""
        return_request = await self.db.get(ReturnRequest, return_id)
        if not return_request:
            raise HTTPException(status_code=404, detail="Return request not found")
        return return_request

    async def _add_cart_item(self, cart_id: int, item_data: CartItemCreate, user: User):
        """اضافه کردن آیتم به سبد (بدون commit)"""
        product = await self.db.get(Product, item_data.product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        cart_item = CartItem(
            cart_id=cart_id,
            product_id=item_data.product_id,
            quantity=item_data.quantity,
            unit_price=product.price,
            subtotal=product.price * item_data.quantity,
            charity_percentage=product.charity_percentage,
            charity_fixed_amount=product.charity_fixed_amount,
            charity_total=(
                    product.charity_fixed_amount * item_data.quantity +
                    (product.price * item_data.quantity * (product.charity_percentage / 100))
            ),
            donation_amount=item_data.donation_amount or 0.0
        )

        self.db.add(cart_item)

    async def _recalculate_cart(self, cart_id: int):
        """محاسبه مجدد سبد خرید"""
        # محاسبه مجموع‌ها
        cart = await self.db.get(Cart, cart_id)
        if not cart:
            return

        # محاسبه از آیتم‌ها
        items = await self.db.execute(
            select(CartItem).where(CartItem.cart_id == cart_id)
        )
        items = items.scalars().all()

        subtotal = 0
        charity_amount = 0
        donation_amount = 0

        for item in items:
            subtotal += item.subtotal
            charity_amount += item.charity_total
            donation_amount += item.donation_amount

        # محاسبه هزینه ارسال
        shipping_cost = self._calculate_shipping_cost(cart.shipping_cost, subtotal)

        # محاسبه مالیات
        tax_amount = subtotal * self.settings.tax_rate

        # محاسبه کل
        grand_total = subtotal + shipping_cost + tax_amount - cart.discount_amount

        # به‌روزرسانی سبد
        cart.subtotal = subtotal
        cart.shipping_cost = shipping_cost
        cart.tax_amount = tax_amount
        cart.charity_amount = charity_amount
        cart.donation_amount = donation_amount
        cart.grand_total = grand_total
        cart.updated_at = datetime.utcnow()

        self.db.add(cart)
        await self.db.commit()

    async def _validate_cart_inventory(self, cart: Cart):
        """بررسی موجودی محصولات سبد"""
        items = await self.db.execute(
            select(CartItem).where(CartItem.cart_id == cart.id)
        )

        for item in items.scalars().all():
            product = await self.db.get(Product, item.product_id)
            if product.stock_quantity < item.quantity:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient stock for {product.name}. Available: {product.stock_quantity}"
                )

    async def _create_order_items(self, order_id: int, cart_id: int):
        """ایجاد آیتم‌های سفارش از سبد"""
        cart_items = await self.db.execute(
            select(CartItem).where(CartItem.cart_id == cart_id)
        )

        for cart_item in cart_items.scalars().all():
            product = await self.db.get(Product, cart_item.product_id)

            order_item = OrderItem(
                order_id=order_id,
                product_id=cart_item.product_id,
                product_name=product.name,
                product_sku=product.sku,
                unit_price=cart_item.unit_price,
                quantity=cart_item.quantity,
                subtotal=cart_item.subtotal,
                charity_percentage=cart_item.charity_percentage,
                charity_fixed_amount=cart_item.charity_fixed_amount,
                charity_total=cart_item.charity_total
            )

            self.db.add(order_item)

    async def _update_inventory_from_cart(self, cart_id: int, reason: str, user_id: int):
        """کاهش موجودی از سبد"""
        cart_items = await self.db.execute(
            select(CartItem).where(CartItem.cart_id == cart_id)
        )

        for cart_item in cart_items.scalars().all():
            product = await self.db.get(Product, cart_item.product_id)

            old_quantity = product.stock_quantity
            new_quantity = old_quantity - cart_item.quantity

            product.stock_quantity = new_quantity

            # ثبت تاریخچه
            history = InventoryHistory(
                product_id=product.id,
                previous_quantity=old_quantity,
                new_quantity=new_quantity,
                adjustment=-cart_item.quantity,
                reason=reason,
                notes=f"Order from cart {cart_id}",
                created_by=user_id
            )

            self.db.add(product)
            self.db.add(history)

    async def _restore_inventory_from_order(self, order_id: int, reason: str, user_id: int):
        """بازگرداندن موجودی از سفارش"""
        order_items = await self.db.execute(
            select(OrderItem).where(OrderItem.order_id == order_id)
        )

        for order_item in order_items.scalars().all():
            product = await self.db.get(Product, order_item.product_id)

            if product:
                old_quantity = product.stock_quantity
                new_quantity = old_quantity + order_item.quantity

                product.stock_quantity = new_quantity

                # ثبت تاریخچه
                history = InventoryHistory(
                    product_id=product.id,
                    previous_quantity=old_quantity,
                    new_quantity=new_quantity,
                    adjustment=order_item.quantity,
                    reason=reason,
                    notes=f"Restore from order {order_id}",
                    created_by=user_id
                )

                self.db.add(product)
                self.db.add(history)

    async def _restore_inventory_from_return(self, return_request: ReturnRequest):
        """بازگرداندن موجودی از برگشت"""
        for item in return_request.items:
            product_id = item.get("product_id")
            quantity = item.get("quantity", 0)

            if product_id and quantity > 0:
                product = await self.db.get(Product, product_id)

                if product:
                    old_quantity = product.stock_quantity
                    new_quantity = old_quantity + quantity

                    product.stock_quantity = new_quantity

                    # ثبت تاریخچه
                    history = InventoryHistory(
                        product_id=product.id,
                        previous_quantity=old_quantity,
                        new_quantity=new_quantity,
                        adjustment=quantity,
                        reason="return",
                        notes=f"Restore from return request {return_request.id}",
                        created_by=return_request.processed_by
                    )

                    self.db.add(product)
                    self.db.add(history)

    async def _create_charity_donation(self, order: Order, user: User):
        """ایجاد کمک از مبلغ خیریه سفارش"""
        from models.donation import Donation

        if order.charity_amount > 0:
            donation = Donation(
                amount=order.charity_amount,
                currency=order.currency,
                payment_method="product_sale",
                status="completed",
                payment_status="paid",
                donor_id=user.id,
                charity_id=order.charity_id,
                need_id=order.need_id,
                tracking_code=self._generate_tracking_code(),
                receipt_number=self._generate_receipt_number(),
                completed_at=datetime.utcnow()
            )

            self.db.add(donation)

            # به‌روزرسانی مبلغ جمع‌آوری شده نیاز
            if order.need_id:
                need = await self.db.get(NeedAd, order.need_id)
                if need:
                    need.collected_amount = (need.collected_amount or 0) + order.charity_amount
                    self.db.add(need)

    async def _validate_coupon(self, code: str, cart: Cart, customer_id: Optional[int] = None) -> Optional[Coupon]:
        """اعتبارسنجی کوپن"""
        result = await self.db.execute(
            select(Coupon).where(
                and_(
                    Coupon.code == code.upper(),
                    Coupon.active == True,
                    Coupon.valid_from <= datetime.utcnow(),
                    or_(
                        Coupon.valid_until.is_(None),
                        Coupon.valid_until >= datetime.utcnow()
                    )
                )
            )
        )
        coupon = result.scalar_one_or_none()

        if not coupon:
            return None

        # بررسی محدودیت استفاده
        if coupon.usage_limit and coupon.usage_count >= coupon.usage_limit:
            return None

        # بررسی حداقل سفارش
        if coupon.min_order_amount and cart.subtotal < coupon.min_order_amount:
            return None

        # بررسی محدودیت محصول
        if coupon.product_ids:
            cart_items = await self.db.execute(
                select(CartItem).where(CartItem.cart_id == cart.id)
            )
            has_valid_product = False
            for item in cart_items.scalars().all():
                if item.product_id in coupon.product_ids:
                    has_valid_product = True
                    break
            if not has_valid_product:
                return None

        # بررسی محدودیت کاربر
        if coupon.user_ids and customer_id and customer_id not in coupon.user_ids:
            return None

        # بررسی محدودیت خیریه
        if coupon.charity_id and cart.charity_id != coupon.charity_id:
            return None

        return coupon

    async def _calculate_discount(self, cart: Cart, coupon: Coupon) -> float:
        """محاسبه تخفیف"""
        if coupon.discount_type == "percentage":
            discount = cart.subtotal * (coupon.discount_value / 100)
            if coupon.max_discount:
                discount = min(discount, coupon.max_discount)
        else:  # fixed
            discount = coupon.discount_value

        return round(discount, 2)

    async def _handle_status_change(self, order: Order, new_status: str, user: User) -> Order:
        """مدیریت تغییر وضعیت سفارش"""
        if new_status == "shipped" and order.status != "shipped":
            order.shipped_at = datetime.utcnow()
        elif new_status == "delivered" and order.status != "delivered":
            order.delivered_at = datetime.utcnow()

        return order

    async def _prepare_cart_data(self, cart: Cart) -> Dict[str, Any]:
        """آماده‌سازی داده‌های سبد خرید"""
        # گرفتن آیتم‌ها
        items = await self.db.execute(
            select(CartItem).where(CartItem.cart_id == cart.id)
        )

        cart_items = []
        for item in items.scalars().all():
            product = await self.db.get(Product, item.product_id)
            cart_items.append({
                "id": item.id,
                "product_id": item.product_id,
                "product_name": product.name if product else "Unknown",
                "product_price": item.unit_price,
                "quantity": item.quantity,
                "subtotal": item.subtotal,
                "charity_amount": item.charity_total,
                "donation_amount": item.donation_amount,
                "total": item.subtotal + item.donation_amount,
                "image_url": product.images[0] if product and product.images else None
            })

        # گرفتن اطلاعات مرتبط
        charity_name = None
        if cart.charity_id:
            charity = await self.db.get(Charity, cart.charity_id)
            charity_name = charity.name if charity else None

        need_title = None
        if cart.need_id:
            need = await self.db.get(NeedAd, cart.need_id)
            need_title = need.title if need else None

        return {
            "cart_id": cart.uuid,
            "user_id": cart.user_id,
            "items": cart_items,
            "item_count": len(cart_items),
            "subtotal": cart.subtotal,
            "total_charity": cart.charity_amount,
            "total_donation": cart.donation_amount,
            "shipping_cost": cart.shipping_cost,
            "tax_amount": cart.tax_amount,
            "discount_amount": cart.discount_amount,
            "grand_total": cart.grand_total,
            "currency": cart.currency,
            "status": cart.status,
            "charity_id": cart.charity_id,
            "charity_name": charity_name,
            "need_id": cart.need_id,
            "need_title": need_title,
            "created_at": cart.created_at,
            "updated_at": cart.updated_at,
            "expires_at": cart.expires_at
        }

    async def _prepare_order_data(self, order: Order, user: Optional[User]) -> Dict[str, Any]:
        """آماده‌سازی داده‌های سفارش"""
        # گرفتن آیتم‌ها
        items = await self.db.execute(
            select(OrderItem).where(OrderItem.order_id == order.id)
        )

        order_items = []
        for item in items.scalars().all():
            product = await self.db.get(Product, item.product_id)
            order_items.append({
                "id": item.id,
                "product_id": item.product_id,
                "product_name": item.product_name,
                "product_sku": item.product_sku,
                "unit_price": item.unit_price,
                "quantity": item.quantity,
                "subtotal": item.subtotal,
                "charity_percentage": item.charity_percentage,
                "charity_fixed_amount": item.charity_fixed_amount,
                "charity_total": item.charity_total,
                "image_url": product.images[0] if product and product.images else None
            })

        # گرفتن اطلاعات مرتبط
        charity_name = None
        if order.charity_id:
            charity = await self.db.get(Charity, order.charity_id)
            charity_name = charity.name if charity else None

        need_title = None
        if order.need_id:
            need = await self.db.get(NeedAd, order.need_id)
            need_title = need.title if need else None

        # تعیین سطح دسترسی
        user_roles = []
        if user:
            user_roles = [r.key for r in user.roles]

        can_view_details = "ADMIN" in user_roles or order.customer_id == user.id

        data = {
            "id": order.id,
            "uuid": order.uuid,
            "order_number": order.order_number,
            "status": order.status,
            "payment_status": order.payment_status,
            "subtotal": order.subtotal,
            "shipping_cost": order.shipping_cost,
            "tax_amount": order.tax_amount,
            "discount_amount": order.discount_amount,
            "charity_amount": order.charity_amount,
            "grand_total": order.grand_total,
            "currency": order.currency,
            "customer_id": order.customer_id,
            "customer_name": order.customer_name,
            "customer_email": order.customer_email,
            "shipping_method": order.shipping_method,
            "shipping_address": order.shipping_address,
            "shipping_city": order.shipping_city,
            "shipping_province": order.shipping_province,
            "shipping_postal_code": order.shipping_postal_code,
            "charity_id": order.charity_id,
            "charity_name": charity_name,
            "need_id": order.need_id,
            "need_title": need_title,
            "created_at": order.created_at,
            "updated_at": order.updated_at,
            "items": order_items
        }

        if can_view_details:
            data.update({
                "customer_phone": order.customer_phone,
                "shipping_tracking_code": order.shipping_tracking_code,
                "shipping_carrier": order.shipping_carrier,
                "shipping_notes": order.shipping_notes,
                "billing_address": order.billing_address,
                "billing_city": order.billing_city,
                "billing_province": order.billing_province,
                "payment_method": order.payment_method,
                "paid_at": order.paid_at,
                "shipped_at": order.shipped_at,
                "delivered_at": order.delivered_at,
                "cancelled_at": order.cancelled_at
            })

            if "ADMIN" in user_roles:
                data.update({
                    "transaction_id": order.transaction_id,
                    "payment_details": order.payment_details,
                    "internal_notes": order.internal_notes,
                    "customer_notes": order.customer_notes
                })

        return data

    async def _log_order_action(self, order_id: int, action: str, user_id: Optional[int], details: Dict[str, Any]):
        """ثبت لاگ برای عمل روی سفارش"""
        # در حالت واقعی، در AuditLog ذخیره می‌شود
        print(f"[Order Log] {action} - Order: {order_id}, User: {user_id}, Details: {details}")

    def _get_default_settings(self) -> ShopSettings:
        """تنظیمات پیش‌فرض فروشگاه"""
        return ShopSettings(
            currency="IRR",
            tax_rate=0.09,
            shipping_cost_standard=30000,
            shipping_cost_express=60000,
            shipping_cost_courier=15000,
            free_shipping_threshold=500000,
            low_stock_threshold=10,
            cart_expiry_minutes=1440,
            order_confirmation_email=True,
            order_shipped_email=True,
            order_delivered_email=True,
            return_policy_days=7
        )

    def _calculate_shipping_cost(self, current_cost: float, subtotal: float) -> float:
        """محاسبه هزینه ارسال"""
        if self.settings.free_shipping_threshold and subtotal >= self.settings.free_shipping_threshold:
            return 0
        return current_cost

    def _generate_order_number(self) -> str:
        """تولید شماره سفارش"""
        timestamp = int(datetime.utcnow().timestamp())
        random_part = uuid.uuid4().hex[:6].upper()
        return f"ORD-{timestamp}-{random_part}"

    def _generate_tracking_code(self) -> str:
        """تولید کد رهگیری"""
        timestamp = int(datetime.utcnow().timestamp())
        random_part = uuid.uuid4().hex[:8].upper()
        return f"TRK-{timestamp}-{random_part}"

    def _generate_receipt_number(self) -> str:
        """تولید شماره رسید"""
        timestamp = int(datetime.utcnow().timestamp())
        random_part = uuid.uuid4().hex[:6].upper()
        return f"REC-{timestamp}-{random_part}"