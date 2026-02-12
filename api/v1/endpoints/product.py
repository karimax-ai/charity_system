from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from typing import List, Optional

from core.database import get_db
from core.permissions import get_current_active_user, require_roles
from models.user import User
from models.product import Product
from models.shop import Shop
from schemas.product import ProductCreate, ProductRead, ProductUpdate, ProductStatusUpdate


router = APIRouter()


# -------------------------
# 1️⃣ ایجاد محصول
# -------------------------
@router.post("/", response_model=ProductRead)
async def create_product(
    product_data: ProductCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    # فقط فروشنده یا مدیر فروشگاه اجازه دارند
    if "VENDOR" not in [role.key for role in current_user.roles] and "MANAGER" not in [role.key for role in current_user.roles]:
        raise HTTPException(status_code=403, detail="Not authorized")

    # اگر shop_id داده شده، بررسی مالکیت
    if product_data.shop_id:
        result = await db.execute(select(Shop).where(Shop.id == product_data.shop_id))
        shop = result.scalar_one_or_none()
        if not shop:
            raise HTTPException(status_code=404, detail="Shop not found")
        # فقط مدیر فروشگاه می‌تواند محصول اضافه کند
        if shop.manager_id != current_user.id and "ADMIN" not in [role.key for role in current_user.roles]:
            raise HTTPException(status_code=403, detail="Not authorized for this shop")
    else:
        shop = None

    product = Product(
        name=product_data.name,
        description=product_data.description,
        price=product_data.price,
        currency=product_data.currency,
        stock_quantity=product_data.stock_quantity,
        max_order_quantity=product_data.max_order_quantity,
        charity_percentage=product_data.charity_percentage,
        charity_fixed_amount=product_data.charity_fixed_amount,
        category=product_data.category,
        images=product_data.images or [],
        vendor_id=current_user.id,
        shop_id=shop.id if shop else None,
        status="draft",
    )

    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


# -------------------------
# 2️⃣ ویرایش محصول
# -------------------------
@router.patch("/{product_id}", response_model=ProductRead)
async def update_product(
    product_id: int,
    product_data: ProductUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # فقط فروشنده یا مدیر فروشگاه اجازه دارند
    if product.vendor_id != current_user.id:
        if product.shop and product.shop.manager_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized")

    for key, value in product_data.dict(exclude_unset=True).items():
        setattr(product, key, value)

    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


# -------------------------
# 3️⃣ حذف محصول
# -------------------------
@router.delete("/{product_id}")
async def delete_product(
    product_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if product.vendor_id != current_user.id:
        if product.shop and product.shop.manager_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized")

    await db.delete(product)
    await db.commit()
    return {"detail": "Product deleted successfully"}


# -------------------------
# 4️⃣ تغییر وضعیت محصول
# -------------------------
@router.patch("/{product_id}/status", response_model=ProductRead)
async def update_product_status(
    product_id: int,
    status_data: ProductStatusUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if product.vendor_id != current_user.id:
        if product.shop and product.shop.manager_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized")

    product.status = status_data.status
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


# -------------------------
# 5️⃣ لیست محصولات با فیلتر
# -------------------------
@router.get("/", response_model=List[ProductRead])
async def list_products(
    vendor_id: Optional[int] = None,
    shop_id: Optional[int] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    query = select(Product)
    if vendor_id:
        query = query.where(Product.vendor_id == vendor_id)
    if shop_id:
        query = query.where(Product.shop_id == shop_id)
    if status:
        query = query.where(Product.status == status)

    result = await db.execute(query)
    products = result.scalars().all()
    return products
