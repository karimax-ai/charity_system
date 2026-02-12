# app/core/initial_data.py
import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import AsyncSessionLocal
from models.role import Role
from models.permission import Permission
from models.association_tables import role_permissions

# ========== نقش‌های سیستم ==========
SYSTEM_ROLES = {
    "SUPER_ADMIN": {
        "title": "Super Admin",
        "description": "Full system access",
        "is_system": True,
        "permissions": "*"  # همه دسترسی‌ها
    },
    "CHARITY_MANAGER": {
        "title": "Charity Manager",
        "description": "Manages all charities and their activities",
        "is_system": True,
        "permissions": [
            "charity.*",
            "need.approve",
            "user.read",
            "report.view"
        ]
    },
    "CHARITY": {
        "title": "Charity Organization",
        "description": "Charity organization account",
        "is_system": True,
        "permissions": [
            "need.create",
            "need.update",
            "need.delete",
            "need.view_private",
            "donation.view"
        ]
    },
    "DONOR": {
        "title": "Donor",
        "description": "Can donate to needs",
        "is_system": True,
        "permissions": [
            "donation.create",
            "donation.view",
            "need.read"
        ]
    },
    "NEEDY": {
        "title": "Needy Person",
        "description": "Can request help",
        "is_system": True,
        "permissions": [
            "need.create",
            "need.update",
            "need.delete"
        ]
    },
    "VENDOR": {
        "title": "Vendor",
        "description": "Can sell products for charity",
        "is_system": True,
        "permissions": [
            "product.create",
            "product.sell"
        ]
    },
    "SHOP_MANAGER": {
        "title": "Shop Manager",
        "description": "Manages vendors and products",
        "is_system": True,
        "permissions": [
            "product.*",
            "vendor.manage"
        ]
    },
    "VOLUNTEER": {
        "title": "Volunteer",
        "description": "Helps manage needs without full access",
        "is_system": True,
        "permissions": [
            "need.read",
            "need.update_status"
        ]
    },
    "USER": {
        "title": "Regular User",
        "description": "Can view public content",
        "is_system": True,
        "is_default": True,  # نقش پیش‌فرض برای ثبت‌نام
        "permissions": [
            "need.read",
            "charity.read"
        ]
    },
    "GUEST": {
        "title": "Guest",
        "description": "Unauthenticated user - view only",
        "is_system": True,
        "permissions": [
            "need.read_public",
            "charity.read_public"
        ]
    }
}

# ========== دسترسی‌های سیستم ==========
SYSTEM_PERMISSIONS = {
    # Charity
    "charity.create": "Create new charity",
    "charity.read": "View charity details",
    "charity.read_public": "View public charity info",
    "charity.update": "Update charity",
    "charity.delete": "Delete charity",
    "charity.*": "All charity operations",

    # Needs
    "need.create": "Create need advertisement",
    "need.read": "View need details",
    "need.read_public": "View public needs",
    "need.update": "Update need",
    "need.delete": "Delete need",
    "need.approve": "Approve need",
    "need.view_private": "View private need",
    "need.update_status": "Update need status",
    "need.*": "All need operations",

    # Donations
    "donation.create": "Create donation",
    "donation.view": "View donations",
    "donation.*": "All donation operations",

    # Users
    "user.read": "Read users",
    "user.create": "Create user",
    "user.update": "Update user",
    "user.delete": "Delete user",
    "user.*": "All user operations",

    # Products
    "product.create": "Create product",
    "product.sell": "Sell product",
    "product.*": "All product operations",

    # Vendors
    "vendor.manage": "Manage vendors",

    # Reports
    "report.view": "View reports",
    "report.*": "All report operations",
}


async def init_system_roles_and_permissions(db: AsyncSession):
    """ایجاد نقش‌ها و دسترسی‌های پیش‌فرض سیستم"""

    # 1. ایجاد دسترسی‌ها
    permissions = {}
    for code, description in SYSTEM_PERMISSIONS.items():
        result = await db.execute(
            select(Permission).where(Permission.code == code)
        )
        perm = result.scalar_one_or_none()
        if not perm:
            perm = Permission(
                code=code,
                title=description.split(":")[0] if ":" in description else code,
                description=description
            )
            db.add(perm)
            await db.flush()
        permissions[code] = perm

    # 2. ایجاد نقش‌ها
    for key, role_data in SYSTEM_ROLES.items():
        result = await db.execute(
            select(Role).where(Role.key == key)
        )
        role = result.scalar_one_or_none()
        if not role:
            role = Role(
                key=key,
                title=role_data["title"],
                description=role_data["description"],
                is_system=role_data["is_system"]
            )
            db.add(role)
            await db.flush()

        # 3. افزودن دسترسی‌ها به نقش
        role.permissions = []
        if role_data["permissions"] == "*":
            # همه دسترسی‌ها
            role.permissions = list(permissions.values())
        else:
            # دسترسی‌های مشخص
            for perm_code in role_data["permissions"]:
                if perm_code.endswith(".*"):
                    # دسترسی گروهی (مثلاً charity.*)
                    prefix = perm_code[:-2]
                    for p_code, p_obj in permissions.items():
                        if p_code.startswith(prefix):
                            role.permissions.append(p_obj)
                elif perm_code in permissions:
                    role.permissions.append(permissions[perm_code])

        await db.flush()

    await db.commit()
    print("✅ System roles and permissions initialized")


async def init_db():
    async with AsyncSessionLocal() as db:
        await init_system_roles_and_permissions(db)


if __name__ == "__main__":
    asyncio.run(init_db())