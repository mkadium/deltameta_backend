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
from app.auth.dependencies import get_active_org_id, require_active_user, require_org_admin
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


class LookupCategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class LookupValueUpdate(BaseModel):
    label: Optional[str] = None
    value: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_model=List[LookupCategoryOut])
async def list_categories(
    search: Optional[str] = Query(None, description="Search by category name or slug."),
    is_system: Optional[bool] = Query(None, description="Filter system categories vs org-custom categories."),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """Return all categories visible to this org (system + org-scoped)."""
    active_org = get_active_org_id(user)
    stmt = (
        select(LookupCategory)
        .where(or_(LookupCategory.org_id == active_org, LookupCategory.org_id.is_(None)))
        .options(selectinload(LookupCategory.values))
        .order_by(LookupCategory.name)
    )
    if is_system is not None:
        stmt = stmt.where(LookupCategory.is_system == is_system)
    if search:
        stmt = stmt.where(LookupCategory.name.ilike(f"%{search}%") | LookupCategory.slug.ilike(f"%{search}%"))
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{slug}", response_model=LookupCategoryOut)
async def get_category_by_slug(
    slug: str,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    stmt = (
        select(LookupCategory)
        .where(
            LookupCategory.slug == slug,
            or_(LookupCategory.org_id == active_org, LookupCategory.org_id.is_(None)),
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
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    """Create an org-scoped lookup category (org admin only)."""
    active_org = get_active_org_id(user)
    cat = LookupCategory(org_id=active_org, **body.model_dump())
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return cat


@router.get("/{category_id}/values", response_model=List[LookupValueOut])
async def list_values(
    category_id: uuid.UUID,
    search: Optional[str] = Query(None, description="Search by label or value."),
    is_active: Optional[bool] = Query(True, description="Filter by active/inactive values."),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """List values for a lookup category, filtered by active state and searchable by label/value."""
    active_org = get_active_org_id(user)
    cat = await db.get(LookupCategory, category_id)
    if not cat or (cat.org_id is not None and cat.org_id != active_org):
        raise HTTPException(status_code=404, detail="Category not found")
    stmt = select(LookupValue).where(LookupValue.category_id == category_id)
    if is_active is not None:
        stmt = stmt.where(LookupValue.is_active == is_active)
    if search:
        stmt = stmt.where(LookupValue.label.ilike(f"%{search}%") | LookupValue.value.ilike(f"%{search}%"))
    stmt = stmt.order_by(LookupValue.sort_order, LookupValue.label).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/{category_id}/values", response_model=LookupValueOut, status_code=status.HTTP_201_CREATED)
async def add_value(
    category_id: uuid.UUID,
    body: LookupValueCreate,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    cat = await db.get(LookupCategory, category_id)
    if not cat or (cat.org_id is not None and cat.org_id != active_org):
        raise HTTPException(status_code=404, detail="Category not found")
    val = LookupValue(category_id=category_id, org_id=active_org, **body.model_dump())
    db.add(val)
    await db.commit()
    await db.refresh(val)
    return val


@router.patch("/{category_id}/values/{value_id}", response_model=LookupValueOut)
async def update_value(
    category_id: uuid.UUID,
    value_id: uuid.UUID,
    body: LookupValueUpdate,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    """Update label, value, sort_order, or is_active for a lookup value (org admin only)."""
    active_org = get_active_org_id(user)
    val = await db.get(LookupValue, value_id)
    if not val or val.category_id != category_id:
        raise HTTPException(status_code=404, detail="Value not found")
    if val.org_id is not None and val.org_id != active_org:
        raise HTTPException(status_code=403, detail="Cannot modify a value belonging to another organization")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(val, k, v)
    await db.commit()
    await db.refresh(val)
    return val


@router.delete("/{category_id}/values/{value_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_value(
    category_id: uuid.UUID,
    value_id: uuid.UUID,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    val = await db.get(LookupValue, value_id)
    if not val or val.category_id != category_id:
        raise HTTPException(status_code=404, detail="Value not found")
    if val.org_id is not None and val.org_id != active_org:
        raise HTTPException(status_code=403, detail="Cannot delete a value belonging to another organization")
    await db.delete(val)
    await db.commit()


@router.put("/{category_id}", response_model=LookupCategoryOut)
async def update_category(
    category_id: uuid.UUID,
    body: LookupCategoryUpdate,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    """Update name or description for an org-scoped lookup category."""
    active_org = get_active_org_id(user)
    cat = await db.get(LookupCategory, category_id)
    if not cat or cat.is_system:
        raise HTTPException(status_code=404, detail="Category not found or is a system category")
    if cat.org_id != active_org:
        raise HTTPException(status_code=403, detail="Cannot modify a category belonging to another organization")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(cat, k, v)
    await db.commit()
    await db.refresh(cat)
    return cat


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: uuid.UUID,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    """Delete an org-scoped lookup category (system categories cannot be deleted)."""
    active_org = get_active_org_id(user)
    cat = await db.get(LookupCategory, category_id)
    if not cat or cat.is_system:
        raise HTTPException(status_code=404, detail="Category not found or is a system category")
    if cat.org_id != active_org:
        raise HTTPException(status_code=403, detail="Cannot delete a category belonging to another organization")
    await db.delete(cat)
    await db.commit()
