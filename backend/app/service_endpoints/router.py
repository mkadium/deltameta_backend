"""Service Endpoints — configurable base URLs for Spark, Trino, Airflow, RabbitMQ, etc."""
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
from app.govern.models import ServiceEndpoint

router = APIRouter(prefix="/service-endpoints", tags=["Service Endpoints"])

KNOWN_SERVICES = {
    "spark_ui", "spark_history", "trino_ui", "airflow_ui",
    "rabbitmq_ui", "celery_flower", "jupyter", "minio_console",
    "iceberg_rest",
}


# ── Schemas ──────────────────────────────────────────────────────────────────

class ServiceEndpointCreate(BaseModel):
    service_name: str
    base_url: str
    extra: dict = {}


class ServiceEndpointUpdate(BaseModel):
    base_url: Optional[str] = None
    extra: Optional[dict] = None
    is_active: Optional[bool] = None


class ServiceEndpointOut(BaseModel):
    id: uuid.UUID
    org_id: Optional[uuid.UUID]
    service_name: str
    base_url: str
    extra: dict
    is_active: bool
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_model=List[ServiceEndpointOut])
async def list_endpoints(
    service_name: Optional[str] = Query(None, description="Filter by service name (e.g. spark_ui, trino_ui)."),
    is_active: Optional[bool] = Query(None, description="Filter by active/inactive endpoints."),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    stmt = select(ServiceEndpoint).where(ServiceEndpoint.org_id == active_org)
    if service_name:
        stmt = stmt.where(ServiceEndpoint.service_name == service_name)
    if is_active is not None:
        stmt = stmt.where(ServiceEndpoint.is_active == is_active)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=ServiceEndpointOut, status_code=status.HTTP_201_CREATED)
async def create_endpoint(
    body: ServiceEndpointCreate,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    obj = ServiceEndpoint(org_id=active_org, **body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{endpoint_id}", response_model=ServiceEndpointOut)
async def get_endpoint(
    endpoint_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(ServiceEndpoint, endpoint_id)
    if not obj or obj.org_id != get_active_org_id(user):
        raise HTTPException(status_code=404, detail="Service endpoint not found")
    return obj


@router.put("/{endpoint_id}", response_model=ServiceEndpointOut)
async def update_endpoint(
    endpoint_id: uuid.UUID,
    body: ServiceEndpointUpdate,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    obj = await db.get(ServiceEndpoint, endpoint_id)
    if not obj or obj.org_id != active_org:
        raise HTTPException(status_code=404, detail="Service endpoint not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_endpoint(
    endpoint_id: uuid.UUID,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    obj = await db.get(ServiceEndpoint, endpoint_id)
    if not obj or obj.org_id != active_org:
        raise HTTPException(status_code=404, detail="Service endpoint not found")
    await db.delete(obj)
    await db.commit()
