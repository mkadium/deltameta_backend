"""
FastAPI dependencies for authentication and authorization.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.auth.models import User
from app.auth.service import decode_access_token

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_session),
) -> User:
    """
    Decode the Bearer token, look up the user in DB.
    Raises 401 if token is invalid or user not found.
    Eagerly loads teams and roles for downstream use.
    """
    payload = decode_access_token(credentials.credentials)
    user_id: str = payload.get("sub")

    stmt = (
        select(User)
        .where(User.id == user_id)
        .options(
            selectinload(User.teams),
            selectinload(User.roles),
            selectinload(User.policies),
        )
    )
    result = await db.execute(stmt)
    user = result.scalars().first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def require_active_user(
    user: User = Depends(get_current_user),
) -> User:
    """Raise 403 if the user account is inactive."""
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive. Contact your administrator.",
        )
    return user


async def require_org_admin(
    user: User = Depends(require_active_user),
) -> User:
    """Raise 403 if the user is not an org admin (is_admin=True) or global admin."""
    if not (user.is_admin or user.is_global_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization admin privileges required.",
        )
    return user


async def require_global_admin(
    user: User = Depends(require_active_user),
) -> User:
    """Raise 403 if the user is not a global admin."""
    if not user.is_global_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Global admin privileges required.",
        )
    return user
