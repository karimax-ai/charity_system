# app/models/product.py
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, func, ForeignKey, Float, Enum, JSON
from sqlalchemy.orm import relationship
import uuid
from models.base import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))

    # اطلاعات محصول
    name = Column(String(200), nullable=False)
    description = Column(Text)
    sku = Column(String(100))  # کد محصول
    price = Column(Float, nullable=False)
    currency = Column(String(3), default="IRR")

    # موجودی
    stock_quantity = Column(Integer, default=0)
    max_order_quantity = Column(Integer, default=10)

    # اختصاص به خیریه
    charity_percentage = Column(Float, default=0.0)  # درصدی که به خیریه می‌رود
    charity_fixed_amount = Column(Float, default=0.0)  # مبلغ ثابت به خیریه

    # وضعیت
    status = Column(
        Enum("draft", "pending", "approved", "active", "sold_out", "archived", name="product_status"),
        default="draft"
    )

    # دسته‌بندی
    category = Column(String(100))

    # تصاویر
    images = Column(JSON, default=list)

    # Foreign Keys
    vendor_id = Column(Integer, ForeignKey("users.id"))  # فروشنده
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=True)  # فروشگاه (اگر تیم است)
    charity_id = Column(Integer, ForeignKey("charities.id"), nullable=True)
    need_id = Column(Integer, ForeignKey("need_ads.id"), nullable=True)  # اختصاص به نیاز خاص

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    vendor = relationship("User", foreign_keys=[vendor_id])
    shop = relationship("Shop", back_populates="products")
    charity = relationship("Charity", back_populates="products")
    need = relationship("NeedAd", back_populates="products")
    donations = relationship("Donation", back_populates="product")
    orders = relationship("Order", back_populates="product")
    cart_items = relationship("CartItem", back_populates="product")
    order_items = relationship("OrderItem", back_populates="product")
    inventory_history = relationship("InventoryHistory", back_populates="product")