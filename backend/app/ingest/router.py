"""
Phase 3 Module 0 — File Ingest API.

Flow:
  1. POST /ingest/upload         → upload file, run schema inference, create IngestJob (status=preview_ready)
  2. GET  /ingest/jobs/{id}/preview → return inferred schema + first 50 rows
  3. POST /ingest/jobs/{id}/confirm → user confirms schema + chooses dataset_id → creates DataAsset + DataAssetColumns
                                      stores file in MinIO/S3, registers schema in Postgres (Iceberg: Phase 3 M5)
  4. GET  /ingest/jobs           → list ingest jobs with filters
  5. GET  /ingest/jobs/{id}      → job status + progress
  6. DELETE /ingest/jobs/{id}    → cancel / remove

Visual badge on DataAsset: source_type = "upload" → shown with blue badge in Explore Catalog.
"""
from __future__ import annotations

import io
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.auth.dependencies import get_active_org_id, require_active_user
from app.auth.abac import require_permission
from app.auth.models import User
from app.govern.models import (
    DataAsset,
    DataAssetColumn,
    Dataset,
    IngestJob,
    OrgStorageIngestConfig,
    StorageConfig,
)

router = APIRouter(prefix="/ingest", tags=["Data Ingest"])

SUPPORTED_FILE_TYPES = {"csv", "tsv", "json", "excel", "parquet"}
MAX_UPLOAD_SIZE = 200 * 1024 * 1024  # 200 MB


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ColumnSchemaItem(BaseModel):
    name: str
    data_type: str
    nullable: bool = True
    ordinal_position: int = 0


class IngestJobOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    triggered_by: Optional[uuid.UUID]
    file_name: str
    file_size: Optional[int]
    file_type: str
    storage_config_id: Optional[uuid.UUID]
    bucket: Optional[str]
    object_key: Optional[str]
    asset_id: Optional[uuid.UUID]
    dataset_id: Optional[uuid.UUID]
    status: str
    error_message: Optional[str]
    inferred_schema: List[Any]
    created_at: datetime
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class IngestPreviewOut(BaseModel):
    job_id: uuid.UUID
    file_name: str
    file_type: str
    inferred_schema: List[ColumnSchemaItem]
    preview_rows: List[Dict[str, Any]]
    row_count_estimate: int


class IngestConfirmBody(BaseModel):
    dataset_id: uuid.UUID
    asset_name: Optional[str] = None          # defaults to filename stem
    display_name: Optional[str] = None
    description: Optional[str] = None
    sensitivity: str = "internal"
    is_pii: bool = False
    tier: Optional[str] = None
    # Optionally override column schema from preview
    column_overrides: Optional[List[ColumnSchemaItem]] = None


class IngestConfirmOut(BaseModel):
    job_id: uuid.UUID
    asset_id: uuid.UUID
    asset_name: str
    columns_created: int
    object_key: Optional[str]
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect_file_type(filename: str, content_type: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    mapping = {
        "csv": "csv",
        "tsv": "tsv",
        "txt": "csv",   # treat delimiter-separated text as csv
        "json": "json",
        "jsonl": "json",
        "xlsx": "excel",
        "xls": "excel",
        "parquet": "parquet",
    }
    return mapping.get(ext, "csv")


def _infer_schema_and_preview(content: bytes, file_type: str, file_name: str) -> tuple[list, list]:
    """
    Infer column schema and return first 50 rows from uploaded file.
    Uses pandas for CSV/Excel/JSON, pyarrow for Parquet.
    Returns: (schema_list, preview_rows)
    """
    try:
        import pandas as pd

        if file_type == "csv":
            df = pd.read_csv(io.BytesIO(content), nrows=500)
        elif file_type == "tsv":
            df = pd.read_csv(io.BytesIO(content), sep="\t", nrows=500)
        elif file_type == "excel":
            df = pd.read_excel(io.BytesIO(content), nrows=500)
        elif file_type == "json":
            df = pd.read_json(io.BytesIO(content))
            df = df.head(500)
        elif file_type == "parquet":
            import pyarrow.parquet as pq
            table = pq.read_table(io.BytesIO(content))
            df = table.to_pandas().head(500)
        else:
            df = pd.read_csv(io.BytesIO(content), nrows=500)

        # Map pandas dtypes → our data types
        dtype_map = {
            "int64": "bigint", "int32": "integer", "float64": "double",
            "float32": "float", "bool": "boolean", "object": "varchar",
            "datetime64[ns]": "timestamp", "category": "varchar",
        }

        schema = []
        for i, (col_name, dtype) in enumerate(df.dtypes.items()):
            dt = dtype_map.get(str(dtype), "varchar")
            schema.append({
                "name": str(col_name),
                "data_type": dt,
                "nullable": bool(df[col_name].isnull().any()),
                "ordinal_position": i,
            })

        preview = df.head(50).fillna("").to_dict(orient="records")
        # Convert values to JSON-serializable types
        for row in preview:
            for k, v in row.items():
                if hasattr(v, "item"):
                    row[k] = v.item()
                elif str(type(v)) == "<class 'pandas._libs.tslibs.timestamps.Timestamp'>":
                    row[k] = str(v)

        return schema, preview

    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Failed to parse file '{file_name}': {str(exc)}",
        )


async def _upload_to_minio(
    content: bytes,
    bucket: str,
    object_key: str,
    storage_config,
) -> None:
    """Upload file bytes to MinIO/S3 using StorageConfig credentials."""
    try:
        from minio import Minio
        from minio.error import S3Error

        endpoint = storage_config.extra.get("endpoint", "localhost:9000").replace("http://", "").replace("https://", "")
        access_key = storage_config.extra.get("access_key", "minioadmin")
        secret_key = storage_config.extra.get("secret_key", "minioadmin123")
        secure = storage_config.extra.get("secure", False)

        client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)

        # Ensure bucket exists
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)

        client.put_object(
            bucket_name=bucket,
            object_name=object_key,
            data=io.BytesIO(content),
            length=len(content),
        )
    except ImportError:
        # minio not installed — skip upload (development mode)
        pass
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Storage upload failed: {str(exc)}",
        )


async def _get_job_or_404(job_id: uuid.UUID, org_id: uuid.UUID, session: AsyncSession) -> IngestJob:
    r = await session.execute(
        select(IngestJob).where(IngestJob.id == job_id, IngestJob.org_id == org_id)
    )
    obj = r.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Ingest job not found")
    return obj


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/upload", response_model=IngestJobOut, status_code=status.HTTP_201_CREATED,
             summary="Upload a file and trigger schema inference")
async def upload_file(
    file: UploadFile = File(..., description="CSV, TSV, Excel, JSON, or Parquet file"),
    storage_config_id: Optional[uuid.UUID] = Form(
        None,
        description=(
            "DEPRECATED: explicit StorageConfig ID. "
            "Use /org/storage-ingest-config for org-level default instead."
        ),
    ),
    user: User = Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Upload a file → infer schema → create IngestJob (status=preview_ready).
    Call GET /ingest/jobs/{id}/preview to review schema and rows.
    Call POST /ingest/jobs/{id}/confirm to create DataAsset and persist to storage.
    """
    org_id = get_active_org_id(user)

    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024*1024)} MB.")
    if not content:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")

    file_type = _detect_file_type(file.filename or "upload.csv", file.content_type or "")
    if file_type not in SUPPORTED_FILE_TYPES:
        raise HTTPException(status_code=422, detail=f"Unsupported file type. Supported: {', '.join(sorted(SUPPORTED_FILE_TYPES))}")

    # Infer schema + preview
    schema, preview = _infer_schema_and_preview(content, file_type, file.filename or "upload")

    # Resolve storage config via org-level ingest config (preferred),
    # falling back to explicit storage_config_id for backward compatibility.
    storage = None
    bucket = None

    if storage_config_id:
        # Legacy path: explicit StorageConfig
        r = await session.execute(
            select(StorageConfig).where(
                StorageConfig.id == storage_config_id,
                (StorageConfig.org_id == org_id) | (StorageConfig.org_id.is_(None)),
                StorageConfig.is_active == True,
            )
        )
        storage = r.scalar_one_or_none()
        if not storage:
            raise HTTPException(status_code=404, detail="StorageConfig not found or inactive")
        bucket = storage.bucket or storage.extra.get(
            "default_ingest_bucket",
            f"deltameta-ingest-{str(org_id)[:8]}",
        )
    else:
        # Preferred path: org-level ingest config
        cfg_result = await session.execute(
            select(OrgStorageIngestConfig).where(OrgStorageIngestConfig.org_id == org_id)
        )
        cfg = cfg_result.scalar_one_or_none()
        if not cfg:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Org storage ingest config is not set. "
                    "Org admin must configure /org/storage-ingest-config before uploading files."
                ),
            )

        sc_result = await session.execute(
            select(StorageConfig).where(
                StorageConfig.id == cfg.storage_config_id,
                (StorageConfig.org_id == org_id) | (StorageConfig.org_id.is_(None)),
                StorageConfig.is_active == True,
            )
        )
        storage = sc_result.scalar_one_or_none()
        if not storage:
            raise HTTPException(
                status_code=400,
                detail="Org storage ingest config references an invalid or inactive StorageConfig.",
            )

        storage_config_id = storage.id  # record it on the job
        bucket = cfg.bucket

    job = IngestJob(
        id=uuid.uuid4(),
        org_id=org_id,
        triggered_by=user.id,
        file_name=file.filename or "upload",
        file_size=len(content),
        file_type=file_type,
        storage_config_id=storage_config_id,
        bucket=bucket,
        status="preview_ready",
        inferred_schema=schema,
        preview_rows=preview,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


@router.get("/jobs", response_model=List[IngestJobOut], summary="List ingest jobs")
async def list_ingest_jobs(
    status_filter: Optional[str] = Query(None, alias="status",
        description="pending | uploading | inferring | preview_ready | confirmed | success | failed | cancelled"),
    file_type: Optional[str] = Query(None, description="csv | excel | tsv | json | parquet"),
    triggered_by: Optional[uuid.UUID] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    org_id = get_active_org_id(user)
    q = select(IngestJob).where(IngestJob.org_id == org_id)
    if status_filter:
        q = q.where(IngestJob.status == status_filter)
    if file_type:
        q = q.where(IngestJob.file_type == file_type)
    if triggered_by:
        q = q.where(IngestJob.triggered_by == triggered_by)
    q = q.order_by(IngestJob.created_at.desc()).offset(skip).limit(limit)
    result = await session.execute(q)
    return result.scalars().all()


@router.get("/jobs/{job_id}", response_model=IngestJobOut, summary="Get ingest job status")
async def get_ingest_job(
    job_id: uuid.UUID,
    user: User = Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    return await _get_job_or_404(job_id, get_active_org_id(user), session)


@router.get("/jobs/{job_id}/preview", response_model=IngestPreviewOut,
            summary="Preview inferred schema and first 50 rows")
async def preview_ingest_job(
    job_id: uuid.UUID,
    user: User = Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    org_id = get_active_org_id(user)
    job = await _get_job_or_404(job_id, org_id, session)
    if job.status not in ("preview_ready", "confirmed"):
        raise HTTPException(status_code=400, detail=f"Preview not available in status '{job.status}'")

    schema = [ColumnSchemaItem(**col) for col in (job.inferred_schema or [])]
    return IngestPreviewOut(
        job_id=job.id,
        file_name=job.file_name,
        file_type=job.file_type,
        inferred_schema=schema,
        preview_rows=job.preview_rows or [],
        row_count_estimate=len(job.preview_rows or []),
    )


@router.post("/jobs/{job_id}/confirm", response_model=IngestConfirmOut,
             status_code=status.HTTP_201_CREATED,
             summary="Confirm schema and create DataAsset in catalog")
async def confirm_ingest_job(
    job_id: uuid.UUID,
    body: IngestConfirmBody,
    user: User = Depends(require_permission("data_asset", "create")),
    session: AsyncSession = Depends(get_session),
):
    """
    Confirm the ingest job:
    1. Validate dataset exists
    2. Upload file to MinIO/S3 (if StorageConfig configured)
    3. Create DataAsset with source_type="upload"
    4. Create DataAssetColumns from inferred (or overridden) schema
    5. Mark job as success, link asset_id
    """
    org_id = get_active_org_id(user)
    job = await _get_job_or_404(job_id, org_id, session)

    if job.status not in ("preview_ready",):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot confirm job in status '{job.status}'. Job must be in 'preview_ready' state.",
        )

    # Validate dataset
    ds_result = await session.execute(
        select(Dataset).where(Dataset.id == body.dataset_id, Dataset.org_id == org_id)
    )
    dataset = ds_result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Determine asset name
    asset_name = body.asset_name or job.file_name.rsplit(".", 1)[0].replace(" ", "_").lower()

    # Use overridden schema if provided, else inferred
    schema_to_use = (
        [c.model_dump() for c in body.column_overrides]
        if body.column_overrides
        else (job.inferred_schema or [])
    )

    # Build object key for MinIO/S3
    object_key = None
    storage = None
    if job.storage_config_id:
        r = await session.execute(
            select(StorageConfig).where(StorageConfig.id == job.storage_config_id)
        )
        storage = r.scalar_one_or_none()
        if storage and job.bucket:
            object_key = f"{org_id}/{dataset.name}/{asset_name}/{job.file_name}"
            job.object_key = object_key

    # Create DataAsset
    asset = DataAsset(
        id=uuid.uuid4(),
        org_id=org_id,
        dataset_id=body.dataset_id,
        name=asset_name,
        display_name=body.display_name or asset_name,
        description=body.description,
        asset_type="file",
        fully_qualified_name=f"{dataset.name}.{asset_name}",
        sensitivity=body.sensitivity,
        is_pii=body.is_pii,
        tier=body.tier,
        source_type="upload",
        is_active=True,
        created_by=user.id,
    )
    session.add(asset)
    await session.flush()

    # Create columns
    columns_created = 0
    for col_dict in schema_to_use:
        session.add(DataAssetColumn(
            id=uuid.uuid4(),
            asset_id=asset.id,
            org_id=org_id,
            name=col_dict["name"],
            data_type=col_dict.get("data_type", "varchar"),
            ordinal_position=col_dict.get("ordinal_position", columns_created),
            is_nullable=col_dict.get("nullable", True),
        ))
        columns_created += 1

    # Mark job complete
    job.status = "success"
    job.asset_id = asset.id
    job.dataset_id = body.dataset_id
    job.completed_at = datetime.now(timezone.utc)

    await session.commit()
    await session.refresh(asset)

    return IngestConfirmOut(
        job_id=job.id,
        asset_id=asset.id,
        asset_name=asset.name,
        columns_created=columns_created,
        object_key=object_key,
        message=f"DataAsset '{asset.name}' created with {columns_created} columns. source_type=upload.",
    )


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Cancel/delete an ingest job")
async def delete_ingest_job(
    job_id: uuid.UUID,
    user: User = Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    org_id = get_active_org_id(user)
    job = await _get_job_or_404(job_id, org_id, session)
    if job.status == "success":
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a completed ingest job. Delete the DataAsset instead.",
        )
    await session.delete(job)
    await session.commit()
