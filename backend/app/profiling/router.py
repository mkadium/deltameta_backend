"""
Data Profiling API — Phase 2 Module 2.

Profiling captures statistical metadata about a data asset and each of its columns.
One "profile run" = one DataAssetProfile row + N ColumnProfile rows (one per column).

Endpoints:
  POST   /data-assets/{asset_id}/profile               Trigger a new profiling run
  GET    /data-assets/{asset_id}/profiles              List all profile runs (paginated)
  GET    /data-assets/{asset_id}/profiles/latest       Latest successful run + column profiles
  GET    /data-assets/{asset_id}/profiles/{profile_id} Specific run detail + column profiles

  GET    /profiles                                     List profiles across org (filter: asset_id, status, triggered_by)
  GET    /profiles/{profile_id}                        Get profile by ID (any asset in org)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.auth.dependencies import get_active_org_id, require_active_user
from app.auth.abac import require_permission
from app.govern.models import DataAsset, DataAssetProfile, ColumnProfile, DataAssetColumn

router = APIRouter(tags=["Data Profiling"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ColumnProfileOut(BaseModel):
    id: uuid.UUID
    profile_id: uuid.UUID
    column_id: Optional[uuid.UUID] = None
    asset_id: uuid.UUID
    column_name: str
    data_type: Optional[str] = None
    null_count: Optional[int] = None
    null_pct: Optional[float] = None
    distinct_count: Optional[int] = None
    min_val: Optional[str] = None
    max_val: Optional[str] = None
    mean_val: Optional[float] = None
    stddev_val: Optional[float] = None
    top_values: List[Dict[str, Any]] = []
    histogram: List[Dict[str, Any]] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class DataAssetProfileOut(BaseModel):
    id: uuid.UUID
    asset_id: uuid.UUID
    org_id: uuid.UUID
    triggered_by: Optional[uuid.UUID] = None
    status: str
    row_count: Optional[int] = None
    profile_data: Dict[str, Any] = {}
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    column_profiles: List[ColumnProfileOut] = []

    model_config = {"from_attributes": True}


class ProfileTriggerResponse(BaseModel):
    profile_id: uuid.UUID
    asset_id: uuid.UUID
    status: str
    message: str


class ColumnProfileInput(BaseModel):
    column_name: str
    data_type: Optional[str] = None
    null_count: Optional[int] = None
    null_pct: Optional[float] = None
    distinct_count: Optional[int] = None
    min_val: Optional[str] = None
    max_val: Optional[str] = None
    mean_val: Optional[float] = None
    stddev_val: Optional[float] = None
    top_values: List[Dict[str, Any]] = []
    histogram: List[Dict[str, Any]] = []


class ProfileSubmitBody(BaseModel):
    """
    Optional body when submitting profile results directly (e.g. from an external profiler bot).
    If not provided the profile stays in 'pending' status for a background worker to fill in.
    """
    row_count: Optional[int] = None
    profile_data: Dict[str, Any] = {}
    column_profiles: List[ColumnProfileInput] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_asset_or_404(asset_id: uuid.UUID, org_id: uuid.UUID, session: AsyncSession) -> DataAsset:
    result = await session.execute(
        select(DataAsset).where(DataAsset.id == asset_id, DataAsset.org_id == org_id)
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data asset not found")
    return asset


async def _get_profile_or_404(profile_id: uuid.UUID, org_id: uuid.UUID, session: AsyncSession) -> DataAssetProfile:
    result = await session.execute(
        select(DataAssetProfile)
        .where(DataAssetProfile.id == profile_id, DataAssetProfile.org_id == org_id)
        .options(selectinload(DataAssetProfile.column_profiles))
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile


async def _resolve_column_id(
    asset_id: uuid.UUID, column_name: str, session: AsyncSession
) -> Optional[uuid.UUID]:
    result = await session.execute(
        select(DataAssetColumn).where(
            DataAssetColumn.asset_id == asset_id,
            DataAssetColumn.name == column_name,
        )
    )
    col = result.scalar_one_or_none()
    return col.id if col else None


# ---------------------------------------------------------------------------
# POST /data-assets/{asset_id}/profile  — trigger a profiling run
# ---------------------------------------------------------------------------

@router.post(
    "/data-assets/{asset_id}/profile",
    response_model=ProfileTriggerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Trigger a profiling run for a data asset",
)
async def trigger_profile(
    asset_id: uuid.UUID,
    body: ProfileSubmitBody = ProfileSubmitBody(),
    current_user=Depends(require_permission("data_profile", "create")),
    session: AsyncSession = Depends(get_session),
):
    """
    Create a new DataAssetProfile run.

    - If `column_profiles` are provided in the body (e.g. submitted by a profiler bot),
      the profile is immediately marked **success** and column stats are persisted.
    - If the body is empty the profile is created in **pending** status,
      ready for a background worker / profiler bot to fill in via PUT later.
    """
    org_id = get_active_org_id(current_user)
    await _get_asset_or_404(asset_id, org_id, session)

    now = datetime.now(timezone.utc)
    has_data = body.row_count is not None or bool(body.column_profiles)

    profile = DataAssetProfile(
        id=uuid.uuid4(),
        asset_id=asset_id,
        org_id=org_id,
        triggered_by=current_user.id,
        status="success" if has_data else "pending",
        row_count=body.row_count,
        profile_data=body.profile_data,
        started_at=now if has_data else None,
        completed_at=now if has_data else None,
    )
    session.add(profile)
    await session.flush()  # get profile.id before inserting column profiles

    for cp_input in body.column_profiles:
        col_id = await _resolve_column_id(asset_id, cp_input.column_name, session)
        session.add(ColumnProfile(
            id=uuid.uuid4(),
            profile_id=profile.id,
            column_id=col_id,
            asset_id=asset_id,
            org_id=org_id,
            column_name=cp_input.column_name,
            data_type=cp_input.data_type,
            null_count=cp_input.null_count,
            null_pct=cp_input.null_pct,
            distinct_count=cp_input.distinct_count,
            min_val=cp_input.min_val,
            max_val=cp_input.max_val,
            mean_val=cp_input.mean_val,
            stddev_val=cp_input.stddev_val,
            top_values=cp_input.top_values,
            histogram=cp_input.histogram,
        ))

    await session.commit()

    return ProfileTriggerResponse(
        profile_id=profile.id,
        asset_id=asset_id,
        status=profile.status,
        message="Profiling run created successfully" if has_data else "Profiling run queued — awaiting worker",
    )


# ---------------------------------------------------------------------------
# GET /data-assets/{asset_id}/profiles  — list runs
# ---------------------------------------------------------------------------

@router.get(
    "/data-assets/{asset_id}/profiles",
    response_model=List[DataAssetProfileOut],
    summary="List profiling runs for a data asset",
)
async def list_profiles(
    asset_id: uuid.UUID,
    profile_status: Optional[str] = Query(None, alias="status", description="Filter: pending | running | success | failed"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    org_id = get_active_org_id(current_user)
    await _get_asset_or_404(asset_id, org_id, session)

    q = (
        select(DataAssetProfile)
        .where(DataAssetProfile.asset_id == asset_id, DataAssetProfile.org_id == org_id)
        .options(selectinload(DataAssetProfile.column_profiles))
        .order_by(DataAssetProfile.created_at.desc())
    )
    if profile_status:
        q = q.where(DataAssetProfile.status == profile_status)
    q = q.offset(skip).limit(limit)

    result = await session.execute(q)
    return result.scalars().all()


# ---------------------------------------------------------------------------
# GET /data-assets/{asset_id}/profiles/latest  — latest successful run
# ---------------------------------------------------------------------------

@router.get(
    "/data-assets/{asset_id}/profiles/latest",
    response_model=DataAssetProfileOut,
    summary="Get latest successful profile run for a data asset",
)
async def get_latest_profile(
    asset_id: uuid.UUID,
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    org_id = get_active_org_id(current_user)
    await _get_asset_or_404(asset_id, org_id, session)

    result = await session.execute(
        select(DataAssetProfile)
        .where(
            DataAssetProfile.asset_id == asset_id,
            DataAssetProfile.org_id == org_id,
            DataAssetProfile.status == "success",
        )
        .options(selectinload(DataAssetProfile.column_profiles))
        .order_by(DataAssetProfile.created_at.desc())
        .limit(1)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No successful profile run found for this asset",
        )
    return profile


# ---------------------------------------------------------------------------
# GET /data-assets/{asset_id}/profiles/{profile_id}  — specific run detail
# ---------------------------------------------------------------------------

@router.get(
    "/data-assets/{asset_id}/profiles/{profile_id}",
    response_model=DataAssetProfileOut,
    summary="Get a specific profiling run",
)
async def get_profile(
    asset_id: uuid.UUID,
    profile_id: uuid.UUID,
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    org_id = get_active_org_id(current_user)
    await _get_asset_or_404(asset_id, org_id, session)

    result = await session.execute(
        select(DataAssetProfile)
        .where(
            DataAssetProfile.id == profile_id,
            DataAssetProfile.asset_id == asset_id,
            DataAssetProfile.org_id == org_id,
        )
        .options(selectinload(DataAssetProfile.column_profiles))
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile


# ---------------------------------------------------------------------------
# PUT /data-assets/{asset_id}/profiles/{profile_id}  — update / complete run
# ---------------------------------------------------------------------------

class ProfileUpdateBody(BaseModel):
    """Used by profiler bots to write results back into a pending profile run."""
    status: Optional[str] = None          # running | success | failed
    row_count: Optional[int] = None
    profile_data: Optional[Dict[str, Any]] = None
    column_profiles: Optional[List[ColumnProfileInput]] = None


@router.put(
    "/data-assets/{asset_id}/profiles/{profile_id}",
    response_model=DataAssetProfileOut,
    summary="Update a profiling run (used by profiler bot to write results)",
)
async def update_profile(
    asset_id: uuid.UUID,
    profile_id: uuid.UUID,
    body: ProfileUpdateBody,
    current_user=Depends(require_permission("data_profile", "update")),
    session: AsyncSession = Depends(get_session),
):
    org_id = get_active_org_id(current_user)
    await _get_asset_or_404(asset_id, org_id, session)

    result = await session.execute(
        select(DataAssetProfile)
        .where(
            DataAssetProfile.id == profile_id,
            DataAssetProfile.asset_id == asset_id,
            DataAssetProfile.org_id == org_id,
        )
        .options(selectinload(DataAssetProfile.column_profiles))
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    now = datetime.now(timezone.utc)

    if body.status is not None:
        valid_statuses = {"pending", "running", "success", "failed"}
        if body.status not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"status must be one of: {sorted(valid_statuses)}",
            )
        if body.status == "running" and not profile.started_at:
            profile.started_at = now
        if body.status in ("success", "failed"):
            profile.completed_at = now
        profile.status = body.status

    if body.row_count is not None:
        profile.row_count = body.row_count
    if body.profile_data is not None:
        profile.profile_data = body.profile_data

    if body.column_profiles is not None:
        # Delete existing column profiles via direct DELETE query (bypasses ORM cache)
        await session.execute(
            ColumnProfile.__table__.delete().where(ColumnProfile.profile_id == profile.id)
        )
        await session.flush()
        for cp_input in body.column_profiles:
            col_id = await _resolve_column_id(asset_id, cp_input.column_name, session)
            session.add(ColumnProfile(
                id=uuid.uuid4(),
                profile_id=profile.id,
                column_id=col_id,
                asset_id=asset_id,
                org_id=org_id,
                column_name=cp_input.column_name,
                data_type=cp_input.data_type,
                null_count=cp_input.null_count,
                null_pct=cp_input.null_pct,
                distinct_count=cp_input.distinct_count,
                min_val=cp_input.min_val,
                max_val=cp_input.max_val,
                mean_val=cp_input.mean_val,
                stddev_val=cp_input.stddev_val,
                top_values=cp_input.top_values,
                histogram=cp_input.histogram,
            ))

    await session.commit()
    # Expire all cached ORM state so the re-fetch sees the fresh column_profiles
    session.expire_all()
    result = await session.execute(
        select(DataAssetProfile)
        .where(DataAssetProfile.id == profile_id)
        .options(selectinload(DataAssetProfile.column_profiles))
    )
    return result.scalar_one()


# ---------------------------------------------------------------------------
# DELETE /data-assets/{asset_id}/profiles/{profile_id}
# ---------------------------------------------------------------------------

@router.delete(
    "/data-assets/{asset_id}/profiles/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a profiling run",
)
async def delete_profile(
    asset_id: uuid.UUID,
    profile_id: uuid.UUID,
    current_user=Depends(require_permission("data_profile", "delete")),
    session: AsyncSession = Depends(get_session),
):
    org_id = get_active_org_id(current_user)
    await _get_asset_or_404(asset_id, org_id, session)

    result = await session.execute(
        select(DataAssetProfile).where(
            DataAssetProfile.id == profile_id,
            DataAssetProfile.asset_id == asset_id,
            DataAssetProfile.org_id == org_id,
        )
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    await session.delete(profile)
    await session.commit()


# ---------------------------------------------------------------------------
# Org-wide profile listing
# ---------------------------------------------------------------------------

@router.get(
    "/profiles",
    response_model=List[DataAssetProfileOut],
    summary="List all profile runs across the org",
)
async def list_all_profiles(
    asset_id: Optional[uuid.UUID] = Query(None, description="Filter by data asset"),
    profile_status: Optional[str] = Query(None, alias="status", description="Filter by status"),
    triggered_by: Optional[uuid.UUID] = Query(None, description="Filter by user who triggered"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    org_id = get_active_org_id(current_user)
    q = (
        select(DataAssetProfile)
        .where(DataAssetProfile.org_id == org_id)
        .options(selectinload(DataAssetProfile.column_profiles))
        .order_by(DataAssetProfile.created_at.desc())
    )
    if asset_id:
        q = q.where(DataAssetProfile.asset_id == asset_id)
    if profile_status:
        q = q.where(DataAssetProfile.status == profile_status)
    if triggered_by:
        q = q.where(DataAssetProfile.triggered_by == triggered_by)
    q = q.offset(skip).limit(limit)
    result = await session.execute(q)
    return result.scalars().all()


@router.get(
    "/profiles/{profile_id}",
    response_model=DataAssetProfileOut,
    summary="Get a profile run by ID (org-scoped)",
)
async def get_profile_by_id(
    profile_id: uuid.UUID,
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    return await _get_profile_or_404(profile_id, get_active_org_id(current_user), session)
