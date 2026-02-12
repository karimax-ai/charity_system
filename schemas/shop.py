from pydantic import BaseModel, EmailStr
from typing import Optional, List

# برای ایجاد فروشگاه
class ShopCreate(BaseModel):
    name: str
    description: Optional[str] = None
    email: EmailStr
    phone: Optional[str] = None
    address: Optional[str] = None
    website: Optional[str] = None
    shop_type: Optional[str] = "individual"  # individual / company / charity_shop


# برای اضافه کردن فروشنده به فروشگاه
class VendorAdd(BaseModel):
    email: EmailStr
    temporary_password: Optional[str] = "temporary123"


# پاسخ برای فروشگاه و فروشنده
class VendorRead(BaseModel):
    id: int
    email: EmailStr
    username: Optional[str]
    is_verified: bool

    class Config:
        orm_mode = True


class ShopRead(BaseModel):
    id: int
    uuid: str
    name: str
    description: Optional[str]
    email: EmailStr
    phone: Optional[str]
    address: Optional[str]
    website: Optional[str]
    shop_type: str
    verified: bool
    active: bool
    manager_id: int
    vendors: List[VendorRead] = []

    class Config:
        orm_mode = True
