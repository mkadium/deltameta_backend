"""Catalog Domains — Governance data domains (separate from IAM subject areas)."""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.auth.dependencies import get_active_org_id, require_active_user, require_org_admin
from app.auth.models import User
from app.govern.models import (
    CatalogDomain, catalog_domain_owners, catalog_domain_experts,
)
from app.govern.activity import emit

router = APIRouter(prefix="/catalog-domains", tags=["Catalog Domains"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class UserRef(BaseModel):
    id: uuid.UUID
    name: Optional[str] = None

    class Config:
        from_attributes = True


class CatalogDomainCreate(BaseModel):
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    domain_type: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    owner_ids: List[uuid.UUID] = []
    expert_ids: List[uuid.UUID] = []


class CatalogDomainUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    domain_type: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    owner_ids: Optional[List[uuid.UUID]] = None
    expert_ids: Optional[List[uuid.UUID]] = None
    is_active: Optional[bool] = None


class CatalogDomainOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    display_name: Optional[str]
    description: Optional[str]
    domain_type: Optional[str]
    icon: Optional[str]
    color: Optional[str]
    is_active: bool
    created_by: Optional[uuid.UUID]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    owners: List[UserRef] = []
    experts: List[UserRef] = []

    class Config:
        from_attributes = True


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _sync_m2m(db: AsyncSession, table, col_a, val_a, col_b, ids: List[uuid.UUID]):
    """Replace M2M rows for (col_a=val_a) with the given ids."""
    await db.execute(table.delete().where(table.c[col_a] == val_a))
    for id_ in ids:
        await db.execute(table.insert().values({col_a: val_a, col_b: id_}))


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_model=List[CatalogDomainOut])
async def list_catalog_domains(
    search: Optional[str] = Query(None, description="Search by name or display_name."),
    domain_type: Optional[str] = Query(None, description="Filter by domain type."),
    is_active: Optional[bool] = Query(True),
    created_by: Optional[uuid.UUID] = Query(None, description="Filter by creator user ID."),
    # Relational filters
    owner_id: Optional[uuid.UUID] = Query(None, description="Filter domains owned by this user (M2M)."),
    expert_id: Optional[uuid.UUID] = Query(None, description="Filter domains where this user is an expert (M2M)."),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    stmt = select(CatalogDomain).where(CatalogDomain.org_id == get_active_org_id(user)).distinct()
    if is_active is not None:
        stmt = stmt.where(CatalogDomain.is_active == is_active)
    if search:
        stmt = stmt.where(CatalogDomain.name.ilike(f"%{search}%") | CatalogDomain.display_name.ilike(f"%{search}%"))
    if domain_type:
        stmt = stmt.where(CatalogDomain.domain_type == domain_type)
    if created_by:
        stmt = stmt.where(CatalogDomain.created_by == created_by)
    # Relational JOIN filters
    if owner_id is not None:
        stmt = stmt.join(catalog_domain_owners, catalog_domain_owners.c.domain_id == CatalogDomain.id).where(catalog_domain_owners.c.user_id == owner_id)
    if expert_id is not None:
        stmt = stmt.join(catalog_domain_experts, catalog_domain_experts.c.domain_id == CatalogDomain.id).where(catalog_domain_experts.c.user_id == expert_id)
    stmt = stmt.order_by(CatalogDomain.name).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=CatalogDomainOut, status_code=status.HTTP_201_CREATED)
async def create_catalog_domain(
    body: CatalogDomainCreate,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    payload = body.model_dump(exclude={"owner_ids", "expert_ids"})
    obj = CatalogDomain(org_id=active_org, created_by=user.id, **payload)
    db.add(obj)
    await db.flush([obj])
    if body.owner_ids:
        await _sync_m2m(db, catalog_domain_owners, "domain_id", obj.id, "user_id", body.owner_ids)
    if body.expert_ids:
        await _sync_m2m(db, catalog_domain_experts, "domain_id", obj.id, "user_id", body.expert_ids)
    await emit(db, entity_type="catalog_domain", action="created", entity_id=obj.id,
               org_id=active_org, actor_id=user.id, details={"name": obj.name})
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{domain_id}", response_model=CatalogDomainOut)
async def get_catalog_domain(
    domain_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(CatalogDomain, domain_id)
    if not obj or obj.org_id != get_active_org_id(user):
        raise HTTPException(status_code=404, detail="Catalog domain not found")
    return obj


@router.put("/{domain_id}", response_model=CatalogDomainOut)
async def update_catalog_domain(
    domain_id: uuid.UUID,
    body: CatalogDomainUpdate,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    obj = await db.get(CatalogDomain, domain_id)
    if not obj or obj.org_id != active_org:
        raise HTTPException(status_code=404, detail="Catalog domain not found")
    data = body.model_dump(exclude_unset=True)
    owner_ids = data.pop("owner_ids", None)
    expert_ids = data.pop("expert_ids", None)
    for k, v in data.items():
        setattr(obj, k, v)
    if owner_ids is not None:
        await _sync_m2m(db, catalog_domain_owners, "domain_id", obj.id, "user_id", owner_ids)
    if expert_ids is not None:
        await _sync_m2m(db, catalog_domain_experts, "domain_id", obj.id, "user_id", expert_ids)
    await emit(db, entity_type="catalog_domain", action="updated", entity_id=obj.id,
               org_id=active_org, actor_id=user.id)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{domain_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_catalog_domain(
    domain_id: uuid.UUID,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(CatalogDomain, domain_id)
    if not obj or obj.org_id != get_active_org_id(user):
        raise HTTPException(status_code=404, detail="Catalog domain not found")
    await db.delete(obj)
    await db.commit()
