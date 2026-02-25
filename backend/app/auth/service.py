"""
Auth service — password hashing, JWT creation/decoding, lockout logic.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.settings import settings
from app.auth.models import AuthConfig, Organization, User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------------------------------------------------------------------------
# Password utilities
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    """Return bcrypt hash of the plain-text password."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain matches the stored hash."""
    return pwd_context.verify(plain, hashed)


# ---------------------------------------------------------------------------
# JWT utilities
# ---------------------------------------------------------------------------

def create_access_token(
    user_id: str,
    org_id: str,
    expiry_minutes: int,
    is_admin: bool = False,
    is_global_admin: bool = False,
) -> str:
    """Create a signed JWT access token."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=expiry_minutes)
    payload = {
        "sub": str(user_id),
        "org": str(org_id),
        "is_admin": is_admin,
        "is_global_admin": is_global_admin,
        "iat": now,
        "exp": expire,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """
    Decode and validate a JWT.
    Raises HTTP 401 on any failure (expired, invalid signature, malformed).
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        if payload.get("sub") is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is invalid or expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ---------------------------------------------------------------------------
# Lockout logic
# ---------------------------------------------------------------------------

def check_lockout(user: User, auth_config: AuthConfig) -> None:
    """
    Raise HTTP 403 if the user is currently locked out.
    Lockout is cleared automatically once locked_until has passed.
    """
    if user.locked_until is not None:
        now = datetime.now(timezone.utc)
        locked_until = user.locked_until
        # Make timezone-aware if necessary
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if now < locked_until:
            remaining = int((locked_until - now).total_seconds() // 60)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Account is locked. Try again in {remaining} minute(s).",
            )


async def handle_failed_attempt(
    user: User, auth_config: AuthConfig, db: AsyncSession
) -> None:
    """
    Increment failed_attempts counter.
    If max_failed_attempts is reached, set locked_until.
    """
    user.failed_attempts = (user.failed_attempts or 0) + 1

    if user.failed_attempts >= auth_config.max_failed_attempts:
        user.locked_until = datetime.now(timezone.utc) + timedelta(
            minutes=auth_config.lockout_duration_minutes
        )

    db.add(user)
    await db.commit()


async def reset_failed_attempts(user: User, db: AsyncSession) -> None:
    """Clear failed attempt counters on successful login."""
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.now(timezone.utc)
    db.add(user)
    await db.commit()


# ---------------------------------------------------------------------------
# User lookup helpers
# ---------------------------------------------------------------------------

async def get_user_by_login(login: str, db: AsyncSession) -> Optional[User]:
    """
    Find a user by email or username (whichever matches).
    Returns None if not found.
    """
    stmt = select(User).where(
        (User.email == login) | (User.username == login)
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def get_auth_config_for_org(org_id: str, db: AsyncSession) -> AuthConfig:
    """
    Return the AuthConfig row for the given org.
    Raises 500 if missing (shouldn't happen after migration).
    """
    stmt = select(AuthConfig).where(AuthConfig.org_id == org_id)
    result = await db.execute(stmt)
    cfg = result.scalars().first()
    if cfg is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth configuration missing for this organization.",
        )
    return cfg


# ---------------------------------------------------------------------------
# Slug generator
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")
