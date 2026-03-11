from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.auth.dependencies import get_active_org_id, require_active_user
from app.auth.abac import require_permission
from app.auth.models import User
from app.govern.models import ServiceEndpoint


router = APIRouter(prefix="/integrations/spark", tags=["Spark"])


class SparkApp(BaseModel):
    id: str
    name: Optional[str] = None
    state: Optional[str] = None


class SparkJob(BaseModel):
    jobId: int
    name: Optional[str] = None
    status: Optional[str] = None


class SparkStage(BaseModel):
    stageId: int
    name: Optional[str] = None
    status: Optional[str] = None


class SparkAppDetail(BaseModel):
    id: str
    name: Optional[str] = None
    attempts: List[Dict[str, Any]]


class SparkSubmitRequest(BaseModel):
    appResource: str
    mainClass: str
    appArgs: Optional[List[str]] = None
    sparkProperties: Dict[str, Any]


class SparkSubmitResponse(BaseModel):
    submissionId: str
    success: bool
    driverState: Optional[str] = None
    workerHostPort: Optional[str] = None
    message: Optional[str] = None


async def _get_spark_endpoint(
    db: AsyncSession,
    user: User,
    service_name: str = "spark_ui",
) -> ServiceEndpoint:
    org_id = get_active_org_id(user)
    stmt = select(ServiceEndpoint).where(
        ServiceEndpoint.org_id == org_id,
        ServiceEndpoint.service_name == service_name,
        ServiceEndpoint.is_active == True,
    )
    result = await db.execute(stmt)
    ep = result.scalars().first()
    if not ep:
        raise HTTPException(
            status_code=404,
            detail=f"{service_name} ServiceEndpoint not configured for this organization",
        )
    return ep


async def _spark_get(ep: ServiceEndpoint, path: str) -> Any:
    base = ep.base_url.rstrip("/")
    url = f"{base}{path}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"Spark API error: {resp.text}",
            )
        return resp.json()


async def _spark_post(ep: ServiceEndpoint, path: str, json: Dict[str, Any]) -> Any:
    base = ep.base_url.rstrip("/")
    url = f"{base}{path}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=json)
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"Spark submit API error: {resp.text}",
            )
        return resp.json()


@router.get(
    "/apps",
    response_model=List[SparkApp],
    dependencies=[Depends(require_permission("service_endpoint", "read"))],
)
async def list_spark_apps(
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """
    List running/completed Spark applications from the Spark REST API.
    """
    ep = await _get_spark_endpoint(db, user, "spark_ui")
    data = await _spark_get(ep, "/api/v1/applications")
    apps: List[SparkApp] = []
    for app in data or []:
        app_id = app.get("id")
        name = app.get("name")
        state = None
        attempts = app.get("attempts") or []
        if attempts:
            state = attempts[-1].get("completed") and "COMPLETED" or "RUNNING"
        apps.append(SparkApp(id=app_id, name=name, state=state))
    return apps


@router.get(
    "/apps/{app_id}",
    response_model=SparkAppDetail,
    dependencies=[Depends(require_permission("service_endpoint", "read"))],
)
async def get_spark_app(
    app_id: str,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Get detail for a specific Spark application.

    Note: Spark REST API returns a list of attempts; we wrap it directly.
    """
    ep = await _get_spark_endpoint(db, user, "spark_ui")
    data = await _spark_get(ep, f"/api/v1/applications/{app_id}")
    return SparkAppDetail(
        id=data.get("id", app_id),
        name=data.get("name"),
        attempts=data.get("attempts") or [],
    )


@router.get(
    "/apps/{app_id}/jobs",
    response_model=List[SparkJob],
    dependencies=[Depends(require_permission("service_endpoint", "read"))],
)
async def list_spark_jobs(
    app_id: str,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """
    List jobs for a given Spark application.
    """
    ep = await _get_spark_endpoint(db, user, "spark_ui")
    data = await _spark_get(ep, f"/api/v1/applications/{app_id}/jobs")
    jobs: List[SparkJob] = []
    for job in data or []:
        jobs.append(
            SparkJob(
                jobId=job.get("jobId"),
                name=job.get("name"),
                status=job.get("status"),
            )
        )
    return jobs


@router.get(
    "/apps/{app_id}/stages",
    response_model=List[SparkStage],
    dependencies=[Depends(require_permission("service_endpoint", "read"))],
)
async def list_spark_stages(
    app_id: str,
    status_filter: Optional[str] = Query(
        None,
        description="Optional status filter (e.g. ACTIVE, COMPLETE, FAILED).",
    ),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """
    List stages for a given Spark application.
    """
    ep = await _get_spark_endpoint(db, user, "spark_ui")
    data = await _spark_get(ep, f"/api/v1/applications/{app_id}/stages")
    stages: List[SparkStage] = []
    for stage in data or []:
        status = stage.get("status")
        if status_filter and status_filter.upper() != (status or "").upper():
            continue
        stages.append(
            SparkStage(
                stageId=stage.get("stageId"),
                name=stage.get("name"),
                status=status,
            )
        )
    return stages


@router.post(
    "/submissions",
    response_model=SparkSubmitResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("service_endpoint", "create"))],
)
async def submit_spark_job(
    body: SparkSubmitRequest,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Submit a Spark job using the Spark standalone cluster REST API.

    Requires a ServiceEndpoint with service_name='spark_submit' pointing to the master.
    """
    ep = await _get_spark_endpoint(db, user, "spark_submit")
    payload: Dict[str, Any] = {
        "action": "CreateSubmissionRequest",
        "appResource": body.appResource,
        "mainClass": body.mainClass,
        "sparkProperties": body.sparkProperties,
    }
    if body.appArgs:
        payload["appArgs"] = body.appArgs
    data = await _spark_post(ep, "/v1/submissions/create", json=payload)
    return SparkSubmitResponse(
        submissionId=data.get("submissionId") or data.get("serverSparkVersion", ""),
        success=bool(data.get("success")),
        driverState=data.get("driverState"),
        workerHostPort=data.get("workerHostPort"),
        message=data.get("message"),
    )


class SparkSubmissionStatus(BaseModel):
    submissionId: str
    driverState: Optional[str] = None
    workerHostPort: Optional[str] = None
    success: Optional[bool] = None
    message: Optional[str] = None


@router.get(
    "/submissions/{submission_id}",
    response_model=SparkSubmissionStatus,
    dependencies=[Depends(require_permission("service_endpoint", "read"))],
)
async def get_submission_status(
    submission_id: str,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Get status for a Spark job submission (Spark standalone REST).
    """
    ep = await _get_spark_endpoint(db, user, "spark_submit")
    data = await _spark_get(ep, f"/v1/submissions/status/{submission_id}")
    return SparkSubmissionStatus(
        submissionId=data.get("submissionId", submission_id),
        driverState=data.get("driverState"),
        workerHostPort=data.get("workerHostPort"),
        success=data.get("success"),
        message=data.get("message"),
    )

