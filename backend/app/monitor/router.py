"""Monitor — status checks and UI redirect URLs for Spark, Trino, Airflow, etc.

All external service URLs are pulled from the `service_endpoints` table.
Each endpoint returns a redirect URL that the frontend can open in a new tab
or iframe, plus an optional health-check status.
"""
from __future__ import annotations
import uuid
from typing import Dict, List, Optional, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.auth.dependencies import require_active_user
from app.auth.models import User
from app.govern.models import ServiceEndpoint

router = APIRouter(prefix="/monitor", tags=["Monitor"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class ServiceStatusOut(BaseModel):
    service_name: str
    base_url: str
    ui_url: str
    is_active: bool
    health: Optional[str] = None  # "ok" | "unreachable" | "unknown"


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_endpoint(db: AsyncSession, org_id, service_name: str) -> Optional[ServiceEndpoint]:
    stmt = select(ServiceEndpoint).where(
        ServiceEndpoint.org_id == org_id,
        ServiceEndpoint.service_name == service_name,
        ServiceEndpoint.is_active == True,
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def _ping(url: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url)
            return "ok" if resp.status_code < 500 else "unreachable"
    except Exception:
        return "unreachable"


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_model=List[ServiceStatusOut])
async def list_services(
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """List all configured service endpoints with their UI URLs."""
    stmt = select(ServiceEndpoint).where(ServiceEndpoint.org_id == user.org_id)
    result = await db.execute(stmt)
    endpoints = result.scalars().all()
    out = []
    for ep in endpoints:
        out.append(ServiceStatusOut(
            service_name=ep.service_name,
            base_url=ep.base_url,
            ui_url=ep.base_url,
            is_active=ep.is_active,
        ))
    return out


@router.get("/spark")
async def spark_ui(
    job_id: Optional[str] = Query(None),
    app_id: Optional[str] = Query(None),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    ep = await _get_endpoint(db, user.org_id, "spark_ui")
    if not ep:
        raise HTTPException(status_code=404, detail="Spark UI endpoint not configured")
    url = ep.base_url
    if app_id:
        url = f"{url.rstrip('/')}/history/{app_id}"
    elif job_id:
        url = f"{url.rstrip('/')}/jobs/job/?id={job_id}"
    return {"redirect_url": url, "service": "spark_ui"}


@router.get("/spark/history")
async def spark_history(
    app_id: Optional[str] = Query(None),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    ep = await _get_endpoint(db, user.org_id, "spark_history")
    if not ep:
        raise HTTPException(status_code=404, detail="Spark History Server endpoint not configured")
    url = f"{ep.base_url.rstrip('/')}/history/{app_id}" if app_id else ep.base_url
    return {"redirect_url": url, "service": "spark_history"}


@router.get("/trino")
async def trino_ui(
    query_id: Optional[str] = Query(None),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    ep = await _get_endpoint(db, user.org_id, "trino_ui")
    if not ep:
        raise HTTPException(status_code=404, detail="Trino UI endpoint not configured")
    url = f"{ep.base_url.rstrip('/')}/ui/query.html?{query_id}" if query_id else ep.base_url
    return {"redirect_url": url, "service": "trino_ui"}


@router.get("/airflow")
async def airflow_ui(
    dag_id: Optional[str] = Query(None),
    run_id: Optional[str] = Query(None),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    ep = await _get_endpoint(db, user.org_id, "airflow_ui")
    if not ep:
        raise HTTPException(status_code=404, detail="Airflow UI endpoint not configured")
    base = ep.base_url.rstrip("/")
    if dag_id and run_id:
        url = f"{base}/dags/{dag_id}/grid?dag_run_id={run_id}"
    elif dag_id:
        url = f"{base}/dags/{dag_id}/grid"
    else:
        url = base
    return {"redirect_url": url, "service": "airflow_ui"}


@router.get("/rabbitmq")
async def rabbitmq_ui(
    queue: Optional[str] = Query(None),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    ep = await _get_endpoint(db, user.org_id, "rabbitmq_ui")
    if not ep:
        raise HTTPException(status_code=404, detail="RabbitMQ UI endpoint not configured")
    url = f"{ep.base_url.rstrip('/')}/#/queues/%2F/{queue}" if queue else ep.base_url
    return {"redirect_url": url, "service": "rabbitmq_ui"}


@router.get("/celery")
async def celery_flower(
    task_id: Optional[str] = Query(None),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    ep = await _get_endpoint(db, user.org_id, "celery_flower")
    if not ep:
        raise HTTPException(status_code=404, detail="Celery Flower endpoint not configured")
    url = f"{ep.base_url.rstrip('/')}/task/{task_id}" if task_id else ep.base_url
    return {"redirect_url": url, "service": "celery_flower"}


@router.get("/jupyter")
async def jupyter_ui(
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    ep = await _get_endpoint(db, user.org_id, "jupyter")
    if not ep:
        raise HTTPException(status_code=404, detail="Jupyter endpoint not configured")
    return {"redirect_url": ep.base_url, "service": "jupyter"}


@router.get("/minio")
async def minio_console(
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    ep = await _get_endpoint(db, user.org_id, "minio_console")
    if not ep:
        raise HTTPException(status_code=404, detail="MinIO Console endpoint not configured")
    return {"redirect_url": ep.base_url, "service": "minio_console"}


@router.get("/health")
async def services_health(
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """Ping all configured services and return health status."""
    stmt = select(ServiceEndpoint).where(
        ServiceEndpoint.org_id == user.org_id,
        ServiceEndpoint.is_active == True,
    )
    result = await db.execute(stmt)
    endpoints = result.scalars().all()
    results: List[Dict[str, Any]] = []
    for ep in endpoints:
        health = await _ping(ep.base_url)
        results.append({
            "service_name": ep.service_name,
            "base_url": ep.base_url,
            "health": health,
        })
    return {"services": results}
