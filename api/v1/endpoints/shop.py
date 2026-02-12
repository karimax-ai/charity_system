from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from core.database import get_db
from core.permissions import get_current_active_user, require_roles
from models.user import User
from models.shop import Shop
from schemas.shop import ShopCreate, ShopRead, VendorAdd, VendorRead
from services.auth_service import AuthService

router = APIRouter()


# 1️⃣ ایجاد فروشگاه + ثبت فروشنده اولیه
@router.post("/", response_model=ShopRead)
async def create_shop(
    shop_data: ShopCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    # فقط ADMIN یا MANAGER
    if "ADMIN" not in [role.key for role in current_user.roles] and \
       "MANAGER" not in [role.key for role in current_user.roles]:
        raise HTTPException(status_code=403, detail="Not authorized")

    # بررسی ایمیل فروشگاه/کاربر
    result = await db.execute(select(User).where(User.email == shop_data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    # ثبت فروشنده اولیه
    service = AuthService(db)
    vendor_user = await service.register_user(
        email=shop_data.email,
        password="temporary123",
        username=shop_data.name,
        role_key="VENDOR"
    )

    # ثبت فروشگاه
    shop = Shop(
        name=shop_data.name,
        description=shop_data.description,
        email=shop_data.email,
        phone=shop_data.phone,
        address=shop_data.address,
        website=shop_data.website,
        shop_type=shop_data.shop_type,
        manager_id=current_user.id
    )
    shop.vendors.append(vendor_user)

    db.add(shop)
    await db.commit()
    await db.refresh(shop)
    return shop


# 2️⃣ اضافه کردن فروشنده جدید به فروشگاه
@router.post("/{shop_id}/vendors", response_model=VendorRead)
async def add_vendor_to_shop(
    shop_id: int,
    vendor_data: VendorAdd,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    shop_result = await db.execute(select(Shop).where(Shop.id == shop_id))
    shop = shop_result.scalar_one_or_none()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    # فقط ADMIN یا MANAGER یا مدیر این فروشگاه
    if "ADMIN" not in [role.key for role in current_user.roles] and \
       "MANAGER" not in [role.key for role in current_user.roles] and \
       shop.manager_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # بررسی ایمیل
    result = await db.execute(select(User).where(User.email == vendor_data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    # ثبت فروشنده
    service = AuthService(db)
    vendor_user = await service.register_user(
        email=vendor_data.email,
        password=vendor_data.temporary_password,
        role_key="VENDOR"
    )

    shop.vendors.append(vendor_user)
    db.add(shop)
    await db.commit()
    await db.refresh(vendor_user)
    return vendor_user


# 3️⃣ تایید فروشگاه
@router.patch("/{shop_id}/verify", response_model=ShopRead)
async def verify_shop(
    shop_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    shop_result = await db.execute(select(Shop).where(Shop.id == shop_id))
    shop = shop_result.scalar_one_or_none()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    # فقط ADMIN یا MANAGER
    if "ADMIN" not in [role.key for role in current_user.roles] and \
       "MANAGER" not in [role.key for role in current_user.roles]:
        raise HTTPException(status_code=403, detail="Not authorized")

    shop.verified = True
    # همه فروشنده‌های این فروشگاه هم verified
    for vendor in shop.vendors:
        vendor.is_verified = True

    db.add(shop)
    await db.commit()
    await db.refresh(shop)
    return shop


# 4️⃣ مشاهده لیست فروشگاه‌ها
@router.get("/", response_model=List[ShopRead])
async def list_shops(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Shop))
    shops = result.scalars().all()
    return shops


# 5️⃣ مشاهده فروشندگان یک فروشگاه
@router.get("/{shop_id}/vendors", response_model=List[VendorRead])
async def list_shop_vendors(shop_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Shop).where(Shop.id == shop_id))
    shop = result.scalar_one_or_none()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    return shop.vendors
