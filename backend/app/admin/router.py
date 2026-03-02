"""Admin User Management — create, list, update, deactivate users (org admin only)."""
from __future__ import annotations
import secrets
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.auth.dependencies import require_org_admin
from app.auth.models import User
from app.auth.service import hash_password

router = APIRouter(prefix="/admin", tags=["Admin"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class AdminUserCreate(BaseModel):
    email: EmailStr
    username: str
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    is_admin: bool = False
    send_invite: bool = False


class AdminUserUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None


class PasswordResetRequest(BaseModel):
    new_password: Optional[str] = None  # if None, a random password is generated


class AdminUserOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    email: str
    username: str
    name: str
    display_name: Optional[str]
    is_admin: bool
    is_active: bool
    is_verified: bool
    last_login_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class PasswordResetOut(BaseModel):
    user_id: uuid.UUID
    temporary_password: Optional[str] = None
    message: str


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/users", response_model=List[AdminUserOut])
async def list_users(
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    is_admin: Optional[bool] = Query(None),
    skip: int = 0,
    limit: int = 50,
    admin: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    stmt = select(User).where(User.org_id == admin.org_id)
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)
    if is_admin is not None:
        stmt = stmt.where(User.is_admin == is_admin)
    if search:
        stmt = stmt.where(
            User.name.ilike(f"%{search}%") |
            User.email.ilike(f"%{search}%") |
            User.username.ilike(f"%{search}%")
        )
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/users", response_model=AdminUserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: AdminUserCreate,
    admin: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    # Check uniqueness
    existing = await db.execute(
        select(User).where(
            (User.email == body.email) | (User.username == body.username)
        )
    )
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="Email or username already exists")

    temp_password = secrets.token_urlsafe(12)
    user = User(
        org_id=admin.org_id,
        email=body.email,
        username=body.username,
        name=body.name,
        display_name=body.display_name,
        description=body.description,
        is_admin=body.is_admin,
        hashed_password=hash_password(temp_password),
        is_active=True,
        is_verified=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    # In production, send temp_password via email when send_invite=True
    return user


@router.get("/users/{user_id}", response_model=AdminUserOut)
async def get_user(
    user_id: uuid.UUID,
    admin: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    user = await db.get(User, user_id)
    if not user or user.org_id != admin.org_id:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.put("/users/{user_id}", response_model=AdminUserOut)
async def update_user(
    user_id: uuid.UUID,
    body: AdminUserUpdate,
    admin: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    user = await db.get(User, user_id)
    if not user or user.org_id != admin.org_id:
        raise HTTPException(status_code=404, detail="User not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(user, k, v)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/users/{user_id}/reset-password", response_model=PasswordResetOut)
async def reset_password(
    user_id: uuid.UUID,
    body: PasswordResetRequest,
    admin: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    user = await db.get(User, user_id)
    if not user or user.org_id != admin.org_id:
        raise HTTPException(status_code=404, detail="User not found")
    new_pwd = body.new_password or secrets.token_urlsafe(12)
    user.hashed_password = hash_password(new_pwd)
    user.failed_attempts = 0
    user.locked_until = None
    await db.commit()
    return PasswordResetOut(
        user_id=user.id,
        temporary_password=new_pwd if not body.new_password else None,
        message="Password updated. Share the temporary password with the user securely." if not body.new_password else "Password updated.",
    )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: uuid.UUID,
    admin: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    """Soft-delete: deactivate rather than physical delete."""
    user = await db.get(User, user_id)
    if not user or user.org_id != admin.org_id:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
    user.is_active = False
    await db.commit()
