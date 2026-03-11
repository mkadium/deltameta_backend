from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.auth.dependencies import get_active_org_id, require_active_user
from app.auth.abac import require_permission
from app.auth.models import User
from app.govern.models import ServiceEndpoint


router = APIRouter(prefix="/service-endpoints", tags=["Connection Explorer"])


class DatabaseItem(BaseModel):
    name: str


class SchemaItem(BaseModel):
    name: str


class ObjectItem(BaseModel):
    name: str
    object_type: str  # table | view | materialized_view | other


class ColumnItem(BaseModel):
    name: str
    data_type: str
    is_nullable: bool
    ordinal_position: int


class TablePreview(BaseModel):
    schema: str
    table: str
    object_type: str
    columns: List[ColumnItem]


async def _get_connection_endpoint(
    db: AsyncSession,
    user: User,
    endpoint_id: uuid.UUID,
) -> ServiceEndpoint:
    org_id = get_active_org_id(user)
    obj = await db.get(ServiceEndpoint, endpoint_id)
    if not obj or obj.org_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service endpoint not found")
    return obj


def _build_pg_url_from_extra(extra: dict) -> Optional[str]:
    """
    Build an asyncpg-style URL from ServiceEndpoint.extra.

    Expected keys (convention):
      - host
      - port
      - user
      - password
      - database (optional for cluster-level ops)
    """
    host = extra.get("host")
    user = extra.get("user")
    password = extra.get("password")
    port = extra.get("port", 5432)
    database = extra.get("database")

    if not host or not user:
        return None

    if database:
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/postgres"


async def _get_ad_hoc_pg_session(
    endpoint: ServiceEndpoint,
    app_session: AsyncSession,
):
    """
    Create an ad-hoc AsyncSession bound to an external Postgres connection.

    For now, we reuse the existing engine infrastructure by creating a
    temporary engine via text() execution on the app_session's bind.
    This function assumes the PRIMARY DB is Postgres-compatible.
    """
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession as _AsyncSession
    from sqlalchemy.orm import sessionmaker as _sessionmaker

    url = _build_pg_url_from_extra(endpoint.extra or {})
    if not url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ServiceEndpoint.extra is missing required Postgres connection fields",
        )

    engine = create_async_engine(url, echo=False, future=True)
    SessionLocal = _sessionmaker(engine, class_=_AsyncSession, expire_on_commit=False)
    return engine, SessionLocal()


@router.get(
    "/{endpoint_id}/explore/databases",
    response_model=List[DatabaseItem],
    dependencies=[Depends(require_permission("service_endpoint", "read"))],
)
async def list_databases(
    endpoint_id: uuid.UUID = Path(..., description="ServiceEndpoint ID for the connection"),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """
    List databases for a Postgres-compatible ServiceEndpoint.

    For now, supports connections where extra contains host/user/password/port.
    """
    endpoint = await _get_connection_endpoint(db, user, endpoint_id)

    # We only support Postgres-like connections at the moment.
    if not endpoint.service_name.lower().startswith("postgres"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Connection explorer currently supports only Postgres-compatible endpoints",
        )

    engine, ext_session = await _get_ad_hoc_pg_session(endpoint, db)
    try:
        result = await ext_session.execute(
            text("SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname")
        )
        rows = result.mappings().all()
        return [DatabaseItem(name=row["datname"]) for row in rows]
    finally:
        await ext_session.close()
        await engine.dispose()


@router.get(
    "/{endpoint_id}/explore/{database}/schemas",
    response_model=List[SchemaItem],
    dependencies=[Depends(require_permission("service_endpoint", "read"))],
)
async def list_schemas(
    endpoint_id: uuid.UUID,
    database: str,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """List schemas in a given database for a Postgres-compatible endpoint."""
    endpoint = await _get_connection_endpoint(db, user, endpoint_id)
    extra = dict(endpoint.extra or {})
    extra["database"] = database

    engine, ext_session = await _get_ad_hoc_pg_session(
        ServiceEndpoint(
            id=endpoint.id,
            org_id=endpoint.org_id,
            service_name=endpoint.service_name,
            base_url=endpoint.base_url,
            extra=extra,
            is_active=endpoint.is_active,
        ),
        db,
    )
    try:
        result = await ext_session.execute(
            text(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE schema_name NOT IN ('pg_catalog', 'information_schema') "
                "ORDER BY schema_name"
            )
        )
        rows = result.mappings().all()
        return [SchemaItem(name=row["schema_name"]) for row in rows]
    finally:
        await ext_session.close()
        await engine.dispose()


@router.get(
    "/{endpoint_id}/explore/{database}/{schema}/objects",
    response_model=List[ObjectItem],
    dependencies=[Depends(require_permission("service_endpoint", "read"))],
)
async def list_objects(
    endpoint_id: uuid.UUID,
    database: str,
    schema: str,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """List tables/views/materialized views in a given schema."""
    endpoint = await _get_connection_endpoint(db, user, endpoint_id)
    extra = dict(endpoint.extra or {})
    extra["database"] = database

    engine, ext_session = await _get_ad_hoc_pg_session(
        ServiceEndpoint(
            id=endpoint.id,
            org_id=endpoint.org_id,
            service_name=endpoint.service_name,
            base_url=endpoint.base_url,
            extra=extra,
            is_active=endpoint.is_active,
        ),
        db,
    )
    try:
        # Tables and views
        result = await ext_session.execute(
            text(
                "SELECT table_name, table_type "
                "FROM information_schema.tables "
                "WHERE table_schema = :schema "
                "ORDER BY table_name"
            ),
            {"schema": schema},
        )
        rows = result.mappings().all()
        items: List[ObjectItem] = []
        for row in rows:
            table_type = row["table_type"] or ""
            if table_type.upper() == "BASE TABLE":
                obj_type = "table"
            elif table_type.upper() == "VIEW":
                obj_type = "view"
            else:
                obj_type = "other"
            items.append(ObjectItem(name=row["table_name"], object_type=obj_type))

        # Materialized views (Postgres-specific)
        mv_result = await ext_session.execute(
            text(
                "SELECT matviewname FROM pg_matviews WHERE schemaname = :schema "
                "ORDER BY matviewname"
            ),
            {"schema": schema},
        )
        for row in mv_result.mappings().all():
            items.append(ObjectItem(name=row["matviewname"], object_type="materialized_view"))

        return items
    finally:
        await ext_session.close()
        await engine.dispose()


@router.get(
    "/{endpoint_id}/explore/{database}/{schema}/{object_name}",
    response_model=TablePreview,
    dependencies=[Depends(require_permission("service_endpoint", "read"))],
)
async def get_object_schema(
    endpoint_id: uuid.UUID,
    database: str,
    schema: str,
    object_name: str,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Get schema metadata for a specific table/view/materialized view.

    Returns column names, data types, nullability, and ordinal positions.
    """
    endpoint = await _get_connection_endpoint(db, user, endpoint_id)
    extra = dict(endpoint.extra or {})
    extra["database"] = database

    engine, ext_session = await _get_ad_hoc_pg_session(
        ServiceEndpoint(
            id=endpoint.id,
            org_id=endpoint.org_id,
            service_name=endpoint.service_name,
            base_url=endpoint.base_url,
            extra=extra,
            is_active=endpoint.is_active,
        ),
        db,
    )
    try:
        # Determine object type (table/view/materialized_view)
        type_result = await ext_session.execute(
            text(
                "SELECT table_type FROM information_schema.tables "
                "WHERE table_schema = :schema AND table_name = :table"
            ),
            {"schema": schema, "table": object_name},
        )
        type_row = type_result.mappings().first()
        if type_row:
            table_type = type_row["table_type"] or ""
            if table_type.upper() == "BASE TABLE":
                obj_type = "table"
            elif table_type.upper() == "VIEW":
                obj_type = "view"
            else:
                obj_type = "other"
        else:
            # Try materialized view
            mv_result = await ext_session.execute(
                text(
                    "SELECT 1 FROM pg_matviews "
                    "WHERE schemaname = :schema AND matviewname = :table"
                ),
                {"schema": schema, "table": object_name},
            )
            if mv_result.mappings().first():
                obj_type = "materialized_view"
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Object not found in the specified schema",
                )

        col_result = await ext_session.execute(
            text(
                "SELECT column_name, data_type, is_nullable, ordinal_position "
                "FROM information_schema.columns "
                "WHERE table_schema = :schema AND table_name = :table "
                "ORDER BY ordinal_position"
            ),
            {"schema": schema, "table": object_name},
        )
        columns = [
            ColumnItem(
                name=row["column_name"],
                data_type=row["data_type"],
                is_nullable=(row["is_nullable"] == "YES"),
                ordinal_position=row["ordinal_position"],
            )
            for row in col_result.mappings().all()
        ]

        return TablePreview(
            schema=schema,
            table=object_name,
            object_type=obj_type,
            columns=columns,
        )
    finally:
        await ext_session.close()
        await engine.dispose()

