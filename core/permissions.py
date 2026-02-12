# app/core/permissions.py
from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.security import decode_token
from models.user import User


async def get_current_user(
        token: str = Depends(decode_token),
        db: AsyncSession = Depends(get_db),
) -> User:

    try:
        user_id = decode_token(token)
    except:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    result = await db.execute(
        select(User).where(User.uuid == user_id)
    )
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not authenticated",
        )

    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


def require_permission(permission_code: str):
    async def checker(
            user: User = Depends(get_current_user),
            db: AsyncSession = Depends(get_db)
    ):
        # بارگذاری roles و permissions اگر lazy loading داریم
        await db.refresh(user, ['roles'])
        for role in user.roles:
            await db.refresh(role, ['permissions'])

        user_permissions = set()
        for role in user.roles:
            user_permissions.update({perm.code for perm in role.permissions})

        if permission_code not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied",
            )

        return True

    return checker



# core/permissions.py
def require_roles(*roles_allowed):
    def wrapper(user: User = Depends(get_current_active_user)):
        user_roles = [role.key for role in user.roles]
        if not any(r in user_roles for r in roles_allowed):
            raise HTTPException(status_code=403, detail="Not authorized")
        return user
    return wrapper
