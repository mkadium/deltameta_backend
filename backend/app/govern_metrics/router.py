"""Govern Metrics — catalog and manage standardized business metrics."""
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
from app.govern.models import GovernMetric, govern_metric_owners
from app.govern.activity import emit

router = APIRouter(prefix="/govern-metrics", tags=["Govern Metrics"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class UserRef(BaseModel):
    id: uuid.UUID
    name: Optional[str] = None

    class Config:
        from_attributes = True


class MetricCreate(BaseModel):
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    granularity: Optional[str] = None
    metric_type: Optional[str] = None
    language: Optional[str] = None
    measurement_unit: Optional[str] = None
    code: Optional[str] = None
    owner_ids: List[uuid.UUID] = []


class MetricUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    granularity: Optional[str] = None
    metric_type: Optional[str] = None
    language: Optional[str] = None
    measurement_unit: Optional[str] = None
    code: Optional[str] = None
    owner_ids: Optional[List[uuid.UUID]] = None
    is_active: Optional[bool] = None


class MetricOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    display_name: Optional[str]
    description: Optional[str]
    granularity: Optional[str]
    metric_type: Optional[str]
    language: Optional[str]
    measurement_unit: Optional[str]
    code: Optional[str]
    is_active: bool
    owners: List[UserRef] = []

    class Config:
        from_attributes = True


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _sync_owners(db, metric_id, ids):
    await db.execute(govern_metric_owners.delete().where(govern_metric_owners.c.metric_id == metric_id))
    for uid in ids:
        await db.execute(govern_metric_owners.insert().values(metric_id=metric_id, user_id=uid))


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_model=List[MetricOut])
async def list_metrics(
    search: Optional[str] = Query(None),
    metric_type: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 50,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    stmt = select(GovernMetric).where(GovernMetric.org_id == user.org_id)
    if search:
        stmt = stmt.where(GovernMetric.name.ilike(f"%{search}%"))
    if metric_type:
        stmt = stmt.where(GovernMetric.metric_type == metric_type)
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=MetricOut, status_code=status.HTTP_201_CREATED)
async def create_metric(
    body: MetricCreate,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    payload = body.model_dump(exclude={"owner_ids"})
    obj = GovernMetric(org_id=user.org_id, created_by=user.id, **payload)
    db.add(obj)
    await db.flush([obj])
    if body.owner_ids:
        await _sync_owners(db, obj.id, body.owner_ids)
    await emit(db, entity_type="govern_metric", action="created", entity_id=obj.id,
               org_id=user.org_id, actor_id=user.id, details={"name": obj.name})
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{metric_id}", response_model=MetricOut)
async def get_metric(
    metric_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(GovernMetric, metric_id)
    if not obj or obj.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Metric not found")
    return obj


@router.put("/{metric_id}", response_model=MetricOut)
async def update_metric(
    metric_id: uuid.UUID,
    body: MetricUpdate,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(GovernMetric, metric_id)
    if not obj or obj.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Metric not found")
    data = body.model_dump(exclude_unset=True)
    owner_ids = data.pop("owner_ids", None)
    for k, v in data.items():
        setattr(obj, k, v)
    if owner_ids is not None:
        await _sync_owners(db, obj.id, owner_ids)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{metric_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_metric(
    metric_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(GovernMetric, metric_id)
    if not obj or obj.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Metric not found")
    await db.delete(obj)
    await db.commit()
