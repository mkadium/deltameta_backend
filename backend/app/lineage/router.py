"""
Data Lineage API — Phase 2 Module 3.

Tracks directed edges between data assets, forming a lineage graph.
Each edge represents data flowing FROM a source asset TO a target asset.

Endpoints:
  POST   /lineage                            Create an edge (source → target)
  GET    /lineage                            List all edges (filters: source, target, edge_type)
  DELETE /lineage/{edge_id}                  Remove an edge

  GET    /lineage/{asset_id}/upstream        All assets that feed INTO this asset (recursive)
  GET    /lineage/{asset_id}/downstream      All assets this asset feeds INTO (recursive)
  GET    /lineage/{asset_id}/graph           Full graph for UI visualisation (nodes + edges)
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.auth.dependencies import get_active_org_id, require_active_user
from app.auth.abac import require_permission
from app.govern.models import DataAsset, LineageEdge

router = APIRouter(prefix="/lineage", tags=["Data Lineage"])

VALID_EDGE_TYPES = {"direct", "derived", "copy", "aggregated"}

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class LineageEdgeCreate(BaseModel):
    source_asset_id: uuid.UUID
    target_asset_id: uuid.UUID
    edge_type: str = "direct"
    transformation: Optional[str] = None

    @model_validator(mode="after")
    def check_no_self_loop(self) -> "LineageEdgeCreate":
        if self.source_asset_id == self.target_asset_id:
            raise ValueError("source_asset_id and target_asset_id must be different")
        if self.edge_type not in VALID_EDGE_TYPES:
            raise ValueError(f"edge_type must be one of: {sorted(VALID_EDGE_TYPES)}")
        return self


class AssetRef(BaseModel):
    id: uuid.UUID
    name: str
    display_name: Optional[str] = None
    asset_type: str
    fully_qualified_name: Optional[str] = None

    model_config = {"from_attributes": True}


class LineageEdgeOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    source_asset_id: uuid.UUID
    target_asset_id: uuid.UUID
    edge_type: str
    transformation: Optional[str] = None
    created_by: Optional[uuid.UUID] = None
    created_at: datetime
    source_asset: Optional[AssetRef] = None
    target_asset: Optional[AssetRef] = None

    model_config = {"from_attributes": True}


class LineageNodeOut(BaseModel):
    id: uuid.UUID
    name: str
    display_name: Optional[str] = None
    asset_type: str
    fully_qualified_name: Optional[str] = None
    depth: int = 0          # hops from the queried asset (0 = the asset itself)
    direction: str = "self" # upstream | downstream | self


class LineageGraphOut(BaseModel):
    asset_id: uuid.UUID
    nodes: List[LineageNodeOut]
    edges: List[LineageEdgeOut]


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


async def _get_edge_or_404(edge_id: uuid.UUID, org_id: uuid.UUID, session: AsyncSession) -> LineageEdge:
    result = await session.execute(
        select(LineageEdge).where(LineageEdge.id == edge_id, LineageEdge.org_id == org_id)
    )
    edge = result.scalar_one_or_none()
    if not edge:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lineage edge not found")
    return edge


def _asset_to_ref(asset: DataAsset) -> AssetRef:
    return AssetRef(
        id=asset.id,
        name=asset.name,
        display_name=asset.display_name,
        asset_type=asset.asset_type,
        fully_qualified_name=asset.fully_qualified_name,
    )


def _edge_to_out(edge: LineageEdge) -> LineageEdgeOut:
    return LineageEdgeOut(
        id=edge.id,
        org_id=edge.org_id,
        source_asset_id=edge.source_asset_id,
        target_asset_id=edge.target_asset_id,
        edge_type=edge.edge_type,
        transformation=edge.transformation,
        created_by=edge.created_by,
        created_at=edge.created_at,
        source_asset=_asset_to_ref(edge.source_asset) if edge.source_asset else None,
        target_asset=_asset_to_ref(edge.target_asset) if edge.target_asset else None,
    )


async def _load_all_org_edges(org_id: uuid.UUID, session: AsyncSession) -> List[LineageEdge]:
    """Load all lineage edges for the org — used for graph traversal."""
    result = await session.execute(
        select(LineageEdge).where(LineageEdge.org_id == org_id)
    )
    return result.scalars().all()


async def _traverse(
    start_id: uuid.UUID,
    org_id: uuid.UUID,
    direction: str,   # "upstream" or "downstream"
    session: AsyncSession,
    max_depth: int = 20,
) -> List[Dict[str, Any]]:
    """
    BFS traversal of the lineage graph.
    direction='upstream'   → follow edges WHERE target_asset_id = current → collect source_asset_id
    direction='downstream' → follow edges WHERE source_asset_id = current → collect target_asset_id
    Returns list of {asset_id, depth}.
    """
    all_edges = await _load_all_org_edges(org_id, session)

    # Build adjacency maps
    # upstream: target → list of sources
    # downstream: source → list of targets
    upstream_map: Dict[uuid.UUID, List[uuid.UUID]] = {}
    downstream_map: Dict[uuid.UUID, List[uuid.UUID]] = {}
    for e in all_edges:
        downstream_map.setdefault(e.source_asset_id, []).append(e.target_asset_id)
        upstream_map.setdefault(e.target_asset_id, []).append(e.source_asset_id)

    adj = upstream_map if direction == "upstream" else downstream_map

    visited: Set[uuid.UUID] = set()
    queue: List[tuple[uuid.UUID, int]] = [(start_id, 0)]
    result_nodes: List[Dict[str, Any]] = []

    while queue:
        current_id, depth = queue.pop(0)
        if current_id in visited or depth > max_depth:
            continue
        visited.add(current_id)
        if current_id != start_id:
            result_nodes.append({"asset_id": current_id, "depth": depth, "direction": direction})
        for neighbor_id in adj.get(current_id, []):
            if neighbor_id not in visited:
                queue.append((neighbor_id, depth + 1))

    return result_nodes


# ---------------------------------------------------------------------------
# POST /lineage — create edge
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=LineageEdgeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a lineage edge (source → target)",
)
async def create_edge(
    body: LineageEdgeCreate,
    current_user=Depends(require_permission("lineage", "create")),
    session: AsyncSession = Depends(get_session),
):
    org_id = get_active_org_id(current_user)

    # Validate both assets exist in this org
    await _get_asset_or_404(body.source_asset_id, org_id, session)
    await _get_asset_or_404(body.target_asset_id, org_id, session)

    # Check duplicate
    existing = await session.execute(
        select(LineageEdge).where(
            LineageEdge.org_id == org_id,
            LineageEdge.source_asset_id == body.source_asset_id,
            LineageEdge.target_asset_id == body.target_asset_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Lineage edge already exists between these two assets",
        )

    edge = LineageEdge(
        id=uuid.uuid4(),
        org_id=org_id,
        source_asset_id=body.source_asset_id,
        target_asset_id=body.target_asset_id,
        edge_type=body.edge_type,
        transformation=body.transformation,
        created_by=current_user.id,
    )
    session.add(edge)
    await session.commit()

    # Reload with relationships
    result = await session.execute(
        select(LineageEdge).where(LineageEdge.id == edge.id)
    )
    edge = result.scalar_one()
    # Eagerly load asset refs
    await session.refresh(edge, ["source_asset", "target_asset"])
    return _edge_to_out(edge)


# ---------------------------------------------------------------------------
# GET /lineage — list edges
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=List[LineageEdgeOut],
    summary="List lineage edges (filterable)",
)
async def list_edges(
    source_asset_id: Optional[uuid.UUID] = Query(None),
    target_asset_id: Optional[uuid.UUID] = Query(None),
    edge_type: Optional[str] = Query(None, description="direct | derived | copy | aggregated"),
    created_by: Optional[uuid.UUID] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    org_id = get_active_org_id(current_user)
    q = select(LineageEdge).where(LineageEdge.org_id == org_id)
    if source_asset_id:
        q = q.where(LineageEdge.source_asset_id == source_asset_id)
    if target_asset_id:
        q = q.where(LineageEdge.target_asset_id == target_asset_id)
    if edge_type:
        q = q.where(LineageEdge.edge_type == edge_type)
    if created_by:
        q = q.where(LineageEdge.created_by == created_by)
    q = q.order_by(LineageEdge.created_at.desc()).offset(skip).limit(limit)
    result = await session.execute(q)
    edges = result.scalars().all()

    # Load asset refs for each edge
    out = []
    for edge in edges:
        await session.refresh(edge, ["source_asset", "target_asset"])
        out.append(_edge_to_out(edge))
    return out


# ---------------------------------------------------------------------------
# DELETE /lineage/{edge_id}
# ---------------------------------------------------------------------------

@router.delete(
    "/{edge_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a lineage edge",
)
async def delete_edge(
    edge_id: uuid.UUID,
    current_user=Depends(require_permission("lineage", "delete")),
    session: AsyncSession = Depends(get_session),
):
    edge = await _get_edge_or_404(edge_id, get_active_org_id(current_user), session)
    await session.delete(edge)
    await session.commit()


# ---------------------------------------------------------------------------
# GET /lineage/{asset_id}/upstream
# ---------------------------------------------------------------------------

@router.get(
    "/{asset_id}/upstream",
    response_model=List[LineageNodeOut],
    summary="List all upstream assets (recursive BFS)",
)
async def get_upstream(
    asset_id: uuid.UUID,
    max_depth: int = Query(10, ge=1, le=50, description="Max hops to traverse"),
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Returns all assets that directly or indirectly feed data INTO this asset.
    Depth 1 = direct parents, depth 2 = grandparents, etc.
    """
    org_id = get_active_org_id(current_user)
    await _get_asset_or_404(asset_id, org_id, session)
    nodes_raw = await _traverse(asset_id, org_id, "upstream", session, max_depth)
    if not nodes_raw:
        return []

    # Fetch asset details for all found nodes
    asset_ids = [n["asset_id"] for n in nodes_raw]
    result = await session.execute(
        select(DataAsset).where(DataAsset.id.in_(asset_ids), DataAsset.org_id == org_id)
    )
    asset_map = {a.id: a for a in result.scalars().all()}

    out = []
    for n in nodes_raw:
        a = asset_map.get(n["asset_id"])
        if a:
            out.append(LineageNodeOut(
                id=a.id, name=a.name, display_name=a.display_name,
                asset_type=a.asset_type, fully_qualified_name=a.fully_qualified_name,
                depth=n["depth"], direction="upstream",
            ))
    return out


# ---------------------------------------------------------------------------
# GET /lineage/{asset_id}/downstream
# ---------------------------------------------------------------------------

@router.get(
    "/{asset_id}/downstream",
    response_model=List[LineageNodeOut],
    summary="List all downstream assets (recursive BFS)",
)
async def get_downstream(
    asset_id: uuid.UUID,
    max_depth: int = Query(10, ge=1, le=50, description="Max hops to traverse"),
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Returns all assets that this asset directly or indirectly feeds data INTO.
    Depth 1 = direct children, depth 2 = grandchildren, etc.
    """
    org_id = get_active_org_id(current_user)
    await _get_asset_or_404(asset_id, org_id, session)
    nodes_raw = await _traverse(asset_id, org_id, "downstream", session, max_depth)
    if not nodes_raw:
        return []

    asset_ids = [n["asset_id"] for n in nodes_raw]
    result = await session.execute(
        select(DataAsset).where(DataAsset.id.in_(asset_ids), DataAsset.org_id == org_id)
    )
    asset_map = {a.id: a for a in result.scalars().all()}

    out = []
    for n in nodes_raw:
        a = asset_map.get(n["asset_id"])
        if a:
            out.append(LineageNodeOut(
                id=a.id, name=a.name, display_name=a.display_name,
                asset_type=a.asset_type, fully_qualified_name=a.fully_qualified_name,
                depth=n["depth"], direction="downstream",
            ))
    return out


# ---------------------------------------------------------------------------
# GET /lineage/{asset_id}/graph
# ---------------------------------------------------------------------------

@router.get(
    "/{asset_id}/graph",
    response_model=LineageGraphOut,
    summary="Full lineage graph for UI visualisation (nodes + edges)",
)
async def get_graph(
    asset_id: uuid.UUID,
    max_depth: int = Query(5, ge=1, le=20),
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Returns the complete lineage subgraph centred on this asset:
    - All upstream nodes (recursive)
    - All downstream nodes (recursive)
    - The asset itself
    - All edges connecting them (subset of org edges relevant to these nodes)

    Designed to power a force-directed or DAG graph in the frontend.
    """
    org_id = get_active_org_id(current_user)
    root_asset = await _get_asset_or_404(asset_id, org_id, session)

    upstream_raw = await _traverse(asset_id, org_id, "upstream", session, max_depth)
    downstream_raw = await _traverse(asset_id, org_id, "downstream", session, max_depth)

    # Collect all unique asset IDs in the subgraph
    all_node_ids: Set[uuid.UUID] = {asset_id}
    for n in upstream_raw + downstream_raw:
        all_node_ids.add(n["asset_id"])

    # Fetch all assets in one query
    result = await session.execute(
        select(DataAsset).where(DataAsset.id.in_(all_node_ids), DataAsset.org_id == org_id)
    )
    asset_map = {a.id: a for a in result.scalars().all()}

    # Build depth/direction map
    depth_dir: Dict[uuid.UUID, Dict] = {
        asset_id: {"depth": 0, "direction": "self"}
    }
    for n in upstream_raw:
        depth_dir[n["asset_id"]] = {"depth": n["depth"], "direction": "upstream"}
    for n in downstream_raw:
        depth_dir.setdefault(n["asset_id"], {"depth": n["depth"], "direction": "downstream"})

    nodes: List[LineageNodeOut] = []
    for aid, meta in depth_dir.items():
        a = asset_map.get(aid)
        if a:
            nodes.append(LineageNodeOut(
                id=a.id, name=a.name, display_name=a.display_name,
                asset_type=a.asset_type, fully_qualified_name=a.fully_qualified_name,
                depth=meta["depth"], direction=meta["direction"],
            ))

    # Fetch all edges where both endpoints are in the subgraph
    edges_result = await session.execute(
        select(LineageEdge).where(
            LineageEdge.org_id == org_id,
            LineageEdge.source_asset_id.in_(all_node_ids),
            LineageEdge.target_asset_id.in_(all_node_ids),
        )
    )
    raw_edges = edges_result.scalars().all()

    edge_outs: List[LineageEdgeOut] = []
    for edge in raw_edges:
        await session.refresh(edge, ["source_asset", "target_asset"])
        edge_outs.append(_edge_to_out(edge))

    return LineageGraphOut(asset_id=asset_id, nodes=nodes, edges=edge_outs)
