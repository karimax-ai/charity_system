# scripts/seed_roles_permissions.py
import asyncio
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import hashlib

from core.database import AsyncSessionLocal
from models.permission import Permission
from models.role import Role
from models.user import User

# ۱️⃣ نقش‌ها
ROLES = [
    {"key": "super_admin", "title": "ادمین اصلی", "description": "دسترسی کامل سیستم", "is_system": True},
    {"key": "charity_admin", "title": "مدیر خیریه‌ها", "description": "مدیریت خیریه‌ها و تأیید آگهی‌ها",
     "is_system": True},
    {"key": "charity", "title": "خیریه", "description": "مدیریت آگهی‌ها و خیرین خودش", "is_system": True},
    {"key": "donor", "title": "خیر کمک‌کننده", "description": "ثبت و پیگیری کمک‌ها", "is_system": True},
    {"key": "needy", "title": "نیازمند", "description": "ارسال نیاز و پیگیری تأیید", "is_system": True},
    {"key": "user", "title": "کاربر عادی", "description": "کاربر معمولی", "is_system": True},
    {"key": "seller", "title": "فروشنده", "description": "مدیریت محصولات و درصد خیریه", "is_system": True},
    {"key": "store_manager", "title": "مدیر فروشگاه", "description": "نظارت بر فروشنده‌ها و محصولات",
     "is_system": True},
    {"key": "volunteer", "title": "داوطلب", "description": "کمک به مدیریت آگهی‌ها", "is_system": True},
]

# ۲️⃣ Permissionها
PERMISSIONS = [
    "users:create", "users:read", "users:update", "users:delete",
    "charities:create", "charities:read", "charities:update", "charities:delete",
    "needs:create", "needs:read", "needs:update", "needs:approve", "needs:delete",
    "donations:create", "donations:read",
    "payments:verify",
    "reports:view",
    "products:create", "products:update", "products:read", "products:delete",
]

# ۳️⃣ Mapping نقش‌ها و Permissionها
ROLE_PERMISSIONS = {
    "super_admin": PERMISSIONS,
    "charity_admin": ["charities:read", "charities:update", "needs:approve", "needs:read", "donations:read",
                      "reports:view"],
    "charity": ["needs:create", "needs:read", "donations:read", "products:read", "products:update"],
    "donor": ["needs:read", "donations:create", "donations:read", "products:read"],
    "needy": ["needs:create", "needs:read"],
    "user": ["needs:read", "products:read"],
    "seller": ["products:create", "products:update", "products:read"],
    "store_manager": ["products:read", "products:update"],
    "volunteer": ["needs:read", "needs:approve"],
}


# ساده‌ترین هش - فقط برای development
def simple_hash(password: str) -> str:
    """Hash ساده با SHA256 - فقط برای محیط توسعه"""
    return hashlib.sha256(password.encode()).hexdigest()


async def seed():
    async with AsyncSessionLocal() as session:
        # 🔹 Seed Permissions
        print("🔹 در حال ایجاد permissions...")
        for code in PERMISSIONS:
            result = await session.execute(select(Permission).where(Permission.code == code))
            perm = result.scalar_one_or_none()
            if not perm:
                perm = Permission(code=code, title=code)
                session.add(perm)
                print(f"  ایجاد permission: {code}")
        await session.commit()
        print("✅ Permissions ایجاد شدند!")

        # 🔹 Seed Roles
        print("\n🔹 در حال ایجاد نقش‌ها...")
        for r in ROLES:
            result = await session.execute(select(Role).where(Role.key == r["key"]))
            role = result.scalar_one_or_none()
            if not role:
                role = Role(**r)
                session.add(role)
                print(f"  ایجاد نقش: {r['key']} - {r['title']}")
        await session.commit()
        print("✅ نقش‌ها ایجاد شدند!")

        # 🔹 Assign Permissions to Roles
        print("\n🔹 در حال تخصیص permissions به نقش‌ها...")
        for role_key, perms in ROLE_PERMISSIONS.items():
            result = await session.execute(
                select(Role)
                .options(selectinload(Role.permissions))
                .where(Role.key == role_key)
            )
            role = result.unique().scalar_one()

            for code in perms:
                perm_result = await session.execute(select(Permission).where(Permission.code == code))
                perm = perm_result.scalar_one()
                if perm not in role.permissions:
                    role.permissions.append(perm)
                    print(f"  اضافه کردن {code} به {role_key}")

            session.add(role)

        await session.commit()
        print("✅ تخصیص permissions انجام شد!")

        # 🔹 Seed Super Admin
        print("\n🔹 در حال ایجاد ادمین اصلی...")
        result = await session.execute(select(User).where(User.email == "admin@example.com"))
        super_admin = result.scalar_one_or_none()

        if not super_admin:
            role_result = await session.execute(select(Role).where(Role.key == "super_admin"))
            super_admin_role = role_result.scalar_one()

            # رمز ساده - فقط برای development
            password = "admin123"
            hashed_password = simple_hash(password)

            super_admin = User(
                email="admin@example.com",
                username="superadmin",
                hashed_password=hashed_password,
                role=super_admin_role,
                is_active=True,
                is_verified=True
            )
            session.add(super_admin)
            print(f"✅ ادمین اصلی ایجاد شد!")
            print(f"  ایمیل: admin@example.com")
            print(f"  رمز عبور: {password}")
        else:
            print("⚠️ ادمین اصلی از قبل وجود دارد")

        await session.commit()

        print("\n" + "=" * 50)
        print("✅ عملیات seeding با موفقیت انجام شد!")
        print("=" * 50)


if __name__ == "__main__":
    asyncio.run(seed())