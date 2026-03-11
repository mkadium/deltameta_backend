from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.auth.dependencies import get_active_org_id, require_active_user
from app.auth.abac import require_permission
from app.auth.models import User
from app.govern.models import ServiceEndpoint


router = APIRouter(prefix="/integrations/trino", tags=["Trino"])


class CatalogItem(BaseModel):
    name: str


class SchemaItem(BaseModel):
    name: str


class TableItem(BaseModel):
    name: str


class ColumnInfo(BaseModel):
    name: str
    type: str
    nullable: Optional[bool] = None


class TableDetail(BaseModel):
    catalog: str
    schema: str
    table: str
    columns: List[ColumnInfo]
    row_count: Optional[int] = None


class TrinoQueryRequest(BaseModel):
    sql: str = Field(..., description="SQL query to execute in Trino.")
    catalog: Optional[str] = Field(
        None, description="Optional catalog; sets X-Trino-Catalog header."
    )
    schema: Optional[str] = Field(
        None, description="Optional schema; sets X-Trino-Schema header."
    )
    limit: int = Field(
        100,
        ge=1,
        le=1000,
        description="Maximum number of rows to return (hard-capped at 1000).",
    )


class TrinoQueryResponse(BaseModel):
    columns: List[str]
    rows: List[List[Any]]


async def _get_trino_endpoint(
    db: AsyncSession,
    user: User,
    endpoint_id: Optional[uuid.UUID] = None,
) -> ServiceEndpoint:
    org_id = get_active_org_id(user)

    if endpoint_id:
        ep = await db.get(ServiceEndpoint, endpoint_id)
        if not ep or ep.org_id != org_id:
            raise HTTPException(status_code=404, detail="Trino endpoint not found")
        return ep

    stmt = select(ServiceEndpoint).where(
        ServiceEndpoint.org_id == org_id,
        ServiceEndpoint.service_name == "trino_ui",
        ServiceEndpoint.is_active == True,
    )
    result = await db.execute(stmt)
    eps = result.scalars().all()
    if not eps:
        raise HTTPException(
            status_code=404,
            detail="No active ServiceEndpoint with service_name='trino_ui' configured for this org.",
        )
    if len(eps) > 1:
        raise HTTPException(
            status_code=400,
            detail="Multiple trino_ui ServiceEndpoints configured; specify endpoint_id explicitly.",
        )
    return eps[0]


async def _trino_execute(
    ep: ServiceEndpoint,
    sql: str,
    catalog: Optional[str] = None,
    schema: Optional[str] = None,
    max_rows: int = 1000,
) -> Dict[str, Any]:
    """
    Execute a SQL statement against Trino and return aggregated results.

    Aggregates rows across pages up to max_rows.
    """
    base_url = ep.base_url.rstrip("/")
    url = f"{base_url}/v1/statement"

    user_name = (ep.extra or {}).get("user", "deltameta")
    headers = {
        "X-Trino-User": user_name,
    }
    if catalog:
        headers["X-Trino-Catalog"] = catalog
    if schema:
        headers["X-Trino-Schema"] = schema

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, headers=headers, content=sql.encode("utf-8"))
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Trino error: {resp.text}",
            )
        data = resp.json()

        columns = [col["name"] for col in data.get("columns", [])]
        rows: List[List[Any]] = []

        def _accumulate(page: Dict[str, Any]) -> None:
            nonlocal rows, columns
            if "columns" in page and not columns:
                columns = [col["name"] for col in page["columns"]]
            for r in page.get("data", []) or []:
                if len(rows) >= max_rows:
                    break
                rows.append(r)

        _accumulate(data)

        next_uri = data.get("nextUri")
        while next_uri and len(rows) < max_rows:
            next_resp = await client.get(next_uri)
            if next_resp.status_code >= 400:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Trino error on nextUri: {next_resp.text}",
                )
            page = next_resp.json()
            _accumulate(page)
            next_uri = page.get("nextUri")

        return {"columns": columns, "rows": rows}


async def _trino_get(
    ep: ServiceEndpoint,
    path: str,
) -> Dict[str, Any]:
    base_url = ep.base_url.rstrip("/")
    url = f"{base_url}{path}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Trino management error: {resp.text}",
            )
        return resp.json()


async def _trino_delete(
    ep: ServiceEndpoint,
    path: str,
) -> None:
    base_url = ep.base_url.rstrip("/")
    url = f"{base_url}{path}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.delete(url)
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Trino cancel error: {resp.text}",
            )


@router.get(
    "/catalogs",
    response_model=List[CatalogItem],
    dependencies=[Depends(require_permission("service_endpoint", "read"))],
)
async def list_catalogs(
    endpoint_id: Optional[uuid.UUID] = Query(
        None, description="Optional ServiceEndpoint ID; defaults to org's trino_ui."
    ),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    ep = await _get_trino_endpoint(db, user, endpoint_id)
    result = await _trino_execute(ep, "SHOW CATALOGS", max_rows=1000)
    return [CatalogItem(name=row[0]) for row in result["rows"]]


@router.get(
    "/catalogs/{catalog}/schemas",
    response_model=List[SchemaItem],
    dependencies=[Depends(require_permission("service_endpoint", "read"))],
)
async def list_schemas(
    catalog: str,
    endpoint_id: Optional[uuid.UUID] = Query(
        None, description="Optional ServiceEndpoint ID; defaults to org's trino_ui."
    ),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    ep = await _get_trino_endpoint(db, user, endpoint_id)
    sql = f"SHOW SCHEMAS FROM {catalog}"
    result = await _trino_execute(ep, sql, max_rows=1000)
    return [SchemaItem(name=row[0]) for row in result["rows"]]


@router.get(
    "/catalogs/{catalog}/{schema}/tables",
    response_model=List[TableItem],
    dependencies=[Depends(require_permission("service_endpoint", "read"))],
)
async def list_tables(
    catalog: str,
    schema: str,
    endpoint_id: Optional[uuid.UUID] = Query(
        None, description="Optional ServiceEndpoint ID; defaults to org's trino_ui."
    ),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    ep = await _get_trino_endpoint(db, user, endpoint_id)
    sql = f"SHOW TABLES FROM {catalog}.{schema}"
    result = await _trino_execute(ep, sql, max_rows=1000)
    return [TableItem(name=row[0]) for row in result["rows"]]


@router.get(
    "/catalogs/{catalog}/{schema}/{table}",
    response_model=TableDetail,
    dependencies=[Depends(require_permission("service_endpoint", "read"))],
)
async def get_table_detail(
    catalog: str,
    schema: str,
    table: str,
    include_stats: bool = Query(
        False,
        description="If true, also run COUNT(*) to estimate row count (may be slower).",
    ),
    endpoint_id: Optional[uuid.UUID] = Query(
        None, description="Optional ServiceEndpoint ID; defaults to org's trino_ui."
    ),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    ep = await _get_trino_endpoint(db, user, endpoint_id)

    # DESCRIBE to get column metadata
    describe_sql = f"DESCRIBE {catalog}.{schema}.{table}"
    describe_result = await _trino_execute(ep, describe_sql, max_rows=1000)

    cols: List[ColumnInfo] = []
    for row in describe_result["rows"]:
        # Trino DESCRIBE returns: Column, Type, Extra, Comment
        cols.append(
            ColumnInfo(
                name=row[0],
                type=row[1],
                nullable=None,
            )
        )

    row_count: Optional[int] = None
    if include_stats:
        count_sql = f"SELECT COUNT(*) FROM {catalog}.{schema}.{table}"
        count_result = await _trino_execute(ep, count_sql, max_rows=1)
        if count_result["rows"]:
            row_count = int(count_result["rows"][0][0])

    return TableDetail(
        catalog=catalog,
        schema=schema,
        table=table,
        columns=cols,
        row_count=row_count,
    )


@router.post(
    "/query",
    response_model=TrinoQueryResponse,
    dependencies=[Depends(require_permission("service_endpoint", "read"))],
)
async def run_query(
    body: TrinoQueryRequest,
    endpoint_id: Optional[uuid.UUID] = Query(
        None, description="Optional ServiceEndpoint ID; defaults to org's trino_ui."
    ),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    ep = await _get_trino_endpoint(db, user, endpoint_id)
    max_rows = min(body.limit, 1000)
    result = await _trino_execute(
        ep,
        body.sql,
        catalog=body.catalog,
        schema=body.schema,
        max_rows=max_rows,
    )
    return TrinoQueryResponse(columns=result["columns"], rows=result["rows"])


class TrinoQuerySummary(BaseModel):
    queryId: str
    state: Optional[str] = None
    query: Optional[str] = None
    user: Optional[str] = None
    source: Optional[str] = None
    catalog: Optional[str] = None
    schema: Optional[str] = None


@router.get(
    "/queries",
    response_model=List[TrinoQuerySummary],
    dependencies=[Depends(require_permission("service_endpoint", "read"))],
)
async def list_queries(
    endpoint_id: Optional[uuid.UUID] = Query(
        None, description="Optional ServiceEndpoint ID; defaults to org's trino_ui."
    ),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """
    List recent queries from Trino coordinator.
    """
    ep = await _get_trino_endpoint(db, user, endpoint_id)
    data = await _trino_get(ep, "/v1/query")
    items: List[TrinoQuerySummary] = []
    for q in data or []:
        items.append(
            TrinoQuerySummary(
                queryId=q.get("queryId") or q.get("id"),
                state=q.get("state"),
                query=q.get("query"),
                user=q.get("session", {}).get("user"),
                source=q.get("session", {}).get("source"),
                catalog=q.get("session", {}).get("catalog"),
                schema=q.get("session", {}).get("schema"),
            )
        )
    return items


@router.get(
    "/queries/{query_id}",
    response_model=TrinoQuerySummary,
    dependencies=[Depends(require_permission("service_endpoint", "read"))],
)
async def get_query(
    query_id: str,
    endpoint_id: Optional[uuid.UUID] = Query(
        None, description="Optional ServiceEndpoint ID; defaults to org's trino_ui."
    ),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Get status for a specific Trino query.
    """
    ep = await _get_trino_endpoint(db, user, endpoint_id)
    q = await _trino_get(ep, f"/v1/query/{query_id}")
    return TrinoQuerySummary(
        queryId=q.get("queryId") or q.get("id") or query_id,
        state=q.get("state"),
        query=q.get("query"),
        user=q.get("session", {}).get("user"),
        source=q.get("session", {}).get("source"),
        catalog=q.get("session", {}).get("catalog"),
        schema=q.get("session", {}).get("schema"),
    )


@router.delete(
    "/queries/{query_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("service_endpoint", "update"))],
)
async def cancel_query(
    query_id: str,
    endpoint_id: Optional[uuid.UUID] = Query(
        None, description="Optional ServiceEndpoint ID; defaults to org's trino_ui."
    ),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Cancel a running Trino query.
    """
    ep = await _get_trino_endpoint(db, user, endpoint_id)
    await _trino_delete(ep, f"/v1/query/{query_id}")

