from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException
from models.shop import Shop
from models.user import User
from schemas.shop import ShopCreate

class ShopService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_shop(self, shop_data: ShopCreate, manager: User):
        shop = Shop(
            name=shop_data.name,
            description=shop_data.description,
            email=shop_data.email,
            phone=shop_data.phone,
            address=shop_data.address,
            website=shop_data.website,
            shop_type=shop_data.shop_type,
            manager_id=manager.id
        )
        self.db.add(shop)
        await self.db.commit()
        await self.db.refresh(shop)
        return shop

    async def verify_shop(self, shop_id: int):
        result = await self.db.execute(select(Shop).where(Shop.id == shop_id))
        shop = result.scalar_one_or_none()
        if not shop:
            raise HTTPException(status_code=404, detail="Shop not found")

        shop.verified = True
        for vendor in shop.vendors:
            vendor.is_verified = True

        self.db.add(shop)
        await self.db.commit()
        await self.db.refresh(shop)
        return shop
