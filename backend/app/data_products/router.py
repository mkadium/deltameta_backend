"""Data Products — CRUD API."""
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
from app.govern.models import DataProduct, data_product_owners, data_product_experts
from app.govern.activity import emit

router = APIRouter(prefix="/data-products", tags=["Data Products"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class UserRef(BaseModel):
    id: uuid.UUID
    name: Optional[str] = None

    class Config:
        from_attributes = True


class DataProductCreate(BaseModel):
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    domain_id: Optional[uuid.UUID] = None
    owner_ids: List[uuid.UUID] = []
    expert_ids: List[uuid.UUID] = []


class DataProductUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    domain_id: Optional[uuid.UUID] = None
    status: Optional[str] = None
    version: Optional[str] = None
    owner_ids: Optional[List[uuid.UUID]] = None
    expert_ids: Optional[List[uuid.UUID]] = None
    is_active: Optional[bool] = None


class DataProductOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    domain_id: Optional[uuid.UUID]
    name: str
    display_name: Optional[str]
    description: Optional[str]
    version: str
    status: str
    is_active: bool
    created_by: Optional[uuid.UUID]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    owners: List[UserRef] = []
    experts: List[UserRef] = []

    class Config:
        from_attributes = True


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _sync_m2m(db, table, col_a, val_a, col_b, ids):
    await db.execute(table.delete().where(table.c[col_a] == val_a))
    for id_ in ids:
        await db.execute(table.insert().values({col_a: val_a, col_b: id_}))


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_model=List[DataProductOut])
async def list_data_products(
    search: Optional[str] = Query(None, description="Search by name or display_name."),
    domain_id: Optional[uuid.UUID] = Query(None, description="Filter by catalog domain."),
    product_status: Optional[str] = Query(None, alias="status", description="Filter by status (draft/published/deprecated)."),
    is_active: Optional[bool] = Query(None, description="Filter by active/inactive."),
    version: Optional[str] = Query(None, description="Filter by version string."),
    created_by: Optional[uuid.UUID] = Query(None, description="Filter by creator user ID."),
    # Relational filters
    owner_id: Optional[uuid.UUID] = Query(None, description="Filter products owned by this user (M2M)."),
    expert_id: Optional[uuid.UUID] = Query(None, description="Filter products where this user is an expert (M2M)."),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    stmt = select(DataProduct).where(DataProduct.org_id == get_active_org_id(user)).distinct()
    if search:
        stmt = stmt.where(DataProduct.name.ilike(f"%{search}%") | DataProduct.display_name.ilike(f"%{search}%"))
    if domain_id:
        stmt = stmt.where(DataProduct.domain_id == domain_id)
    if product_status:
        stmt = stmt.where(DataProduct.status == product_status)
    if is_active is not None:
        stmt = stmt.where(DataProduct.is_active == is_active)
    if version:
        stmt = stmt.where(DataProduct.version == version)
    if created_by:
        stmt = stmt.where(DataProduct.created_by == created_by)
    # Relational JOIN filters
    if owner_id is not None:
        stmt = stmt.join(data_product_owners, data_product_owners.c.product_id == DataProduct.id).where(data_product_owners.c.user_id == owner_id)
    if expert_id is not None:
        stmt = stmt.join(data_product_experts, data_product_experts.c.product_id == DataProduct.id).where(data_product_experts.c.user_id == expert_id)
    stmt = stmt.order_by(DataProduct.name).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=DataProductOut, status_code=status.HTTP_201_CREATED)
async def create_data_product(
    body: DataProductCreate,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    payload = body.model_dump(exclude={"owner_ids", "expert_ids"})
    obj = DataProduct(org_id=get_active_org_id(user), created_by=user.id, **payload)
    db.add(obj)
    await db.flush([obj])
    if body.owner_ids:
        await _sync_m2m(db, data_product_owners, "product_id", obj.id, "user_id", body.owner_ids)
    if body.expert_ids:
        await _sync_m2m(db, data_product_experts, "product_id", obj.id, "user_id", body.expert_ids)
    await emit(db, entity_type="data_product", action="created", entity_id=obj.id,
               org_id=get_active_org_id(user), actor_id=user.id, details={"name": obj.name})
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{product_id}", response_model=DataProductOut)
async def get_data_product(
    product_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(DataProduct, product_id)
    if not obj or obj.org_id != get_active_org_id(user):
        raise HTTPException(status_code=404, detail="Data product not found")
    return obj


@router.put("/{product_id}", response_model=DataProductOut)
async def update_data_product(
    product_id: uuid.UUID,
    body: DataProductUpdate,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(DataProduct, product_id)
    if not obj or obj.org_id != get_active_org_id(user):
        raise HTTPException(status_code=404, detail="Data product not found")
    data = body.model_dump(exclude_unset=True)
    owner_ids = data.pop("owner_ids", None)
    expert_ids = data.pop("expert_ids", None)
    for k, v in data.items():
        setattr(obj, k, v)
    if owner_ids is not None:
        await _sync_m2m(db, data_product_owners, "product_id", obj.id, "user_id", owner_ids)
    if expert_ids is not None:
        await _sync_m2m(db, data_product_experts, "product_id", obj.id, "user_id", expert_ids)
    await emit(db, entity_type="data_product", action="updated", entity_id=obj.id,
               org_id=get_active_org_id(user), actor_id=user.id)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_data_product(
    product_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(DataProduct, product_id)
    if not obj or obj.org_id != get_active_org_id(user):
        raise HTTPException(status_code=404, detail="Data product not found")
    await db.delete(obj)
    await db.commit()
