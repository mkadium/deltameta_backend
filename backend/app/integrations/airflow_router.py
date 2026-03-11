from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.auth.dependencies import get_active_org_id, require_active_user
from app.auth.abac import require_permission
from app.auth.models import User
from app.govern.models import ServiceEndpoint


router = APIRouter(prefix="/integrations/airflow", tags=["Airflow"])


class AirflowDAG(BaseModel):
    dag_id: str
    description: Optional[str] = None
    is_paused: Optional[bool] = None
    schedule_interval: Optional[Any] = None


class AirflowDAGDetail(BaseModel):
    dag_id: str
    description: Optional[str] = None
    is_paused: Optional[bool] = None
    timetable_description: Optional[str] = None


class AirflowDagRun(BaseModel):
    dag_run_id: str
    state: Optional[str] = None
    execution_date: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class AirflowDagRunDetail(AirflowDagRun):
    conf: Optional[Dict[str, Any]] = None


class TriggerDagRunRequest(BaseModel):
    conf: Optional[Dict[str, Any]] = None


class AirflowTask(BaseModel):
    task_id: str
    owner: Optional[str] = None
    operator: Optional[str] = None


class AirflowTaskInstance(BaseModel):
    task_id: str
    dag_id: str
    dag_run_id: Optional[str] = None
    state: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


async def _get_airflow_endpoint(
    db: AsyncSession,
    user: User,
) -> ServiceEndpoint:
    org_id = get_active_org_id(user)
    stmt = select(ServiceEndpoint).where(
        ServiceEndpoint.org_id == org_id,
        ServiceEndpoint.service_name == "airflow_ui",
        ServiceEndpoint.is_active == True,
    )
    result = await db.execute(stmt)
    ep = result.scalars().first()
    if not ep:
        raise HTTPException(
            status_code=404,
            detail="Airflow ServiceEndpoint (service_name='airflow_ui') not configured for this organization",
        )
    return ep


async def _airflow_get(ep: ServiceEndpoint, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
    base = ep.base_url.rstrip("/")
    url = f"{base}/api/v1{path}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=params)
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"Airflow API error: {resp.text}",
            )
        return resp.json()


async def _airflow_post(
    ep: ServiceEndpoint,
    path: str,
    json: Optional[Dict[str, Any]] = None,
) -> Any:
    base = ep.base_url.rstrip("/")
    url = f"{base}/api/v1{path}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, json=json)
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"Airflow API error: {resp.text}",
            )
        return resp.json()


@router.get(
    "/dags",
    response_model=List[AirflowDAG],
    dependencies=[Depends(require_permission("service_endpoint", "read"))],
)
async def list_dags(
    limit: int = Query(100, ge=1, le=500),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """
    List DAGs from Airflow.
    """
    ep = await _get_airflow_endpoint(db, user)
    data = await _airflow_get(ep, "/dags", params={"limit": limit})
    dags: List[AirflowDAG] = []
    for item in data.get("dags", []) or []:
        dags.append(
            AirflowDAG(
                dag_id=item.get("dag_id"),
                description=item.get("description"),
                is_paused=item.get("is_paused"),
                schedule_interval=item.get("schedule_interval"),
            )
        )
    return dags


@router.get(
    "/dags/{dag_id}",
    response_model=AirflowDAGDetail,
    dependencies=[Depends(require_permission("service_endpoint", "read"))],
)
async def get_dag(
    dag_id: str,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Get detail for a specific DAG.
    """
    ep = await _get_airflow_endpoint(db, user)
    data = await _airflow_get(ep, f"/dags/{dag_id}")
    return AirflowDAGDetail(
        dag_id=data.get("dag_id", dag_id),
        description=data.get("description"),
        is_paused=data.get("is_paused"),
        timetable_description=data.get("timetable_description"),
    )


@router.get(
    "/dags/{dag_id}/runs",
    response_model=List[AirflowDagRun],
    dependencies=[Depends(require_permission("service_endpoint", "read"))],
)
async def list_dag_runs(
    dag_id: str,
    limit: int = Query(100, ge=1, le=500),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """
    List DAG runs for a specific DAG.
    """
    ep = await _get_airflow_endpoint(db, user)
    data = await _airflow_get(ep, f"/dags/{dag_id}/dagRuns", params={"limit": limit})
    runs: List[AirflowDagRun] = []
    for item in data.get("dag_runs", []) or []:
        runs.append(
            AirflowDagRun(
                dag_run_id=item.get("dag_run_id"),
                state=item.get("state"),
                execution_date=item.get("logical_date") or item.get("execution_date"),
                start_date=item.get("start_date"),
                end_date=item.get("end_date"),
            )
        )
    return runs


@router.get(
    "/dags/{dag_id}/runs/{dag_run_id}",
    response_model=AirflowDagRunDetail,
    dependencies=[Depends(require_permission("service_endpoint", "read"))],
)
async def get_dag_run(
    dag_id: str,
    dag_run_id: str,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Get detail for a specific DAG run.
    """
    ep = await _get_airflow_endpoint(db, user)
    data = await _airflow_get(ep, f"/dags/{dag_id}/dagRuns/{dag_run_id}")
    return AirflowDagRunDetail(
        dag_run_id=data.get("dag_run_id", dag_run_id),
        state=data.get("state"),
        execution_date=data.get("logical_date") or data.get("execution_date"),
        start_date=data.get("start_date"),
        end_date=data.get("end_date"),
        conf=data.get("conf"),
    )


@router.post(
    "/dags/{dag_id}/pause",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("service_endpoint", "update"))],
)
async def pause_dag(
    dag_id: str,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Pause a DAG (sets is_paused = true).
    """
    ep = await _get_airflow_endpoint(db, user)
    base = ep.base_url.rstrip("/")
    url = f"{base}/api/v1/dags/{dag_id}"
    params = {"update_mask": "is_paused"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.patch(url, params=params, json={"is_paused": True})
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"Airflow API error: {resp.text}",
            )


@router.post(
    "/dags/{dag_id}/unpause",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("service_endpoint", "update"))],
)
async def unpause_dag(
    dag_id: str,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Unpause a DAG (sets is_paused = false).
    """
    ep = await _get_airflow_endpoint(db, user)
    base = ep.base_url.rstrip("/")
    url = f"{base}/api/v1/dags/{dag_id}"
    params = {"update_mask": "is_paused"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.patch(url, params=params, json={"is_paused": False})
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"Airflow API error: {resp.text}",
            )


@router.get(
    "/dags/{dag_id}/runs/{dag_run_id}/tasks/{task_id}/log",
    response_class=PlainTextResponse,
    dependencies=[Depends(require_permission("service_endpoint", "read"))],
)
async def get_task_log(
    dag_id: str,
    dag_run_id: str,
    task_id: str,
    try_number: int = Query(1, ge=1, description="Task try number for log retrieval."),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Fetch logs for a specific task instance (simple proxy of Airflow logs endpoint).
    """
    ep = await _get_airflow_endpoint(db, user)
    base = ep.base_url.rstrip("/")
    url = f"{base}/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}/logs/{try_number}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url)
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"Airflow log fetch error: {resp.text}",
            )
        return resp.text


@router.post(
    "/dags/{dag_id}/runs",
    response_model=AirflowDagRunDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("service_endpoint", "create"))],
)
async def trigger_dag_run(
    dag_id: str,
    body: TriggerDagRunRequest,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Trigger a new DAG run for a given DAG.
    """
    ep = await _get_airflow_endpoint(db, user)
    payload: Dict[str, Any] = {}
    # Airflow 2.x accepts `conf` as arbitrary JSON for DAG run config
    if body.conf is not None:
        payload["conf"] = body.conf
    data = await _airflow_post(ep, f"/dags/{dag_id}/dagRuns", json=payload)
    return AirflowDagRunDetail(
        dag_run_id=data.get("dag_run_id"),
        state=data.get("state"),
        execution_date=data.get("logical_date") or data.get("execution_date"),
        start_date=data.get("start_date"),
        end_date=data.get("end_date"),
        conf=data.get("conf"),
    )


@router.get(
    "/dags/{dag_id}/tasks",
    response_model=List[AirflowTask],
    dependencies=[Depends(require_permission("service_endpoint", "read"))],
)
async def list_tasks(
    dag_id: str,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """
    List tasks for a DAG.
    """
    ep = await _get_airflow_endpoint(db, user)
    # Airflow task endpoint returns a DAG detail including tasks array
    data = await _airflow_get(ep, f"/dags/{dag_id}/tasks")
    tasks: List[AirflowTask] = []
    for item in data.get("tasks", []) or []:
        tasks.append(
            AirflowTask(
                task_id=item.get("task_id"),
                owner=item.get("owner"),
                operator=item.get("task_type") or item.get("operator"),
            )
        )
    return tasks


@router.get(
    "/dags/{dag_id}/runs/{dag_run_id}/tasks",
    response_model=List[AirflowTaskInstance],
    dependencies=[Depends(require_permission("service_endpoint", "read"))],
)
async def list_task_instances_for_run(
    dag_id: str,
    dag_run_id: str,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """
    List task instances for a specific DAG run.
    """
    ep = await _get_airflow_endpoint(db, user)
    # Airflow exposes task instance listing per DAG run
    data = await _airflow_get(ep, f"/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances")
    tis: List[AirflowTaskInstance] = []
    for item in data.get("task_instances", []) or []:
        tis.append(
            AirflowTaskInstance(
                task_id=item.get("task_id"),
                dag_id=item.get("dag_id", dag_id),
                dag_run_id=item.get("dag_run_id", dag_run_id),
                state=item.get("state"),
                start_date=item.get("start_date"),
                end_date=item.get("end_date"),
            )
        )
    return tis

