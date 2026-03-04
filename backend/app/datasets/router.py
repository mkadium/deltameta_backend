"""
Datasets API — CRUD for raw data collections (DB schemas, S3 buckets, APIs, files).

Hierarchy:  CatalogDomain → Dataset → DataAsset → DataAssetColumn

Endpoints:
  GET    /datasets                      List datasets (with filters)
  POST   /datasets                      Create dataset
  GET    /datasets/{id}                 Get dataset by ID
  PUT    /datasets/{id}                 Update dataset
  DELETE /datasets/{id}                 Delete dataset (soft)

  GET    /datasets/{id}/owners          List dataset owners
  POST   /datasets/{id}/owners          Bulk add owners
  DELETE /datasets/{id}/owners/{uid}    Remove owner

  GET    /datasets/{id}/experts         List dataset experts
  POST   /datasets/{id}/experts         Bulk add experts
  DELETE /datasets/{id}/experts/{uid}   Remove expert
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import distinct, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.auth.dependencies import get_active_org_id, require_active_user, require_org_admin
from app.auth.abac import require_permission
from app.auth.models import User
from sqlalchemy.orm import selectinload

from app.govern.models import (
    CatalogDomain, Dataset,
    dataset_owners, dataset_experts,
)

router = APIRouter(prefix="/datasets", tags=["Datasets"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class UserSummary(BaseModel):
    id: uuid.UUID
    email: str
    display_name: Optional[str] = None
    model_config = {"from_attributes": True}


class DatasetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    display_name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    domain_id: Optional[uuid.UUID] = Field(None, description="Catalog domain this dataset belongs to")
    source_type: Optional[str] = Field(None, max_length=100, description="e.g. database, schema, s3_bucket, api, file")
    source_url: Optional[str] = Field(None, max_length=512)
    tags: List[str] = Field(default_factory=list, description="Free-form string tags")
    owner_ids: List[uuid.UUID] = Field(default_factory=list)
    expert_ids: List[uuid.UUID] = Field(default_factory=list)


class DatasetUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    display_name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    domain_id: Optional[uuid.UUID] = None
    source_type: Optional[str] = Field(None, max_length=100)
    source_url: Optional[str] = Field(None, max_length=512)
    tags: Optional[List[str]] = None
    is_active: Optional[bool] = None
    owner_ids: Optional[List[uuid.UUID]] = None
    expert_ids: Optional[List[uuid.UUID]] = None


class DatasetOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    domain_id: Optional[uuid.UUID] = None
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    source_type: Optional[str] = None
    source_url: Optional[str] = None
    tags: List[str] = []
    is_active: bool
    created_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime
    owners: List[UserSummary] = []
    experts: List[UserSummary] = []

    model_config = {"from_attributes": True}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_dataset_or_404(dataset_id: uuid.UUID, org_id: uuid.UUID, db: AsyncSession) -> Dataset:
    result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id, Dataset.org_id == org_id)
    )
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    return obj


async def _resolve_users(user_ids: List[uuid.UUID], org_id: uuid.UUID, db: AsyncSession) -> List[User]:
    if not user_ids:
        return []
    result = await db.execute(
        select(User).where(User.id.in_(user_ids), User.org_id == org_id, User.is_active == True)
    )
    found = result.scalars().all()
    if len(found) != len(user_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more user IDs not found in this org")
    return list(found)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=List[DatasetOut])
async def list_datasets(
    search: Optional[str] = Query(None, description="Search by name or description"),
    domain_id: Optional[uuid.UUID] = Query(None, description="Filter by catalog domain"),
    source_type: Optional[str] = Query(None, description="Filter by source type (e.g. database, s3_bucket)"),
    is_active: Optional[bool] = Query(None),
    created_by: Optional[uuid.UUID] = Query(None),
    # Relational filters
    owner_id: Optional[uuid.UUID] = Query(None, description="Filter datasets that have this user as owner"),
    expert_id: Optional[uuid.UUID] = Query(None, description="Filter datasets that have this user as expert"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    stmt = select(Dataset).where(Dataset.org_id == active_org).distinct()

    if search:
        stmt = stmt.where(
            Dataset.name.ilike(f"%{search}%") | Dataset.description.ilike(f"%{search}%")
        )
    if domain_id is not None:
        stmt = stmt.where(Dataset.domain_id == domain_id)
    if source_type is not None:
        stmt = stmt.where(Dataset.source_type == source_type)
    if is_active is not None:
        stmt = stmt.where(Dataset.is_active == is_active)
    if created_by is not None:
        stmt = stmt.where(Dataset.created_by == created_by)
    if owner_id is not None:
        stmt = stmt.join(dataset_owners, dataset_owners.c.dataset_id == Dataset.id).where(
            dataset_owners.c.user_id == owner_id
        )
    if expert_id is not None:
        stmt = stmt.join(dataset_experts, dataset_experts.c.dataset_id == Dataset.id).where(
            dataset_experts.c.user_id == expert_id
        )

    stmt = stmt.order_by(Dataset.name).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=DatasetOut, status_code=status.HTTP_201_CREATED)
async def create_dataset(
    body: DatasetCreate,
    user: User = Depends(require_permission("dataset", "create")),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)

    if body.domain_id:
        domain = await db.execute(
            select(CatalogDomain).where(CatalogDomain.id == body.domain_id, CatalogDomain.org_id == active_org)
        )
        if not domain.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Catalog domain not found in this org")

    owners = await _resolve_users(body.owner_ids, active_org, db)
    experts = await _resolve_users(body.expert_ids, active_org, db)

    ds = Dataset(
        id=uuid.uuid4(),
        org_id=active_org,
        domain_id=body.domain_id,
        name=body.name,
        display_name=body.display_name,
        description=body.description,
        source_type=body.source_type,
        source_url=body.source_url,
        tags=body.tags,
        is_active=True,
        created_by=user.id,
    )
    ds.owners = owners
    ds.experts = experts
    db.add(ds)
    await db.commit()
    await db.refresh(ds)
    return ds


@router.get("/{dataset_id}", response_model=DatasetOut)
async def get_dataset(
    dataset_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    return await _get_dataset_or_404(dataset_id, active_org, db)


@router.put("/{dataset_id}", response_model=DatasetOut)
async def update_dataset(
    dataset_id: uuid.UUID,
    body: DatasetUpdate,
    user: User = Depends(require_permission("dataset", "update")),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    ds = await _get_dataset_or_404(dataset_id, active_org, db)

    if body.name is not None:
        ds.name = body.name
    if body.display_name is not None:
        ds.display_name = body.display_name
    if body.description is not None:
        ds.description = body.description
    if body.domain_id is not None:
        domain = await db.execute(
            select(CatalogDomain).where(CatalogDomain.id == body.domain_id, CatalogDomain.org_id == active_org)
        )
        if not domain.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Catalog domain not found in this org")
        ds.domain_id = body.domain_id
    if body.source_type is not None:
        ds.source_type = body.source_type
    if body.source_url is not None:
        ds.source_url = body.source_url
    if body.tags is not None:
        ds.tags = body.tags
    if body.is_active is not None:
        ds.is_active = body.is_active
    if body.owner_ids is not None:
        ds.owners = await _resolve_users(body.owner_ids, active_org, db)
    if body.expert_ids is not None:
        ds.experts = await _resolve_users(body.expert_ids, active_org, db)

    await db.commit()
    await db.refresh(ds)
    return ds


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dataset(
    dataset_id: uuid.UUID,
    user: User = Depends(require_permission("dataset", "delete")),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    ds = await _get_dataset_or_404(dataset_id, active_org, db)
    ds.is_active = False
    await db.commit()


# ── Owner / Expert sub-resources ─────────────────────────────────────────────

class BulkUserIds(BaseModel):
    user_ids: List[uuid.UUID]


async def _load_dataset_with_relations(dataset_id: uuid.UUID, org_id: uuid.UUID, db: AsyncSession) -> Dataset:
    result = await db.execute(
        select(Dataset)
        .where(Dataset.id == dataset_id, Dataset.org_id == org_id)
        .options(selectinload(Dataset.owners), selectinload(Dataset.experts))
    )
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    return obj


@router.get("/{dataset_id}/owners", response_model=List[UserSummary], summary="List owners of a dataset")
async def list_dataset_owners(
    dataset_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    ds = await _load_dataset_with_relations(dataset_id, active_org, db)
    return ds.owners


@router.post("/{dataset_id}/owners", status_code=status.HTTP_201_CREATED)
async def add_dataset_owners(
    dataset_id: uuid.UUID,
    body: BulkUserIds,
    admin: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    """Assign one or more owners to a dataset at once."""
    active_org = get_active_org_id(admin)
    await _get_dataset_or_404(dataset_id, active_org, db)
    for uid in body.user_ids:
        target = await db.get(User, uid)
        if not target or target.org_id != active_org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User {uid} not found in this org")
        await db.execute(
            pg_insert(dataset_owners).values(dataset_id=dataset_id, user_id=uid).on_conflict_do_nothing()
        )
    await db.commit()
    return {"message": f"{len(body.user_ids)} owner(s) added"}


@router.delete("/{dataset_id}/owners/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_dataset_owner(
    dataset_id: uuid.UUID,
    user_id: uuid.UUID,
    admin: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(admin)
    await _get_dataset_or_404(dataset_id, active_org, db)
    await db.execute(
        dataset_owners.delete().where(
            dataset_owners.c.dataset_id == dataset_id,
            dataset_owners.c.user_id == user_id,
        )
    )
    await db.commit()


@router.get("/{dataset_id}/experts", response_model=List[UserSummary], summary="List experts of a dataset")
async def list_dataset_experts(
    dataset_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    ds = await _load_dataset_with_relations(dataset_id, active_org, db)
    return ds.experts


@router.post("/{dataset_id}/experts", status_code=status.HTTP_201_CREATED)
async def add_dataset_experts(
    dataset_id: uuid.UUID,
    body: BulkUserIds,
    admin: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    """Assign one or more experts to a dataset at once."""
    active_org = get_active_org_id(admin)
    await _get_dataset_or_404(dataset_id, active_org, db)
    for uid in body.user_ids:
        target = await db.get(User, uid)
        if not target or target.org_id != active_org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User {uid} not found in this org")
        await db.execute(
            pg_insert(dataset_experts).values(dataset_id=dataset_id, user_id=uid).on_conflict_do_nothing()
        )
    await db.commit()
    return {"message": f"{len(body.user_ids)} expert(s) added"}


@router.delete("/{dataset_id}/experts/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_dataset_expert(
    dataset_id: uuid.UUID,
    user_id: uuid.UUID,
    admin: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(admin)
    await _get_dataset_or_404(dataset_id, active_org, db)
    await db.execute(
        dataset_experts.delete().where(
            dataset_experts.c.dataset_id == dataset_id,
            dataset_experts.c.user_id == user_id,
        )
    )
    await db.commit()
