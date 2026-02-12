# app/models/order_models.py
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, func, ForeignKey, Float, Enum, JSON
from sqlalchemy.orm import relationship
import uuid
from models.base import Base


class Cart(Base):
    """سبد خرید"""
    __tablename__ = "carts"

    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))

    # اطلاعات سبد
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(
        Enum("active", "abandoned", "converted", "expired", name="cart_status"),
        default="active"
    )

    # اطلاعات مالی
    subtotal = Column(Float, default=0.0)
    shipping_cost = Column(Float, default=0.0)
    tax_amount = Column(Float, default=0.0)
    discount_amount = Column(Float, default=0.0)
    charity_amount = Column(Float, default=0.0)  # از محصولات
    donation_amount = Column(Float, default=0.0)  # کمک مستقیم
    grand_total = Column(Float, default=0.0)
    currency = Column(String(3), default="IRR")

    # اطلاعات مرتبط
    charity_id = Column(Integer, ForeignKey("charities.id"), nullable=True)
    need_id = Column(Integer, ForeignKey("need_ads.id"), nullable=True)
    coupon_id = Column(Integer, ForeignKey("coupons.id"), nullable=True)

    # زمان‌ها
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    expires_at = Column(DateTime(timezone=True))

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    charity = relationship("Charity")
    need = relationship("NeedAd")
    coupon = relationship("Coupon")
    items = relationship("CartItem", back_populates="cart", cascade="all, delete-orphan")


class CartItem(Base):
    """آیتم سبد خرید"""
    __tablename__ = "cart_items"

    id = Column(Integer, primary_key=True)
    cart_id = Column(Integer, ForeignKey("carts.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)

    # اطلاعات آیتم
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Float, nullable=False)
    subtotal = Column(Float, nullable=False)
    charity_percentage = Column(Float, default=0.0)
    charity_fixed_amount = Column(Float, default=0.0)
    charity_total = Column(Float, default=0.0)
    donation_amount = Column(Float, default=0.0)  # کمک اضافی برای این آیتم

    # زمان
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    cart = relationship("Cart", back_populates="items")
    product = relationship("Product")


class OrderItem(Base):
    """آیتم سفارش (تاریخچه)"""
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)

    # اطلاعات آیتم (در زمان سفارش)
    product_name = Column(String(200), nullable=False)
    product_sku = Column(String(100))
    unit_price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    subtotal = Column(Float, nullable=False)

    # اطلاعات خیریه (در زمان سفارش)
    charity_percentage = Column(Float, default=0.0)
    charity_fixed_amount = Column(Float, default=0.0)
    charity_total = Column(Float, default=0.0)

    # Relationships
    order = relationship("Order", back_populates="items")
    product = relationship("Product")


class Order(Base):
    """سفارش"""
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    order_number = Column(String(50), unique=True, nullable=False)

    # وضعیت
    status = Column(
        Enum("pending", "confirmed", "processing", "shipped", "delivered", "cancelled",
             "refunded", name="order_status"),
        default="pending"
    )

    payment_status = Column(
        Enum("pending", "paid", "failed", "refunded", "partially_refunded", name="payment_status"),
        default="pending"
    )

    # اطلاعات مالی
    subtotal = Column(Float, nullable=False)
    shipping_cost = Column(Float, default=0.0)
    tax_amount = Column(Float, default=0.0)
    discount_amount = Column(Float, default=0.0)
    charity_amount = Column(Float, default=0.0)
    grand_total = Column(Float, nullable=False)
    currency = Column(String(3), default="IRR")

    # اطلاعات مشتری
    customer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    customer_name = Column(String(200), nullable=False)
    customer_email = Column(String(255), nullable=False)
    customer_phone = Column(String(20))

    # اطلاعات ارسال
    shipping_method = Column(
        Enum("standard", "express", "courier", "store_pickup", name="shipping_method"),
        default="standard"
    )
    shipping_address = Column(Text, nullable=False)
    shipping_city = Column(String(100), nullable=False)
    shipping_province = Column(String(100), nullable=False)
    shipping_postal_code = Column(String(20))
    shipping_tracking_code = Column(String(100))
    shipping_carrier = Column(String(50))
    shipping_notes = Column(Text)

    # اطلاعات صورتحساب
    billing_address = Column(Text)
    billing_city = Column(String(100))
    billing_province = Column(String(100))

    # اطلاعات پرداخت
    payment_method = Column(String(50))
    transaction_id = Column(String(255))
    payment_details = Column(JSON, default=dict)

    # اطلاعات مرتبط
    charity_id = Column(Integer, ForeignKey("charities.id"), nullable=True)
    need_id = Column(Integer, ForeignKey("need_ads.id"), nullable=True)
    coupon_id = Column(Integer, ForeignKey("coupons.id"), nullable=True)

    # یادداشت‌ها
    customer_notes = Column(Text)
    internal_notes = Column(Text)

    # زمان‌ها
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    paid_at = Column(DateTime(timezone=True))
    shipped_at = Column(DateTime(timezone=True))
    delivered_at = Column(DateTime(timezone=True))
    cancelled_at = Column(DateTime(timezone=True))

    # Relationships
    customer = relationship("User", foreign_keys=[customer_id])
    charity = relationship("Charity")
    need = relationship("NeedAd")
    coupon = relationship("Coupon")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    returns = relationship("ReturnRequest", back_populates="order", cascade="all, delete-orphan")


class InventoryHistory(Base):
    """تاریخچه موجودی"""
    __tablename__ = "inventory_history"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)

    # تغییرات
    previous_quantity = Column(Integer, nullable=False)
    new_quantity = Column(Integer, nullable=False)
    adjustment = Column(Integer, nullable=False)  # + برای افزایش، - برای کاهش
    reason = Column(String(100), nullable=False)  # order, return, adjustment, etc.
    notes = Column(Text)

    # ثبت کننده
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # زمان
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    product = relationship("Product")
    creator = relationship("User", foreign_keys=[created_by])


class ReturnRequest(Base):
    """درخواست برگشت کالا"""
    __tablename__ = "return_requests"

    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))

    # اطلاعات سفارش
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # وضعیت
    status = Column(
        Enum("pending", "approved", "rejected", "processed", name="return_status"),
        default="pending"
    )

    # اطلاعات برگشت
    items = Column(JSON, nullable=False)  # لیست آیتم‌های برگشتی
    reason = Column(String(200), nullable=False)
    description = Column(Text)

    # اطلاعات بازپرداخت
    refund_amount = Column(Float)
    refund_method = Column(String(50))  # refund, exchange, credit
    refund_transaction_id = Column(String(255))

    # مدیریت
    admin_notes = Column(Text)
    processed_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # زمان‌ها
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    processed_at = Column(DateTime(timezone=True))

    # Relationships
    order = relationship("Order", back_populates="returns")
    customer = relationship("User", foreign_keys=[customer_id])
    processor = relationship("User", foreign_keys=[processed_by])


class Coupon(Base):
    """کد تخفیف"""
    __tablename__ = "coupons"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False)

    # نوع تخفیف
    discount_type = Column(
        Enum("percentage", "fixed", name="discount_type"),
        default="percentage"
    )
    discount_value = Column(Float, nullable=False)

    # محدودیت‌ها
    min_order_amount = Column(Float)
    max_discount = Column(Float)
    usage_limit = Column(Integer)  # حداکثر تعداد استفاده
    usage_count = Column(Integer, default=0)

    # زمان اعتبار
    valid_from = Column(DateTime(timezone=True), nullable=False)
    valid_until = Column(DateTime(timezone=True))

    # محدودیت‌های دیگر
    charity_id = Column(Integer, ForeignKey("charities.id"), nullable=True)
    product_ids = Column(JSON, default=list)  # لیست ID محصولات مجاز
    user_ids = Column(JSON, default=list)  # لیست ID کاربران مجاز

    # فعال/غیرفعال
    active = Column(Boolean, default=True)

    # زمان
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    charity = relationship("Charity")
    orders = relationship("Order", back_populates="coupon")


# اضافه کردن رابطه به مدل‌های موجود
# در models/product.py اضافه کن:
"""
class Product(Base):
    # ... فیلدهای موجود ...

    # Relationships جدید
    cart_items = relationship("CartItem", back_populates="product")
    order_items = relationship("OrderItem", back_populates="product")
    inventory_history = relationship("InventoryHistory", back_populates="product")
"""