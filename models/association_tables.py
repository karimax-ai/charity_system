# app/models/association_tables.py
from sqlalchemy import Table, Column, ForeignKey, Float, DateTime, func, Integer
from models.base import Base

# جدول‌های ارتباطی اصلی
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", ForeignKey("users.id"), primary_key=True),
    Column("role_id", ForeignKey("roles.id"), primary_key=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", ForeignKey("roles.id"), primary_key=True),
    Column("permission_id", ForeignKey("permissions.id"), primary_key=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

# جدول ارتباطی فروشگاه‌ها و فروشندگان
shop_vendors = Table(
    "shop_vendors",
    Base.metadata,
    Column("shop_id", Integer, ForeignKey("shops.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)

# جدول ارتباطی تعهدات خیرین
donor_commitments = Table(
    "donor_commitments",
    Base.metadata,
    Column("donor_id", ForeignKey("users.id"), primary_key=True),
    Column("need_id", ForeignKey("need_ads.id"), primary_key=True),
    Column("committed_amount", Float, default=0.0),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

# جدول ارتباطی دنبال‌کنندگان خیریه
charity_followers = Table(
    "charity_followers",
    Base.metadata,
    Column("charity_id", ForeignKey("charities.id"), primary_key=True),
    Column("user_id", ForeignKey("users.id"), primary_key=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

product_need_association = Table(
    "product_need_association",
    Base.metadata,
    Column("product_id", Integer, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
    Column("need_id", Integer, ForeignKey("need_ads.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("donation_amount", Float, default=0.0),  # مبلغ کمک از فروش این محصول
    Column("charity_percentage", Float, default=0.0),  # درصد اختصاص یافته
)
