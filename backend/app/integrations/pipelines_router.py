from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import get_session
from app.settings import settings
from app.govern.models import CreateDatasetJob, DataAsset


router = APIRouter(prefix="/integrations/pipelines", tags=["Pipelines"])


class PipelineCallbackStatus(str):
    SUCCESS = "success"
    FAILED = "failed"


class PipelineCallbackBody(BaseModel):
    job_id: uuid.UUID = Field(
        ..., description="CreateDatasetJob ID that this pipeline run corresponds to."
    )
    status: str = Field(
        ...,
        description="Pipeline run status: 'success' or 'failed'.",
    )
    output_asset_id: Optional[uuid.UUID] = Field(
        None,
        description="Optional DataAsset ID created by the pipeline.",
    )
    error_message: Optional[str] = Field(
        None,
        description="Error details if the pipeline failed.",
    )
    output_info: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional additional context (path, row_count, schema, etc.). Currently stored nowhere.",
    )


class PipelineCallbackResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    asset_id: Optional[uuid.UUID]
    completed_at: datetime


def _validate_pipeline_token(x_pipeline_token: Optional[str]) -> None:
    expected = getattr(settings, "pipeline_callback_token", None)
    if not expected:
        # Misconfiguration: callback token not set server-side
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Pipeline callback token is not configured on the server.",
        )
    if not x_pipeline_token or x_pipeline_token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing pipeline callback token.",
        )


@router.post(
    "/callback",
    response_model=PipelineCallbackResponse,
    summary="Callback endpoint for external pipelines to update CreateDatasetJob status.",
)
async def pipeline_callback(
    body: PipelineCallbackBody,
    x_pipeline_token: Optional[str] = Header(None, convert_underscores=True),
    db: AsyncSession = Depends(get_session),
):
    """
    External pipelines (Airflow, Spark, etc.) call this endpoint when a
    CreateDatasetJob completes. This endpoint:

      - Validates a shared callback token (X-Pipeline-Token header)
      - Updates the CreateDatasetJob status and completed_at
      - Optionally links an already-created DataAsset via output_asset_id

    It does *not* create DataAssets by itself.
    """
    _validate_pipeline_token(x_pipeline_token)

    job = await db.get(CreateDatasetJob, body.job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CreateDatasetJob not found",
        )

    now = datetime.utcnow()

    if body.status not in (PipelineCallbackStatus.SUCCESS, PipelineCallbackStatus.FAILED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="status must be 'success' or 'failed'",
        )

    job.status = body.status
    job.completed_at = now
    job.error_message = body.error_message

    if body.output_asset_id:
        # Ensure the referenced DataAsset exists before linking it
        result = await db.execute(
            select(DataAsset).where(DataAsset.id == body.output_asset_id)
        )
        asset = result.scalar_one_or_none()
        if not asset:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="output_asset_id does not reference an existing DataAsset",
            )
        job.asset_id = body.output_asset_id

    await db.commit()
    await db.refresh(job)

    return PipelineCallbackResponse(
        job_id=job.id,
        status=job.status,
        asset_id=job.asset_id,
        completed_at=job.completed_at or now,
    )

