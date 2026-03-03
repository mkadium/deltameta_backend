"""
Scheduled Tasks API — CRUD for managing scheduled/recurring task definitions.

ScheduledTask is a generic scheduling record that can be attached to any entity
(bot, pipeline, data-asset sync, test suite, etc.) via entity_type + entity_id.

Endpoints:
  GET    /scheduled-tasks                  List tasks (with filters)
  POST   /scheduled-tasks                  Create task
  GET    /scheduled-tasks/{id}             Get task by ID
  PUT    /scheduled-tasks/{id}             Update task
  DELETE /scheduled-tasks/{id}             Delete task
  PATCH  /scheduled-tasks/{id}/activate    Activate task
  PATCH  /scheduled-tasks/{id}/deactivate  Deactivate task
  POST   /scheduled-tasks/{id}/trigger     Manually mark triggered (update last_run_at + status)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.auth.dependencies import get_active_org_id, require_active_user, require_org_admin
from app.auth.models import User
from app.govern.models import ScheduledTask

router = APIRouter(prefix="/scheduled-tasks", tags=["Scheduled Tasks"])

VALID_SCHEDULE_TYPES = {"manual", "on_demand", "scheduled"}
VALID_STATUSES = {"pending", "running", "success", "failed", "skipped"}


# ── Schemas ────────────────────────────────────────────────────────────────────

class ScheduledTaskCreate(BaseModel):
    entity_type: str = Field(..., min_length=1, max_length=100,
                             description="Type of entity this task is for, e.g. 'bot', 'pipeline', 'catalog_view'")
    entity_id: Optional[uuid.UUID] = Field(None, description="ID of the related entity (optional)")
    task_name: str = Field(..., min_length=1, max_length=255)
    schedule_type: str = Field("manual", description="manual | on_demand | scheduled")
    cron_expr: Optional[str] = Field(None, max_length=100,
                                     description="Cron expression — required when schedule_type='scheduled'")
    next_run_at: Optional[datetime] = None
    payload: Dict[str, Any] = Field(default_factory=dict,
                                    description="Arbitrary JSON config for the task runner")
    is_active: bool = True


class ScheduledTaskUpdate(BaseModel):
    task_name: Optional[str] = Field(None, min_length=1, max_length=255)
    schedule_type: Optional[str] = None
    cron_expr: Optional[str] = Field(None, max_length=100)
    next_run_at: Optional[datetime] = None
    payload: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class ScheduledTaskOut(BaseModel):
    id: uuid.UUID
    org_id: Optional[uuid.UUID] = None
    entity_type: str
    entity_id: Optional[uuid.UUID] = None
    task_name: str
    schedule_type: str
    cron_expr: Optional[str] = None
    next_run_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None
    last_status: Optional[str] = None
    payload: Dict[str, Any] = {}
    is_active: bool
    created_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TriggerResponse(BaseModel):
    task_id: uuid.UUID
    triggered_at: datetime
    message: str


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_task_or_404(task_id: uuid.UUID, org_id: uuid.UUID, db: AsyncSession) -> ScheduledTask:
    result = await db.execute(
        select(ScheduledTask).where(ScheduledTask.id == task_id, ScheduledTask.org_id == org_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduled task not found")
    return task


def _validate_schedule(schedule_type: str, cron_expr: Optional[str]) -> None:
    if schedule_type not in VALID_SCHEDULE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid schedule_type '{schedule_type}'. Must be one of: {sorted(VALID_SCHEDULE_TYPES)}",
        )
    if schedule_type == "scheduled" and not cron_expr:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="cron_expr is required when schedule_type is 'scheduled'",
        )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("", response_model=List[ScheduledTaskOut], summary="List scheduled tasks")
async def list_scheduled_tasks(
    entity_type: Optional[str] = Query(None, description="Filter by entity type (e.g. bot, pipeline)"),
    entity_id: Optional[uuid.UUID] = Query(None, description="Filter by entity ID"),
    schedule_type: Optional[str] = Query(None, description="Filter by schedule type"),
    is_active: Optional[bool] = Query(None),
    last_status: Optional[str] = Query(None, description="Filter by last run status"),
    search: Optional[str] = Query(None, description="Search by task_name"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    stmt = (
        select(ScheduledTask)
        .where(ScheduledTask.org_id == active_org)
        .order_by(ScheduledTask.task_name)
        .offset(skip)
        .limit(limit)
    )
    if entity_type is not None:
        stmt = stmt.where(ScheduledTask.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(ScheduledTask.entity_id == entity_id)
    if schedule_type is not None:
        stmt = stmt.where(ScheduledTask.schedule_type == schedule_type)
    if is_active is not None:
        stmt = stmt.where(ScheduledTask.is_active == is_active)
    if last_status is not None:
        stmt = stmt.where(ScheduledTask.last_status == last_status)
    if search:
        stmt = stmt.where(ScheduledTask.task_name.ilike(f"%{search}%"))

    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=ScheduledTaskOut, status_code=status.HTTP_201_CREATED,
             summary="Create a scheduled task")
async def create_scheduled_task(
    body: ScheduledTaskCreate,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    _validate_schedule(body.schedule_type, body.cron_expr)
    active_org = get_active_org_id(user)

    task = ScheduledTask(
        id=uuid.uuid4(),
        org_id=active_org,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        task_name=body.task_name,
        schedule_type=body.schedule_type,
        cron_expr=body.cron_expr,
        next_run_at=body.next_run_at,
        payload=body.payload,
        is_active=body.is_active,
        created_by=user.id,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


@router.get("/{task_id}", response_model=ScheduledTaskOut, summary="Get a scheduled task by ID")
async def get_scheduled_task(
    task_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    return await _get_task_or_404(task_id, get_active_org_id(user), db)


@router.put("/{task_id}", response_model=ScheduledTaskOut, summary="Update a scheduled task")
async def update_scheduled_task(
    task_id: uuid.UUID,
    body: ScheduledTaskUpdate,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    task = await _get_task_or_404(task_id, get_active_org_id(user), db)

    if body.task_name is not None:
        task.task_name = body.task_name
    if body.schedule_type is not None or body.cron_expr is not None:
        new_type = body.schedule_type if body.schedule_type is not None else task.schedule_type
        new_cron = body.cron_expr if body.cron_expr is not None else task.cron_expr
        _validate_schedule(new_type, new_cron)
        task.schedule_type = new_type
        task.cron_expr = new_cron
    if body.next_run_at is not None:
        task.next_run_at = body.next_run_at
    if body.payload is not None:
        task.payload = body.payload
    if body.is_active is not None:
        task.is_active = body.is_active

    task.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a scheduled task")
async def delete_scheduled_task(
    task_id: uuid.UUID,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    task = await _get_task_or_404(task_id, get_active_org_id(user), db)
    await db.delete(task)
    await db.commit()


@router.patch("/{task_id}/activate", response_model=ScheduledTaskOut, summary="Activate a scheduled task")
async def activate_scheduled_task(
    task_id: uuid.UUID,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    task = await _get_task_or_404(task_id, get_active_org_id(user), db)
    task.is_active = True
    task.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(task)
    return task


@router.patch("/{task_id}/deactivate", response_model=ScheduledTaskOut, summary="Deactivate a scheduled task")
async def deactivate_scheduled_task(
    task_id: uuid.UUID,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    task = await _get_task_or_404(task_id, get_active_org_id(user), db)
    task.is_active = False
    task.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(task)
    return task


@router.post("/{task_id}/trigger", response_model=TriggerResponse, summary="Manually trigger a scheduled task")
async def trigger_scheduled_task(
    task_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Mark the task as manually triggered — sets last_run_at and last_status='running'.
    Actual execution is handled by the background worker that polls for triggered tasks.
    """
    task = await _get_task_or_404(task_id, get_active_org_id(user), db)
    if not task.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot trigger a deactivated task. Activate it first.",
        )
    now = datetime.now(timezone.utc)
    task.last_run_at = now
    task.last_status = "running"
    task.updated_at = now
    await db.commit()
    return TriggerResponse(
        task_id=task.id,
        triggered_at=now,
        message=f"Task '{task.task_name}' triggered — status set to running",
    )
