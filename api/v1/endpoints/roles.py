from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from core.database import get_db
from core.permissions import require_permission, require_roles
from models.role import Role
from models.permission import Permission
from models.user import User
from schemas.roles import RoleCreate, RoleUpdate, RoleSchema
from schemas.user import MessageResponse

router = APIRouter()


@router.get("/", response_model=List[RoleSchema])
async def get_roles(
        skip: int = 0,
        limit: int = 100,
        db: AsyncSession = Depends(get_db),
        _=Depends(require_permission("user.read"))
):
    """دریافت لیست نقش‌ها (فقط ادمین)"""
    result = await db.execute(
        select(Role).offset(skip).limit(limit)
    )
    roles = result.scalars().all()
    return roles


@router.post("/", response_model=RoleSchema)
async def create_role(
        role_data: RoleCreate,
        db: AsyncSession = Depends(get_db),
        _=Depends(require_permission("user.create"))
):
    """ایجاد نقش جدید (فقط ادمین)"""
    # بررسی تکراری نبودن
    result = await db.execute(
        select(Role).where(Role.key == role_data.key)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Role key already exists")

    # دریافت دسترسی‌ها
    permissions = []
    if role_data.permission_codes:
        result = await db.execute(
            select(Permission).where(Permission.code.in_(role_data.permission_codes))
        )
        permissions = result.scalars().all()

    role = Role(
        key=role_data.key,
        title=role_data.title,
        description=role_data.description,
        is_system=False,
        permissions=permissions
    )

    db.add(role)
    await db.commit()
    await db.refresh(role)
    return role


@router.put("/{role_key}", response_model=RoleSchema)
async def update_role(
        role_key: str,
        role_data: RoleUpdate,
        db: AsyncSession = Depends(get_db),
        _=Depends(require_permission("user.update"))
):
    """ویرایش نقش (فقط ادمین)"""
    result = await db.execute(
        select(Role).where(Role.key == role_key)
    )
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if role.is_system:
        raise HTTPException(status_code=400, detail="Cannot modify system role")

    if role_data.title:
        role.title = role_data.title
    if role_data.description:
        role.description = role_data.description

    if role_data.permission_codes is not None:
        result = await db.execute(
            select(Permission).where(Permission.code.in_(role_data.permission_codes))
        )
        role.permissions = result.scalars().all()

    await db.commit()
    await db.refresh(role)
    return role


@router.delete("/{role_key}")
async def delete_role(
        role_key: str,
        db: AsyncSession = Depends(get_db),
        _=Depends(require_permission("user.delete"))
):
    """حذف نقش (فقط ادمین)"""
    result = await db.execute(
        select(Role).where(Role.key == role_key)
    )
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if role.is_system:
        raise HTTPException(status_code=400, detail="Cannot delete system role")

    await db.delete(role)
    await db.commit()
    return MessageResponse(message=f"Role {role_key} deleted")


@router.post("/assign/{user_id}/{role_key}")
async def assign_role_to_user(
        user_id: int,
        role_key: str,
        db: AsyncSession = Depends(get_db),
        admin: User = Depends(require_roles("SUPER_ADMIN"))
):
    """اختصاص نقش (فقط سوپر ادمین)"""

    # user
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")

    # role
    result = await db.execute(select(Role).where(Role.key == role_key))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(404, "Role not found")

    # prevent assigning system critical roles
    if role.key == "SUPER_ADMIN" and not admin.is_superuser:
        raise HTTPException(403, "Cannot assign super admin")

    if role not in user.roles:
        user.roles.append(role)
        await db.commit()

    return MessageResponse(message=f"Role {role_key} assigned to user {user_id}")
