from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.auth.dependencies import get_active_org_id, require_active_user
from app.auth.abac import require_permission
from app.auth.models import User
from app.govern.models import CreateDatasetJob


router = APIRouter(prefix="/explore", tags=["Explore"])


class SourceType(str, Enum):
    connection = "connection"
    file_upload = "file_upload"
    file_in_storage = "file_in_storage"
    catalog_view = "catalog_view"
    pipeline_output = "pipeline_output"


class PipelineType(str, Enum):
    ingest = "ingest"
    sync = "sync"
    copy = "copy"
    spark_transform = "spark_transform"


class CreateDatasetJobStatus(str, Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"
    cancelled = "cancelled"


class CreateDatasetRequest(BaseModel):
    source_type: SourceType
    source_config: Dict[str, Any] = Field(
        ...,
        description="Opaque config for the source (connection_id, db/schema/object, bucket/key, etc.)",
    )
    dataset_id: Optional[uuid.UUID] = Field(
        None, description="Existing dataset to attach new asset under"
    )
    dataset_name: Optional[str] = Field(
        None,
        description="Optional dataset name if dataset_id is not provided (reserved for future use)",
    )
    asset_name: Optional[str] = Field(
        None,
        description="Optional asset name hint for the resulting DataAsset",
    )
    description: Optional[str] = None
    pipeline_type: PipelineType = Field(
        PipelineType.ingest,
        description="ingest | sync | copy | spark_transform",
    )
    sync_mode: Optional[str] = Field(
        "on_demand",
        description="Reserved for future scheduling integration (on_demand | scheduled)",
    )
    cron_expr: Optional[str] = Field(
        None,
        description="Cron expression when sync_mode=scheduled (not used yet)",
    )


class CreateDatasetJobOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    triggered_by: Optional[uuid.UUID]
    source_type: SourceType
    source_config: Dict[str, Any]
    dataset_id: Optional[uuid.UUID]
    asset_id: Optional[uuid.UUID]
    pipeline_type: PipelineType
    status: CreateDatasetJobStatus
    external_job_id: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class CreateDatasetResponse(BaseModel):
    job_id: uuid.UUID
    status: CreateDatasetJobStatus
    message: str


@router.post(
    "/create-dataset",
    response_model=CreateDatasetResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("explore", "create"))],
)
async def create_dataset_job(
    body: CreateDatasetRequest,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Create a unified 'Create in Data tab' job.

    This does not execute any pipelines yet. It simply records a job that
    downstream agents (e.g., Airflow, Spark, ingest bots) can act on.
    """
    org_id = get_active_org_id(user)

    job = CreateDatasetJob(
        org_id=org_id,
        triggered_by=user.id,
        source_type=body.source_type.value,
        source_config=body.source_config,
        dataset_id=body.dataset_id,
        pipeline_type=body.pipeline_type.value,
        status=CreateDatasetJobStatus.pending.value,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    return CreateDatasetResponse(
        job_id=job.id,
        status=CreateDatasetJobStatus(job.status),
        message="Create dataset job created. A downstream pipeline should process this job.",
    )


@router.get(
    "/create-dataset/jobs/{job_id}",
    response_model=CreateDatasetJobOut,
    dependencies=[Depends(require_permission("explore", "read"))],
)
async def get_create_dataset_job(
    job_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """Get a single CreateDatasetJob by ID (org-scoped)."""
    org_id = get_active_org_id(user)
    job = await db.get(CreateDatasetJob, job_id)
    if not job or job.org_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.get(
    "/create-dataset/jobs",
    response_model=List[CreateDatasetJobOut],
    dependencies=[Depends(require_permission("explore", "read"))],
)
async def list_create_dataset_jobs(
    status_filter: Optional[CreateDatasetJobStatus] = Query(
        None, alias="status", description="Filter by job status"
    ),
    source_type: Optional[SourceType] = Query(
        None, description="Filter by source_type"
    ),
    pipeline_type: Optional[PipelineType] = Query(
        None, description="Filter by pipeline_type"
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """List CreateDatasetJob records for the active org."""
    org_id = get_active_org_id(user)

    stmt = select(CreateDatasetJob).where(CreateDatasetJob.org_id == org_id)
    if status_filter:
        stmt = stmt.where(CreateDatasetJob.status == status_filter.value)
    if source_type:
        stmt = stmt.where(CreateDatasetJob.source_type == source_type.value)
    if pipeline_type:
        stmt = stmt.where(CreateDatasetJob.pipeline_type == pipeline_type.value)

    stmt = stmt.order_by(CreateDatasetJob.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()

