"""Storage Config — switch between MinIO and S3, manage connection details."""
from __future__ import annotations
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.auth.dependencies import get_active_org_id, require_active_user, require_org_admin
from app.auth.models import User
from app.govern.models import StorageConfig

router = APIRouter(prefix="/storage-config", tags=["Storage Config"])

VALID_PROVIDERS = {"minio", "s3", "gcs", "azure_blob"}


# ── Schemas ──────────────────────────────────────────────────────────────────

class StorageConfigCreate(BaseModel):
    provider: str = "minio"
    endpoint: Optional[str] = None
    bucket: Optional[str] = None
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    region: Optional[str] = None
    extra: dict = {}


class StorageConfigUpdate(BaseModel):
    provider: Optional[str] = None
    endpoint: Optional[str] = None
    bucket: Optional[str] = None
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    region: Optional[str] = None
    extra: Optional[dict] = None
    is_active: Optional[bool] = None


class StorageConfigOut(BaseModel):
    id: uuid.UUID
    org_id: Optional[uuid.UUID]
    provider: str
    endpoint: Optional[str]
    bucket: Optional[str]
    access_key: Optional[str]
    region: Optional[str]
    is_active: bool
    # secret_key intentionally omitted from output

    class Config:
        from_attributes = True


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_model=List[StorageConfigOut])
async def list_configs(
    provider: Optional[str] = Query(None, description="Filter by storage provider (minio/s3/gcs/azure_blob)."),
    is_active: Optional[bool] = Query(None, description="Filter by active/inactive configs."),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    stmt = select(StorageConfig).where(StorageConfig.org_id == active_org)
    if provider:
        stmt = stmt.where(StorageConfig.provider == provider)
    if is_active is not None:
        stmt = stmt.where(StorageConfig.is_active == is_active)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=StorageConfigOut, status_code=status.HTTP_201_CREATED)
async def create_config(
    body: StorageConfigCreate,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    if body.provider not in VALID_PROVIDERS:
        raise HTTPException(status_code=422, detail=f"Invalid provider. Allowed: {sorted(VALID_PROVIDERS)}")
    active_org = get_active_org_id(user)
    obj = StorageConfig(org_id=active_org, **body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{config_id}", response_model=StorageConfigOut)
async def get_config(
    config_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(StorageConfig, config_id)
    if not obj or obj.org_id != get_active_org_id(user):
        raise HTTPException(status_code=404, detail="Storage config not found")
    return obj


@router.put("/{config_id}", response_model=StorageConfigOut)
async def update_config(
    config_id: uuid.UUID,
    body: StorageConfigUpdate,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    obj = await db.get(StorageConfig, config_id)
    if not obj or obj.org_id != active_org:
        raise HTTPException(status_code=404, detail="Storage config not found")
    data = body.model_dump(exclude_unset=True)
    if "provider" in data and data["provider"] not in VALID_PROVIDERS:
        raise HTTPException(status_code=422, detail=f"Invalid provider. Allowed: {sorted(VALID_PROVIDERS)}")
    for k, v in data.items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.post("/{config_id}/activate", response_model=StorageConfigOut)
async def activate_config(
    config_id: uuid.UUID,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    """Deactivate all other configs for this org and activate this one."""
    active_org = get_active_org_id(user)
    stmt = select(StorageConfig).where(StorageConfig.org_id == active_org)
    result = await db.execute(stmt)
    all_configs = result.scalars().all()
    target = None
    for cfg in all_configs:
        if cfg.id == config_id:
            target = cfg
        cfg.is_active = (cfg.id == config_id)
    if not target:
        raise HTTPException(status_code=404, detail="Storage config not found")
    await db.commit()
    await db.refresh(target)
    return target


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_config(
    config_id: uuid.UUID,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    obj = await db.get(StorageConfig, config_id)
    if not obj or obj.org_id != active_org:
        raise HTTPException(status_code=404, detail="Storage config not found")
    await db.delete(obj)
    await db.commit()
