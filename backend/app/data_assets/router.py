"""
Data Assets API — CRUD for cataloged data assets (tables, views, files, APIs).

Hierarchy:  Dataset → DataAsset → DataAssetColumn

Endpoints:
  GET    /data-assets                           List assets (with filters)
  POST   /data-assets                           Create asset
  GET    /data-assets/{id}                      Get asset
  PUT    /data-assets/{id}                      Update asset
  DELETE /data-assets/{id}                      Soft delete

  GET    /data-assets/{id}/tags                 List classification tags on asset
  POST   /data-assets/{id}/tags                 Bulk assign classification tags
  DELETE /data-assets/{id}/tags/{tag_id}        Remove classification tag

  GET    /data-assets/{id}/owners               List owners
  POST   /data-assets/{id}/owners               Bulk add owners
  DELETE /data-assets/{id}/owners/{uid}         Remove owner

  GET    /data-assets/{id}/experts              List experts
  POST   /data-assets/{id}/experts              Bulk add experts
  DELETE /data-assets/{id}/experts/{uid}        Remove expert

  GET    /data-assets/{id}/columns              List columns
  POST   /data-assets/{id}/columns              Add column
  PUT    /data-assets/{id}/columns/{col_id}     Update column
  DELETE /data-assets/{id}/columns/{col_id}     Delete column

  POST   /data-assets/{id}/columns/bulk         Bulk replace all columns (schema sync)
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.auth.dependencies import get_active_org_id, require_active_user, require_org_admin
from app.auth.abac import require_permission
from app.auth.models import User
from app.govern.models import (
    ClassificationTag, DataAsset, DataAssetColumn, Dataset,
    data_asset_owners, data_asset_experts, data_asset_tags,
)

router = APIRouter(prefix="/data-assets", tags=["Data Assets"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class UserSummary(BaseModel):
    id: uuid.UUID
    email: str
    display_name: Optional[str] = None
    model_config = {"from_attributes": True}


class TagSummary(BaseModel):
    id: uuid.UUID
    name: str
    display_name: Optional[str] = None
    color: Optional[str] = None
    model_config = {"from_attributes": True}


class ColumnOut(BaseModel):
    id: uuid.UUID
    asset_id: uuid.UUID
    org_id: uuid.UUID
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    data_type: str
    ordinal_position: int
    is_nullable: bool
    is_primary_key: bool
    is_foreign_key: bool
    is_pii: bool
    sensitivity: Optional[str] = None
    default_value: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ColumnCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    display_name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    data_type: str = Field("varchar", max_length=100)
    ordinal_position: int = Field(0, ge=0)
    is_nullable: bool = True
    is_primary_key: bool = False
    is_foreign_key: bool = False
    is_pii: bool = False
    sensitivity: Optional[str] = Field(None, max_length=50)
    default_value: Optional[str] = Field(None, max_length=512)


class ColumnUpdate(BaseModel):
    display_name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    data_type: Optional[str] = Field(None, max_length=100)
    ordinal_position: Optional[int] = Field(None, ge=0)
    is_nullable: Optional[bool] = None
    is_primary_key: Optional[bool] = None
    is_foreign_key: Optional[bool] = None
    is_pii: Optional[bool] = None
    sensitivity: Optional[str] = Field(None, max_length=50)
    default_value: Optional[str] = Field(None, max_length=512)


class DataAssetCreate(BaseModel):
    dataset_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=255)
    display_name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    asset_type: str = Field("table", max_length=100, description="table, view, materialized_view, file, api_endpoint, stream")
    fully_qualified_name: Optional[str] = Field(None, max_length=512, description="e.g. mydb.public.sales")
    sensitivity: Optional[str] = Field("internal", max_length=50, description="public, internal, confidential, restricted")
    is_pii: bool = False
    data_product_id: Optional[uuid.UUID] = None
    owner_ids: List[uuid.UUID] = Field(default_factory=list)
    expert_ids: List[uuid.UUID] = Field(default_factory=list)
    tag_ids: List[uuid.UUID] = Field(default_factory=list, description="Classification tag IDs")
    columns: List[ColumnCreate] = Field(default_factory=list, description="Initial column schema (optional)")


class DataAssetUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    display_name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    asset_type: Optional[str] = Field(None, max_length=100)
    fully_qualified_name: Optional[str] = Field(None, max_length=512)
    sensitivity: Optional[str] = Field(None, max_length=50)
    is_pii: Optional[bool] = None
    row_count: Optional[int] = None
    size_bytes: Optional[int] = None
    data_product_id: Optional[uuid.UUID] = None
    is_active: Optional[bool] = None
    owner_ids: Optional[List[uuid.UUID]] = None
    expert_ids: Optional[List[uuid.UUID]] = None
    tag_ids: Optional[List[uuid.UUID]] = None


class DataAssetOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    dataset_id: uuid.UUID
    data_product_id: Optional[uuid.UUID] = None
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    asset_type: str
    fully_qualified_name: Optional[str] = None
    sensitivity: Optional[str] = None
    row_count: Optional[int] = None
    size_bytes: Optional[int] = None
    is_pii: bool
    is_active: bool
    created_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime
    owners: List[UserSummary] = []
    experts: List[UserSummary] = []
    classification_tags: List[TagSummary] = []
    columns: List[ColumnOut] = []

    model_config = {"from_attributes": True}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_asset_or_404(asset_id: uuid.UUID, org_id: uuid.UUID, db: AsyncSession) -> DataAsset:
    result = await db.execute(
        select(DataAsset).where(DataAsset.id == asset_id, DataAsset.org_id == org_id)
    )
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data asset not found")
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


async def _resolve_tags(tag_ids: List[uuid.UUID], org_id: uuid.UUID, db: AsyncSession) -> List[ClassificationTag]:
    if not tag_ids:
        return []
    result = await db.execute(
        select(ClassificationTag).where(ClassificationTag.id.in_(tag_ids), ClassificationTag.org_id == org_id)
    )
    found = result.scalars().all()
    if len(found) != len(tag_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more tag IDs not found in this org")
    return list(found)


# ── Data Asset Endpoints ───────────────────────────────────────────────────────

@router.get("", response_model=List[DataAssetOut])
async def list_data_assets(
    search: Optional[str] = Query(None, description="Search by name, description, or fully_qualified_name"),
    dataset_id: Optional[uuid.UUID] = Query(None),
    data_product_id: Optional[uuid.UUID] = Query(None),
    asset_type: Optional[str] = Query(None, description="table, view, file, api_endpoint, stream"),
    sensitivity: Optional[str] = Query(None, description="public, internal, confidential, restricted"),
    is_pii: Optional[bool] = Query(None),
    is_active: Optional[bool] = Query(None),
    created_by: Optional[uuid.UUID] = Query(None),
    # Relational filters
    owner_id: Optional[uuid.UUID] = Query(None, description="Filter assets that have this owner"),
    expert_id: Optional[uuid.UUID] = Query(None, description="Filter assets that have this expert"),
    tag_id: Optional[uuid.UUID] = Query(None, description="Filter assets tagged with this classification tag"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    stmt = select(DataAsset).where(DataAsset.org_id == active_org).distinct()

    if search:
        stmt = stmt.where(
            DataAsset.name.ilike(f"%{search}%") |
            DataAsset.description.ilike(f"%{search}%") |
            DataAsset.fully_qualified_name.ilike(f"%{search}%")
        )
    if dataset_id is not None:
        stmt = stmt.where(DataAsset.dataset_id == dataset_id)
    if data_product_id is not None:
        stmt = stmt.where(DataAsset.data_product_id == data_product_id)
    if asset_type is not None:
        stmt = stmt.where(DataAsset.asset_type == asset_type)
    if sensitivity is not None:
        stmt = stmt.where(DataAsset.sensitivity == sensitivity)
    if is_pii is not None:
        stmt = stmt.where(DataAsset.is_pii == is_pii)
    if is_active is not None:
        stmt = stmt.where(DataAsset.is_active == is_active)
    if created_by is not None:
        stmt = stmt.where(DataAsset.created_by == created_by)
    if owner_id is not None:
        stmt = stmt.join(data_asset_owners, data_asset_owners.c.asset_id == DataAsset.id).where(
            data_asset_owners.c.user_id == owner_id
        )
    if expert_id is not None:
        stmt = stmt.join(data_asset_experts, data_asset_experts.c.asset_id == DataAsset.id).where(
            data_asset_experts.c.user_id == expert_id
        )
    if tag_id is not None:
        stmt = stmt.join(data_asset_tags, data_asset_tags.c.asset_id == DataAsset.id).where(
            data_asset_tags.c.tag_id == tag_id
        )

    stmt = stmt.order_by(DataAsset.name).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=DataAssetOut, status_code=status.HTTP_201_CREATED)
async def create_data_asset(
    body: DataAssetCreate,
    user: User = Depends(require_permission("data_asset", "create")),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)

    dataset = await db.execute(
        select(Dataset).where(Dataset.id == body.dataset_id, Dataset.org_id == active_org)
    )
    if not dataset.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found in this org")

    owners = await _resolve_users(body.owner_ids, active_org, db)
    experts = await _resolve_users(body.expert_ids, active_org, db)
    tags = await _resolve_tags(body.tag_ids, active_org, db)

    asset = DataAsset(
        id=uuid.uuid4(),
        org_id=active_org,
        dataset_id=body.dataset_id,
        data_product_id=body.data_product_id,
        name=body.name,
        display_name=body.display_name,
        description=body.description,
        asset_type=body.asset_type,
        fully_qualified_name=body.fully_qualified_name,
        sensitivity=body.sensitivity,
        is_pii=body.is_pii,
        is_active=True,
        created_by=user.id,
    )
    asset.owners = owners
    asset.experts = experts
    asset.classification_tags = tags
    db.add(asset)
    await db.flush()

    for i, col in enumerate(body.columns):
        db.add(DataAssetColumn(
            id=uuid.uuid4(),
            asset_id=asset.id,
            org_id=active_org,
            name=col.name,
            display_name=col.display_name,
            description=col.description,
            data_type=col.data_type,
            ordinal_position=col.ordinal_position if col.ordinal_position else i,
            is_nullable=col.is_nullable,
            is_primary_key=col.is_primary_key,
            is_foreign_key=col.is_foreign_key,
            is_pii=col.is_pii,
            sensitivity=col.sensitivity,
            default_value=col.default_value,
        ))

    await db.commit()
    await db.refresh(asset)
    return asset


@router.get("/{asset_id}", response_model=DataAssetOut)
async def get_data_asset(
    asset_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    return await _get_asset_or_404(asset_id, active_org, db)


@router.put("/{asset_id}", response_model=DataAssetOut)
async def update_data_asset(
    asset_id: uuid.UUID,
    body: DataAssetUpdate,
    user: User = Depends(require_permission("data_asset", "update")),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    asset = await _get_asset_or_404(asset_id, active_org, db)

    if body.name is not None:
        asset.name = body.name
    if body.display_name is not None:
        asset.display_name = body.display_name
    if body.description is not None:
        asset.description = body.description
    if body.asset_type is not None:
        asset.asset_type = body.asset_type
    if body.fully_qualified_name is not None:
        asset.fully_qualified_name = body.fully_qualified_name
    if body.sensitivity is not None:
        asset.sensitivity = body.sensitivity
    if body.is_pii is not None:
        asset.is_pii = body.is_pii
    if body.row_count is not None:
        asset.row_count = body.row_count
    if body.size_bytes is not None:
        asset.size_bytes = body.size_bytes
    if body.data_product_id is not None:
        asset.data_product_id = body.data_product_id
    if body.is_active is not None:
        asset.is_active = body.is_active
    if body.owner_ids is not None:
        asset.owners = await _resolve_users(body.owner_ids, active_org, db)
    if body.expert_ids is not None:
        asset.experts = await _resolve_users(body.expert_ids, active_org, db)
    if body.tag_ids is not None:
        asset.classification_tags = await _resolve_tags(body.tag_ids, active_org, db)

    await db.commit()
    await db.refresh(asset)
    return asset


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_data_asset(
    asset_id: uuid.UUID,
    user: User = Depends(require_permission("data_asset", "delete")),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    asset = await _get_asset_or_404(asset_id, active_org, db)
    asset.is_active = False
    await db.commit()


# ── Tag / Owner / Expert sub-resources ────────────────────────────────────────

class BulkTagIds(BaseModel):
    tag_ids: List[uuid.UUID]


class BulkUserIds(BaseModel):
    user_ids: List[uuid.UUID]


async def _load_asset_with_relations(asset_id: uuid.UUID, org_id: uuid.UUID, db: AsyncSession) -> DataAsset:
    result = await db.execute(
        select(DataAsset)
        .where(DataAsset.id == asset_id, DataAsset.org_id == org_id)
        .options(
            selectinload(DataAsset.classification_tags),
            selectinload(DataAsset.owners),
            selectinload(DataAsset.experts),
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data asset not found")
    return obj


@router.get("/{asset_id}/tags", response_model=List[TagSummary], summary="List classification tags assigned to an asset")
async def list_asset_tags(
    asset_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    asset = await _load_asset_with_relations(asset_id, active_org, db)
    return asset.classification_tags


@router.post("/{asset_id}/tags", status_code=status.HTTP_201_CREATED)
async def add_asset_tags(
    asset_id: uuid.UUID,
    body: BulkTagIds,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """Assign one or more classification tags to a data asset at once."""
    active_org = get_active_org_id(user)
    await _get_asset_or_404(asset_id, active_org, db)
    for tid in body.tag_ids:
        tag = await db.execute(
            select(ClassificationTag).where(ClassificationTag.id == tid, ClassificationTag.org_id == active_org)
        )
        if not tag.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Classification tag {tid} not found in this org")
        await db.execute(
            pg_insert(data_asset_tags).values(asset_id=asset_id, tag_id=tid).on_conflict_do_nothing()
        )
    await db.commit()
    return {"message": f"{len(body.tag_ids)} tag(s) assigned to asset"}


@router.delete("/{asset_id}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_asset_tag(
    asset_id: uuid.UUID,
    tag_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    await _get_asset_or_404(asset_id, active_org, db)
    await db.execute(
        data_asset_tags.delete().where(
            data_asset_tags.c.asset_id == asset_id,
            data_asset_tags.c.tag_id == tag_id,
        )
    )
    await db.commit()


@router.get("/{asset_id}/owners", response_model=List[UserSummary], summary="List owners of a data asset")
async def list_asset_owners(
    asset_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    asset = await _load_asset_with_relations(asset_id, active_org, db)
    return asset.owners


@router.post("/{asset_id}/owners", status_code=status.HTTP_201_CREATED)
async def add_asset_owners(
    asset_id: uuid.UUID,
    body: BulkUserIds,
    admin: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    """Assign one or more owners to a data asset at once."""
    active_org = get_active_org_id(admin)
    await _get_asset_or_404(asset_id, active_org, db)
    for uid in body.user_ids:
        target = await db.get(User, uid)
        if not target or target.org_id != active_org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User {uid} not found in this org")
        await db.execute(
            pg_insert(data_asset_owners).values(asset_id=asset_id, user_id=uid).on_conflict_do_nothing()
        )
    await db.commit()
    return {"message": f"{len(body.user_ids)} owner(s) added"}


@router.delete("/{asset_id}/owners/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_asset_owner(
    asset_id: uuid.UUID,
    user_id: uuid.UUID,
    admin: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(admin)
    await _get_asset_or_404(asset_id, active_org, db)
    await db.execute(
        data_asset_owners.delete().where(
            data_asset_owners.c.asset_id == asset_id,
            data_asset_owners.c.user_id == user_id,
        )
    )
    await db.commit()


@router.get("/{asset_id}/experts", response_model=List[UserSummary], summary="List experts of a data asset")
async def list_asset_experts(
    asset_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    asset = await _load_asset_with_relations(asset_id, active_org, db)
    return asset.experts


@router.post("/{asset_id}/experts", status_code=status.HTTP_201_CREATED)
async def add_asset_experts(
    asset_id: uuid.UUID,
    body: BulkUserIds,
    admin: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    """Assign one or more experts to a data asset at once."""
    active_org = get_active_org_id(admin)
    await _get_asset_or_404(asset_id, active_org, db)
    for uid in body.user_ids:
        target = await db.get(User, uid)
        if not target or target.org_id != active_org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User {uid} not found in this org")
        await db.execute(
            pg_insert(data_asset_experts).values(asset_id=asset_id, user_id=uid).on_conflict_do_nothing()
        )
    await db.commit()
    return {"message": f"{len(body.user_ids)} expert(s) added"}


@router.delete("/{asset_id}/experts/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_asset_expert(
    asset_id: uuid.UUID,
    user_id: uuid.UUID,
    admin: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(admin)
    await _get_asset_or_404(asset_id, active_org, db)
    await db.execute(
        data_asset_experts.delete().where(
            data_asset_experts.c.asset_id == asset_id,
            data_asset_experts.c.user_id == user_id,
        )
    )
    await db.commit()


# ── Column Sub-resource ───────────────────────────────────────────────────────

@router.get("/{asset_id}/columns", response_model=List[ColumnOut])
async def list_columns(
    asset_id: uuid.UUID,
    search: Optional[str] = Query(None),
    data_type: Optional[str] = Query(None),
    is_pii: Optional[bool] = Query(None),
    is_primary_key: Optional[bool] = Query(None),
    is_foreign_key: Optional[bool] = Query(None),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    await _get_asset_or_404(asset_id, active_org, db)
    stmt = select(DataAssetColumn).where(DataAssetColumn.asset_id == asset_id)
    if search:
        stmt = stmt.where(
            DataAssetColumn.name.ilike(f"%{search}%") | DataAssetColumn.description.ilike(f"%{search}%")
        )
    if data_type is not None:
        stmt = stmt.where(DataAssetColumn.data_type == data_type)
    if is_pii is not None:
        stmt = stmt.where(DataAssetColumn.is_pii == is_pii)
    if is_primary_key is not None:
        stmt = stmt.where(DataAssetColumn.is_primary_key == is_primary_key)
    if is_foreign_key is not None:
        stmt = stmt.where(DataAssetColumn.is_foreign_key == is_foreign_key)
    stmt = stmt.order_by(DataAssetColumn.ordinal_position, DataAssetColumn.name)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/{asset_id}/columns", response_model=ColumnOut, status_code=status.HTTP_201_CREATED)
async def add_column(
    asset_id: uuid.UUID,
    body: ColumnCreate,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    await _get_asset_or_404(asset_id, active_org, db)
    col = DataAssetColumn(
        id=uuid.uuid4(),
        asset_id=asset_id,
        org_id=active_org,
        **body.model_dump(),
    )
    db.add(col)
    await db.commit()
    await db.refresh(col)
    return col


@router.put("/{asset_id}/columns/{column_id}", response_model=ColumnOut)
async def update_column(
    asset_id: uuid.UUID,
    column_id: uuid.UUID,
    body: ColumnUpdate,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    await _get_asset_or_404(asset_id, active_org, db)
    result = await db.execute(
        select(DataAssetColumn).where(DataAssetColumn.id == column_id, DataAssetColumn.asset_id == asset_id)
    )
    col = result.scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Column not found")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(col, field, val)
    await db.commit()
    await db.refresh(col)
    return col


@router.delete("/{asset_id}/columns/{column_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_column(
    asset_id: uuid.UUID,
    column_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    await _get_asset_or_404(asset_id, active_org, db)
    result = await db.execute(
        select(DataAssetColumn).where(DataAssetColumn.id == column_id, DataAssetColumn.asset_id == asset_id)
    )
    col = result.scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Column not found")
    await db.delete(col)
    await db.commit()


@router.post("/{asset_id}/columns/bulk", response_model=List[ColumnOut])
async def bulk_replace_columns(
    asset_id: uuid.UUID,
    columns: List[ColumnCreate],
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """Full replace of all columns for a data asset (schema sync from source)."""
    active_org = get_active_org_id(user)
    await _get_asset_or_404(asset_id, active_org, db)
    await db.execute(
        DataAssetColumn.__table__.delete().where(DataAssetColumn.asset_id == asset_id)
    )
    new_cols = [
        DataAssetColumn(
            id=uuid.uuid4(),
            asset_id=asset_id,
            org_id=active_org,
            name=col.name,
            display_name=col.display_name,
            description=col.description,
            data_type=col.data_type,
            ordinal_position=col.ordinal_position if col.ordinal_position else i,
            is_nullable=col.is_nullable,
            is_primary_key=col.is_primary_key,
            is_foreign_key=col.is_foreign_key,
            is_pii=col.is_pii,
            sensitivity=col.sensitivity,
            default_value=col.default_value,
        )
        for i, col in enumerate(columns)
    ]
    db.add_all(new_cols)
    await db.commit()
    result = await db.execute(
        select(DataAssetColumn)
        .where(DataAssetColumn.asset_id == asset_id)
        .order_by(DataAssetColumn.ordinal_position)
    )
    return result.scalars().all()
