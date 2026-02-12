# app/schemas/product.py
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class ProductStatus(str, Enum):
    draft = "draft"
    pending = "pending"
    approved = "approved"
    active = "active"
    sold_out = "sold_out"
    archived = "archived"


class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    currency: Optional[str] = "IRR"
    stock_quantity: Optional[int] = 0
    max_order_quantity: Optional[int] = 10
    charity_percentage: Optional[float] = 0.0
    charity_fixed_amount: Optional[float] = 0.0
    category: Optional[str] = None
    images: Optional[List[str]] = []

    shop_id: Optional[int] = None  # اگر محصول به فروشگاه تعلق دارد
    charity_id: Optional[int] = None
    need_id: Optional[int] = None


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    stock_quantity: Optional[int] = None
    max_order_quantity: Optional[int] = None
    charity_percentage: Optional[float] = None
    charity_fixed_amount: Optional[float] = None
    category: Optional[str] = None
    images: Optional[List[str]] = None


class ProductStatusUpdate(BaseModel):
    status: ProductStatus


class ProductRead(ProductBase):
    id: int
    uuid: str
    vendor_id: int
    status: ProductStatus

    class Config:
        orm_mode = True
