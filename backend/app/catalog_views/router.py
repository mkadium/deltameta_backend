from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.auth.dependencies import get_active_org_id, require_active_user
from app.auth.abac import require_permission
from app.auth.models import User
from app.govern.models import CatalogView, ServiceEndpoint


router = APIRouter(prefix="/catalog-views", tags=["Catalog Views"])


class CatalogViewBase(BaseModel):
    name: str = Field(..., max_length=255)
    display_name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    source_connection_id: Optional[uuid.UUID] = Field(
        None, description="ServiceEndpoint ID for the external connection"
    )
    source_schema: Optional[str] = Field(None, max_length=255)
    source_table: Optional[str] = Field(None, max_length=255)
    source_object_type: str = Field(
        "table",
        description="table | view | materialized_view",
    )
    tags: List[dict] = Field(default_factory=list)
    glossary_term_ids: List[uuid.UUID] = Field(default_factory=list)
    synonyms: List[str] = Field(default_factory=list)
    sync_mode: str = Field(
        "on_demand",
        description="on_demand | scheduled",
    )
    cron_expr: Optional[str] = Field(
        None,
        description="Cron expression when sync_mode=scheduled",
    )


class CatalogViewCreate(CatalogViewBase):
    pass


class CatalogViewUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    display_name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    tags: Optional[List[dict]] = None
    glossary_term_ids: Optional[List[uuid.UUID]] = None
    synonyms: Optional[List[str]] = None
    sync_mode: Optional[str] = Field(
        None,
        description="on_demand | scheduled",
    )
    cron_expr: Optional[str] = Field(
        None,
        description="Cron expression when sync_mode=scheduled",
    )


class CatalogViewOut(CatalogViewBase):
    id: uuid.UUID
    org_id: uuid.UUID
    asset_id: Optional[uuid.UUID]
    sync_status: str
    sync_error: Optional[str]
    last_synced_at: Optional[datetime]
    created_by: Optional[uuid.UUID]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


async def _assert_valid_source_object(
    db: AsyncSession,
    user: User,
    source_connection_id: Optional[uuid.UUID],
    source_schema: Optional[str],
    source_table: Optional[str],
) -> None:
    """
    Light validation that the referenced external object exists.

    For now, supports Postgres-compatible ServiceEndpoints only. If the
    ServiceEndpoint is not Postgres or schema/table are missing, this
    becomes a no-op (we don't block creation in that case).
    """
    if not source_connection_id or not source_schema or not source_table:
        return

    org_id = get_active_org_id(user)
    ep = await db.get(ServiceEndpoint, source_connection_id)
    if not ep or ep.org_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source_connection_id is not a valid ServiceEndpoint for this organization",
        )

    # Only attempt deep validation for Postgres-like endpoints.
    if not ep.service_name.lower().startswith("postgres"):
        return

    # Build ad-hoc connection URL from ServiceEndpoint.extra
    extra = ep.extra or {}
    host = extra.get("host")
    user_name = extra.get("user")
    password = extra.get("password")
    port = extra.get("port", 5432)
    database = extra.get("database")

    if not host or not user_name:
        # Missing connection details; skip deep validation but log via 400 to signal misconfig.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ServiceEndpoint.extra is missing required Postgres connection fields",
        )

    if not database:
        database = "postgres"

    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession as _AsyncSession
    from sqlalchemy.orm import sessionmaker as _sessionmaker

    url = f"postgresql+asyncpg://{user_name}:{password}@{host}:{port}/{database}"
    engine = create_async_engine(url, echo=False, future=True)
    SessionLocal = _sessionmaker(engine, class_=_AsyncSession, expire_on_commit=False)

    ext_session = SessionLocal()
    try:
        result = await ext_session.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = :schema AND table_name = :table"
            ),
            {"schema": source_schema, "table": source_table},
        )
        hit = result.scalar_one_or_none()
        if not hit:
            # Try materialized view
            mv_result = await ext_session.execute(
                text(
                    "SELECT 1 FROM pg_matviews "
                    "WHERE schemaname = :schema AND matviewname = :table"
                ),
                {"schema": source_schema, "table": source_table},
            )
            if not mv_result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Source object not found in external connection: "
                        f"{database}.{source_schema}.{source_table}"
                    ),
                )
    finally:
        await ext_session.close()
        await engine.dispose()


@router.get(
    "",
    response_model=List[CatalogViewOut],
    dependencies=[Depends(require_permission("catalog_view", "read"))],
)
async def list_catalog_views(
    source_connection_id: Optional[uuid.UUID] = Query(
        None, description="Filter by source connection (ServiceEndpoint ID)"
    ),
    sync_status: Optional[str] = Query(
        None, description="Filter by sync status: never | syncing | success | failed"
    ),
    source_object_type: Optional[str] = Query(
        None, description="Filter by source object type: table | view | materialized_view"
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """List Catalog Views for the active org."""
    org_id = get_active_org_id(user)

    stmt = select(CatalogView).where(CatalogView.org_id == org_id)
    if source_connection_id:
        stmt = stmt.where(CatalogView.source_connection_id == source_connection_id)
    if sync_status:
        stmt = stmt.where(CatalogView.sync_status == sync_status)
    if source_object_type:
        stmt = stmt.where(CatalogView.source_object_type == source_object_type)

    stmt = stmt.order_by(CatalogView.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post(
    "",
    response_model=CatalogViewOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("catalog_view", "create"))],
)
async def create_catalog_view(
    payload: CatalogViewCreate,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """Create a Catalog View from an external connection object."""
    org_id = get_active_org_id(user)

    await _assert_valid_source_object(
        db=db,
        user=user,
        source_connection_id=payload.source_connection_id,
        source_schema=payload.source_schema,
        source_table=payload.source_table,
    )

    cv = CatalogView(
        org_id=org_id,
        name=payload.name,
        display_name=payload.display_name,
        description=payload.description,
        source_connection_id=payload.source_connection_id,
        source_schema=payload.source_schema,
        source_table=payload.source_table,
        source_object_type=payload.source_object_type,
        tags=list(payload.tags or []),
        glossary_term_ids=list(payload.glossary_term_ids or []),
        synonyms=list(payload.synonyms or []),
        sync_mode=payload.sync_mode,
        cron_expr=payload.cron_expr,
        sync_status="never",
        created_by=user.id,
    )
    db.add(cv)
    await db.commit()
    await db.refresh(cv)
    return cv


@router.get(
    "/{catalog_view_id}",
    response_model=CatalogViewOut,
    dependencies=[Depends(require_permission("catalog_view", "read"))],
)
async def get_catalog_view(
    catalog_view_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """Get a single Catalog View."""
    org_id = get_active_org_id(user)
    cv = await db.get(CatalogView, catalog_view_id)
    if not cv or cv.org_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CatalogView not found")
    return cv


@router.put(
    "/{catalog_view_id}",
    response_model=CatalogViewOut,
    dependencies=[Depends(require_permission("catalog_view", "update"))],
)
async def update_catalog_view(
    catalog_view_id: uuid.UUID,
    payload: CatalogViewUpdate,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """Update a Catalog View (name, description, tags, sync config)."""
    org_id = get_active_org_id(user)
    cv = await db.get(CatalogView, catalog_view_id)
    if not cv or cv.org_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CatalogView not found")

    data = payload.model_dump(exclude_unset=True)

    # If source connection/schema/table are being changed, revalidate against external DB.
    src_conn_id = data.get("source_connection_id", cv.source_connection_id)
    src_schema = data.get("source_schema", cv.source_schema)
    src_table = data.get("source_table", cv.source_table)
    await _assert_valid_source_object(
        db=db,
        user=user,
        source_connection_id=src_conn_id,
        source_schema=src_schema,
        source_table=src_table,
    )

    for field, value in data.items():
        setattr(cv, field, value)

    await db.commit()
    await db.refresh(cv)
    return cv


@router.delete(
    "/{catalog_view_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("catalog_view", "delete"))],
)
async def delete_catalog_view(
    catalog_view_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """Delete a Catalog View."""
    org_id = get_active_org_id(user)
    cv = await db.get(CatalogView, catalog_view_id)
    if not cv or cv.org_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CatalogView not found")

    await db.delete(cv)
    await db.commit()


class CatalogViewSyncResponse(BaseModel):
    id: uuid.UUID
    sync_status: str
    message: str


@router.post(
    "/{catalog_view_id}/sync",
    response_model=CatalogViewSyncResponse,
    dependencies=[Depends(require_permission("catalog_view", "update"))],
)
async def trigger_catalog_view_sync(
    catalog_view_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Trigger an on-demand sync for a Catalog View.

    For now, this marks the sync_status as 'syncing'; an external agent
    (e.g. catalog_view_sync bot) should perform the actual sync and
    update the row to 'success' or 'failed'.
    """
    org_id = get_active_org_id(user)
    cv = await db.get(CatalogView, catalog_view_id)
    if not cv or cv.org_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CatalogView not found")

    cv.sync_status = "syncing"
    cv.sync_error = None
    await db.commit()
    await db.refresh(cv)

    return CatalogViewSyncResponse(
        id=cv.id,
        sync_status=cv.sync_status,
        message="Sync requested; a background agent should process this Catalog View.",
    )


class CatalogViewSyncHistoryItem(BaseModel):
    timestamp: datetime
    status: str
    message: Optional[str] = None


@router.get(
    "/{catalog_view_id}/sync-history",
    response_model=List[CatalogViewSyncHistoryItem],
    dependencies=[Depends(require_permission("catalog_view", "read"))],
)
async def get_catalog_view_sync_history(
    catalog_view_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Return basic sync history for a Catalog View.

    For now, we surface a minimal synthetic history using the last_synced_at
    and sync_status fields. When a dedicated history table is introduced,
    this endpoint can be updated to return real entries.
    """
    org_id = get_active_org_id(user)
    cv = await db.get(CatalogView, catalog_view_id)
    if not cv or cv.org_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CatalogView not found")

    items: List[CatalogViewSyncHistoryItem] = []
    if cv.last_synced_at:
        items.append(
            CatalogViewSyncHistoryItem(
                timestamp=cv.last_synced_at,
                status=cv.sync_status,
                message=cv.sync_error,
            )
        )
    return items

