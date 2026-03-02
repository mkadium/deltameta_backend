"""Catalog Domains — Governance data domains (separate from IAM subject areas)."""
from __future__ import annotations
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.auth.dependencies import require_active_user
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
    search: Optional[str] = Query(None),
    domain_type: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(True),
    skip: int = 0,
    limit: int = 50,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    stmt = select(CatalogDomain).where(CatalogDomain.org_id == user.org_id)
    if is_active is not None:
        stmt = stmt.where(CatalogDomain.is_active == is_active)
    if search:
        stmt = stmt.where(CatalogDomain.name.ilike(f"%{search}%"))
    if domain_type:
        stmt = stmt.where(CatalogDomain.domain_type == domain_type)
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=CatalogDomainOut, status_code=status.HTTP_201_CREATED)
async def create_catalog_domain(
    body: CatalogDomainCreate,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    payload = body.model_dump(exclude={"owner_ids", "expert_ids"})
    obj = CatalogDomain(org_id=user.org_id, created_by=user.id, **payload)
    db.add(obj)
    await db.flush([obj])
    if body.owner_ids:
        await _sync_m2m(db, catalog_domain_owners, "domain_id", obj.id, "user_id", body.owner_ids)
    if body.expert_ids:
        await _sync_m2m(db, catalog_domain_experts, "domain_id", obj.id, "user_id", body.expert_ids)
    await emit(db, entity_type="catalog_domain", action="created", entity_id=obj.id,
               org_id=user.org_id, actor_id=user.id, details={"name": obj.name})
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
    if not obj or obj.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Catalog domain not found")
    return obj


@router.put("/{domain_id}", response_model=CatalogDomainOut)
async def update_catalog_domain(
    domain_id: uuid.UUID,
    body: CatalogDomainUpdate,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(CatalogDomain, domain_id)
    if not obj or obj.org_id != user.org_id:
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
               org_id=user.org_id, actor_id=user.id)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{domain_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_catalog_domain(
    domain_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(CatalogDomain, domain_id)
    if not obj or obj.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Catalog domain not found")
    await db.delete(obj)
    await db.commit()
