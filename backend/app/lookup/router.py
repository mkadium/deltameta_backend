"""Lookup Categories & Values — CRUD API.

Used by frontend to populate dropdowns for domain_type, metric_type, etc.
System categories (is_system=True) are global; org-scoped ones override or extend.
"""
from __future__ import annotations
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.auth.dependencies import require_active_user
from app.auth.models import User
from app.govern.models import LookupCategory, LookupValue

router = APIRouter(prefix="/lookup", tags=["Lookup"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class LookupValueOut(BaseModel):
    id: uuid.UUID
    label: str
    value: str
    sort_order: int
    is_active: bool

    class Config:
        from_attributes = True


class LookupCategoryOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: Optional[str]
    is_system: bool
    values: List[LookupValueOut] = []

    class Config:
        from_attributes = True


class LookupValueCreate(BaseModel):
    label: str
    value: str
    sort_order: int = 0


class LookupCategoryCreate(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_model=List[LookupCategoryOut])
async def list_categories(
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """Return all categories visible to this org (system + org-scoped)."""
    stmt = (
        select(LookupCategory)
        .where(
            or_(LookupCategory.org_id == user.org_id, LookupCategory.org_id.is_(None))
        )
        .options(selectinload(LookupCategory.values))
        .order_by(LookupCategory.name)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{slug}", response_model=LookupCategoryOut)
async def get_category_by_slug(
    slug: str,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    stmt = (
        select(LookupCategory)
        .where(
            LookupCategory.slug == slug,
            or_(LookupCategory.org_id == user.org_id, LookupCategory.org_id.is_(None)),
        )
        .options(selectinload(LookupCategory.values))
    )
    result = await db.execute(stmt)
    cat = result.scalars().first()
    if not cat:
        raise HTTPException(status_code=404, detail="Lookup category not found")
    return cat


@router.post("", response_model=LookupCategoryOut, status_code=status.HTTP_201_CREATED)
async def create_category(
    body: LookupCategoryCreate,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    cat = LookupCategory(org_id=user.org_id, **body.model_dump())
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return cat


@router.post("/{category_id}/values", response_model=LookupValueOut, status_code=status.HTTP_201_CREATED)
async def add_value(
    category_id: uuid.UUID,
    body: LookupValueCreate,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    cat = await db.get(LookupCategory, category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    val = LookupValue(category_id=category_id, org_id=user.org_id, **body.model_dump())
    db.add(val)
    await db.commit()
    await db.refresh(val)
    return val


@router.delete("/{category_id}/values/{value_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_value(
    category_id: uuid.UUID,
    value_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    val = await db.get(LookupValue, value_id)
    if not val or val.category_id != category_id:
        raise HTTPException(status_code=404, detail="Value not found")
    await db.delete(val)
    await db.commit()
