"""Service Endpoints — configurable base URLs for Spark, Trino, Airflow, RabbitMQ, etc."""
from __future__ import annotations
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.auth.dependencies import require_active_user, require_org_admin
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

    class Config:
        from_attributes = True


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_model=List[ServiceEndpointOut])
async def list_endpoints(
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    stmt = select(ServiceEndpoint).where(ServiceEndpoint.org_id == user.org_id)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=ServiceEndpointOut, status_code=status.HTTP_201_CREATED)
async def create_endpoint(
    body: ServiceEndpointCreate,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    obj = ServiceEndpoint(org_id=user.org_id, **body.model_dump())
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
    if not obj or obj.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Service endpoint not found")
    return obj


@router.put("/{endpoint_id}", response_model=ServiceEndpointOut)
async def update_endpoint(
    endpoint_id: uuid.UUID,
    body: ServiceEndpointUpdate,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(ServiceEndpoint, endpoint_id)
    if not obj or obj.org_id != user.org_id:
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
    obj = await db.get(ServiceEndpoint, endpoint_id)
    if not obj or obj.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Service endpoint not found")
    await db.delete(obj)
    await db.commit()
