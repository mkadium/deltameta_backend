"""
Search API — Phase 2 Module 6.

Implements full-text search across the catalog using PostgreSQL's
built-in tsvector / to_tsquery capabilities via UNION queries.

Covered entity types:
  • data_asset       — DataAsset (name, display_name, description, fully_qualified_name)
  • dataset          — Dataset
  • glossary_term    — GlossaryTerm
  • catalog_domain   — CatalogDomain
  • classification   — Classification
  • classification_tag — ClassificationTag
  • govern_metric    — GovernMetric

Endpoint:
  GET /search?q=&type=&domain_id=&owner_id=&is_pii=&sensitivity=&asset_type=&skip=&limit=

Response: unified list of SearchResult objects sorted by relevance score.

Phase 3 will replace the PG UNION backend with Elasticsearch/OpenSearch
while keeping the same API contract.
"""
from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import Float, Integer, cast, func, literal, select, text, union_all
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.auth.dependencies import get_active_org_id, require_active_user
from app.auth.abac import require_permission
from app.govern.models import (
    CatalogDomain,
    Classification,
    ClassificationTag,
    DataAsset,
    Dataset,
    GovernMetric,
)

try:
    from app.govern.models import GlossaryTerm
except ImportError:
    GlossaryTerm = None  # will skip if not present

router = APIRouter(prefix="/search", tags=["Search"])

VALID_TYPES = {
    "data_asset", "dataset", "glossary_term",
    "catalog_domain", "classification", "classification_tag", "govern_metric",
}


# ---------------------------------------------------------------------------
# Pydantic schema
# ---------------------------------------------------------------------------

class SearchResult(BaseModel):
    entity_type: str
    id: uuid.UUID
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    url_path: Optional[str] = None
    # extra context fields (populated per entity type where available)
    asset_type: Optional[str] = None
    sensitivity: Optional[str] = None
    is_pii: Optional[bool] = None
    score: float = 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts_rank(ts_col, query):
    """Return a ts_rank expression."""
    return func.ts_rank(ts_col, query)


def _to_tsvector(text_expr):
    # Cast the config name to regconfig so Postgres resolves the right overload
    return func.to_tsvector(text("'simple'::regconfig"), text_expr)


def _coalesce(*cols):
    return func.coalesce(*cols, "")


def _concat_ws(*cols):
    """Concatenate non-null columns with a space separator."""
    return func.concat_ws(" ", *cols)


# ---------------------------------------------------------------------------
# GET /search
# ---------------------------------------------------------------------------

@router.get("", response_model=List[SearchResult], summary="Full-text search across catalog entities")
async def search(
    q: str = Query(..., min_length=1, max_length=300, description="Search query"),
    type: Optional[str] = Query(None, description=f"Filter by entity type: {', '.join(sorted(VALID_TYPES))}"),
    domain_id: Optional[uuid.UUID] = Query(None, description="Filter DataAssets/Datasets by catalog domain"),
    owner_id: Optional[uuid.UUID] = Query(None, description="(reserved) Filter by owner user ID"),
    is_pii: Optional[bool] = Query(None, description="Filter DataAssets by PII flag"),
    sensitivity: Optional[str] = Query(None, description="Filter DataAssets by sensitivity (public|internal|confidential|restricted)"),
    asset_type: Optional[str] = Query(None, description="Filter DataAssets by asset_type (table|view|file|api_endpoint|stream)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user=Depends(require_permission("search", "read")),
    session: AsyncSession = Depends(get_session),
) -> List[SearchResult]:
    org_id = get_active_org_id(current_user)

    # Build the ts_query from user input (websearch_to_tsquery handles AND/OR/phrases naturally)
    # Cast config to regconfig to avoid type mismatch with asyncpg
    tsq = func.websearch_to_tsquery(text("'simple'::regconfig"), q)

    results: List[SearchResult] = []

    # Determine which types to query
    types_to_search = {type} if type and type in VALID_TYPES else VALID_TYPES

    # ── DataAsset ────────────────────────────────────────────────────────────
    if "data_asset" in types_to_search:
        text_col = _concat_ws(
            DataAsset.name, DataAsset.display_name,
            DataAsset.description, DataAsset.fully_qualified_name,
        )
        tsvec = _to_tsvector(text_col)
        q_da = (
            select(
                DataAsset.id.label("id"),
                DataAsset.name.label("name"),
                DataAsset.display_name.label("display_name"),
                DataAsset.description.label("description"),
                DataAsset.asset_type.label("asset_type"),
                DataAsset.sensitivity.label("sensitivity"),
                DataAsset.is_pii.label("is_pii"),
                _ts_rank(tsvec, tsq).label("score"),
            )
            .where(DataAsset.org_id == org_id)
            .where(tsvec.op("@@")(tsq))
        )
        if is_pii is not None:
            q_da = q_da.where(DataAsset.is_pii == is_pii)
        if sensitivity:
            q_da = q_da.where(DataAsset.sensitivity == sensitivity)
        if asset_type:
            q_da = q_da.where(DataAsset.asset_type == asset_type)
        rows = (await session.execute(q_da.order_by(func.ts_rank(tsvec, tsq).desc()).limit(limit + skip))).mappings().all()
        for row in rows:
            results.append(SearchResult(
                entity_type="data_asset",
                id=row["id"],
                name=row["name"],
                display_name=row.get("display_name"),
                description=row.get("description"),
                url_path=f"/catalog/data-assets/{row['id']}",
                asset_type=row.get("asset_type"),
                sensitivity=row.get("sensitivity"),
                is_pii=row.get("is_pii"),
                score=float(row["score"] or 0),
            ))

    # ── Dataset ──────────────────────────────────────────────────────────────
    if "dataset" in types_to_search:
        text_col = _concat_ws(Dataset.name, Dataset.display_name, Dataset.description)
        tsvec = _to_tsvector(text_col)
        q_ds = (
            select(
                Dataset.id.label("id"),
                Dataset.name.label("name"),
                Dataset.display_name.label("display_name"),
                Dataset.description.label("description"),
                _ts_rank(tsvec, tsq).label("score"),
            )
            .where(Dataset.org_id == org_id)
            .where(tsvec.op("@@")(tsq))
        )
        rows = (await session.execute(q_ds.order_by(func.ts_rank(tsvec, tsq).desc()).limit(limit + skip))).mappings().all()
        for row in rows:
            results.append(SearchResult(
                entity_type="dataset",
                id=row["id"],
                name=row["name"],
                display_name=row.get("display_name"),
                description=row.get("description"),
                url_path=f"/catalog/datasets/{row['id']}",
                score=float(row["score"] or 0),
            ))

    # ── CatalogDomain ────────────────────────────────────────────────────────
    if "catalog_domain" in types_to_search:
        text_col = _concat_ws(CatalogDomain.name, CatalogDomain.display_name, CatalogDomain.description)
        tsvec = _to_tsvector(text_col)
        q_cd = (
            select(
                CatalogDomain.id.label("id"),
                CatalogDomain.name.label("name"),
                CatalogDomain.display_name.label("display_name"),
                CatalogDomain.description.label("description"),
                _ts_rank(tsvec, tsq).label("score"),
            )
            .where(CatalogDomain.org_id == org_id)
            .where(tsvec.op("@@")(tsq))
        )
        rows = (await session.execute(q_cd.order_by(func.ts_rank(tsvec, tsq).desc()).limit(limit + skip))).mappings().all()
        for row in rows:
            results.append(SearchResult(
                entity_type="catalog_domain",
                id=row["id"],
                name=row["name"],
                display_name=row.get("display_name"),
                description=row.get("description"),
                url_path=f"/govern/domains/{row['id']}",
                score=float(row["score"] or 0),
            ))

    # ── Classification ────────────────────────────────────────────────────────
    if "classification" in types_to_search:
        text_col = _concat_ws(Classification.name, Classification.display_name, Classification.description)
        tsvec = _to_tsvector(text_col)
        q_cl = (
            select(
                Classification.id.label("id"),
                Classification.name.label("name"),
                Classification.display_name.label("display_name"),
                Classification.description.label("description"),
                _ts_rank(tsvec, tsq).label("score"),
            )
            .where(Classification.org_id == org_id)
            .where(tsvec.op("@@")(tsq))
        )
        rows = (await session.execute(q_cl.order_by(func.ts_rank(tsvec, tsq).desc()).limit(limit + skip))).mappings().all()
        for row in rows:
            results.append(SearchResult(
                entity_type="classification",
                id=row["id"],
                name=row["name"],
                display_name=row.get("display_name"),
                description=row.get("description"),
                url_path=f"/govern/classifications/{row['id']}",
                score=float(row["score"] or 0),
            ))

    # ── ClassificationTag ─────────────────────────────────────────────────────
    if "classification_tag" in types_to_search:
        text_col = _concat_ws(ClassificationTag.name, ClassificationTag.display_name, ClassificationTag.description)
        tsvec = _to_tsvector(text_col)
        q_ct = (
            select(
                ClassificationTag.id.label("id"),
                ClassificationTag.name.label("name"),
                ClassificationTag.display_name.label("display_name"),
                ClassificationTag.description.label("description"),
                _ts_rank(tsvec, tsq).label("score"),
            )
            .where(ClassificationTag.org_id == org_id)
            .where(tsvec.op("@@")(tsq))
        )
        rows = (await session.execute(q_ct.order_by(func.ts_rank(tsvec, tsq).desc()).limit(limit + skip))).mappings().all()
        for row in rows:
            results.append(SearchResult(
                entity_type="classification_tag",
                id=row["id"],
                name=row["name"],
                display_name=row.get("display_name"),
                description=row.get("description"),
                url_path=f"/govern/classifications/tags/{row['id']}",
                score=float(row["score"] or 0),
            ))

    # ── GovernMetric ──────────────────────────────────────────────────────────
    if "govern_metric" in types_to_search:
        text_col = _concat_ws(GovernMetric.name, GovernMetric.display_name, GovernMetric.description)
        tsvec = _to_tsvector(text_col)
        q_gm = (
            select(
                GovernMetric.id.label("id"),
                GovernMetric.name.label("name"),
                GovernMetric.display_name.label("display_name"),
                GovernMetric.description.label("description"),
                _ts_rank(tsvec, tsq).label("score"),
            )
            .where(GovernMetric.org_id == org_id)
            .where(tsvec.op("@@")(tsq))
        )
        rows = (await session.execute(q_gm.order_by(func.ts_rank(tsvec, tsq).desc()).limit(limit + skip))).mappings().all()
        for row in rows:
            results.append(SearchResult(
                entity_type="govern_metric",
                id=row["id"],
                name=row["name"],
                display_name=row.get("display_name"),
                description=row.get("description"),
                url_path=f"/govern/metrics/{row['id']}",
                score=float(row["score"] or 0),
            ))

    # ── GlossaryTerm ──────────────────────────────────────────────────────────
    if "glossary_term" in types_to_search and GlossaryTerm is not None:
        try:
            text_col = _concat_ws(
                GlossaryTerm.name, GlossaryTerm.display_name,
                GlossaryTerm.description,
            )
            tsvec = _to_tsvector(text_col)
            q_gt = (
                select(
                    GlossaryTerm.id.label("id"),
                    GlossaryTerm.name.label("name"),
                    GlossaryTerm.display_name.label("display_name"),
                    GlossaryTerm.description.label("description"),
                    _ts_rank(tsvec, tsq).label("score"),
                )
                .where(GlossaryTerm.org_id == org_id)
                .where(tsvec.op("@@")(tsq))
            )
            rows = (await session.execute(q_gt.order_by(func.ts_rank(tsvec, tsq).desc()).limit(limit + skip))).mappings().all()
            for row in rows:
                results.append(SearchResult(
                    entity_type="glossary_term",
                    id=row["id"],
                    name=row["name"],
                    display_name=row.get("display_name"),
                    description=row.get("description"),
                    url_path=f"/govern/glossary/{row['id']}",
                    score=float(row["score"] or 0),
                ))
        except Exception:
            pass  # skip if model not available

    # Sort all results by score desc, apply skip/limit
    results.sort(key=lambda r: r.score, reverse=True)
    return results[skip : skip + limit]


# ---------------------------------------------------------------------------
# GET /search/suggestions  — quick autocomplete (name prefix only)
# ---------------------------------------------------------------------------

@router.get(
    "/suggestions",
    response_model=List[SearchResult],
    summary="Quick autocomplete suggestions (prefix search on name)",
)
async def search_suggestions(
    q: str = Query(..., min_length=1, max_length=100),
    type: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=30),
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
) -> List[SearchResult]:
    """
    Fast prefix search using ILIKE on name field.
    Returns top N suggestions for autocomplete dropdowns.
    Does NOT use ABAC — any authenticated user can auto-complete.
    """
    org_id = get_active_org_id(current_user)
    pattern = f"{q}%"
    suggestions: List[SearchResult] = []

    types_to_search = {type} if type and type in VALID_TYPES else VALID_TYPES

    models_map = {
        "data_asset": (DataAsset, "/catalog/data-assets/{}"),
        "dataset": (Dataset, "/catalog/datasets/{}"),
        "catalog_domain": (CatalogDomain, "/govern/domains/{}"),
        "classification": (Classification, "/govern/classifications/{}"),
        "classification_tag": (ClassificationTag, "/govern/classifications/tags/{}"),
        "govern_metric": (GovernMetric, "/govern/metrics/{}"),
    }

    if GlossaryTerm is not None:
        models_map["glossary_term"] = (GlossaryTerm, "/govern/glossary/{}")

    per_type_limit = max(2, limit // len(types_to_search)) + 2

    for etype, (model, url_tpl) in models_map.items():
        if etype not in types_to_search:
            continue
        q_stmt = (
            select(model.id, model.name, model.display_name, model.description)
            .where(model.org_id == org_id, model.name.ilike(pattern))
            .limit(per_type_limit)
        )
        rows = (await session.execute(q_stmt)).mappings().all()
        for row in rows:
            suggestions.append(SearchResult(
                entity_type=etype,
                id=row["id"],
                name=row["name"],
                display_name=row.get("display_name"),
                description=row.get("description"),
                url_path=url_tpl.format(row["id"]),
            ))

    suggestions.sort(key=lambda r: r.name.lower())
    return suggestions[:limit]
