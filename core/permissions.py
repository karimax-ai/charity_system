# app/core/permissions.py
from fastapi import Depends, HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from core.cache import get_cache, set_cache
import json
from core.database import get_db
from core.security import decode_token, oauth2_scheme
from models.user import User
import logging
logger = logging.getLogger(__name__)

async def get_current_user(
        token: str = Depends(oauth2_scheme),
        db: AsyncSession = Depends(get_db),
) -> User:

    try:
        user_id = decode_token(token)
    except JWTError as e:
        logger.warning(f"Invalid token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    result = await db.execute(select(User).where(User.uuid == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active or user.deleted_at:
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
        cache_key = f"user_permissions:{user.id}"

        cached = await get_cache(cache_key)
        if cached:
            permissions = set(json.loads(cached))
        else:
            result = await db.execute(
                select(User)
                .options(
                    selectinload(User.roles)
                    .selectinload("permissions")
                )
                .where(User.id == user.id)
            )
            db_user = result.scalar_one()

            permissions = {
                perm.code
                for role in db_user.roles
                for perm in role.permissions
            }

            await set_cache(cache_key, json.dumps(list(permissions)), ttl=300)

        if permission_code not in permissions:
            raise HTTPException(status_code=403, detail="Permission denied")

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



