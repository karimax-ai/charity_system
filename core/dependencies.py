from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from typing import Optional, Annotated
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError

from core.database import get_db
from models.user import User
from core.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    auto_error=False
)

async def get_current_user_optional(
    token: Annotated[Optional[str], Depends(oauth2_scheme)],
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:

    if not token:
        return None

    try:
        user_id = decode_token(token)
    except JWTError:
        return None

    result = await db.execute(select(User).where(User.uuid == user_id))
    user = result.scalar_one_or_none()

    if user and user.is_active:
        return user

    return None
