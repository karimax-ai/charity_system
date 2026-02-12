from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException
from models.product import Product
from schemas.product import ProductCreate, ProductUpdate

class ProductService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_product(self, product_data: ProductCreate, vendor_id: int):
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
            vendor_id=vendor_id,
            shop_id=product_data.shop_id,
            status="draft"
        )
        self.db.add(product)
        await self.db.commit()
        await self.db.refresh(product)
        return product

    async def update_product(self, product_id: int, update_data: ProductUpdate):
        result = await self.db.execute(select(Product).where(Product.id == product_id))
        product = result.scalar_one_or_none()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        for key, value in update_data.dict(exclude_unset=True).items():
            setattr(product, key, value)
        self.db.add(product)
        await self.db.commit()
        await self.db.refresh(product)
        return product
