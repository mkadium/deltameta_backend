"""
Settings API — dynamic N-level hierarchy with ABAC + flag-based access control.

Endpoints:
  GET    /settings                         list root nodes (or children of ?parent=<slug>)
  GET    /settings/tree                    full recursive tree from root (or ?parent=<slug>)
  GET    /settings/node/{id}               single node detail
  POST   /settings/nodes                   create a node (org admin+)
  PUT    /settings/nodes/{id}              update a node (org admin+)
  DELETE /settings/nodes/{id}              soft-delete a node (org admin+)

  PUT    /settings/nodes/{id}/org-override       set org-level enable/disable
  DELETE /settings/nodes/{id}/org-override       reset org override (back to global)
  PUT    /settings/nodes/{id}/user-override      set user-level enable/disable
  DELETE /settings/nodes/{id}/user-override      reset user override

  GET    /settings/nodes/{id}/policies     list ABAC policies on this node
  POST   /settings/nodes/{id}/policies     attach a policy to this node
  DELETE /settings/nodes/{id}/policies/{policy_id}  detach policy
"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import require_active_user, require_org_admin
from app.auth.models import Policy, User
from app.db import get_session
from app.setting_nodes.models import (
    OrgSettingOverride, SettingNode, SettingPolicy, UserSettingOverride,
)
from app.setting_nodes.schemas import (
    OrgOverrideResponse, OrgOverrideUpdate,
    SettingNodeCreate, SettingNodeResponse, SettingNodeUpdate,
    SettingPolicyAttach, SettingPolicyResponse,
    UserOverrideResponse, UserOverrideUpdate,
)
from app.setting_nodes.service import compute_slug_path, resolve_nodes

router = APIRouter(prefix="/settings", tags=["Settings"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_node_or_404(db: AsyncSession, node_id: UUID) -> SettingNode:
    result = await db.execute(
        select(SettingNode)
        .where(SettingNode.id == node_id)
        .options(selectinload(SettingNode.children))
    )
    node = result.scalars().first()
    if not node:
        raise HTTPException(status_code=404, detail="Setting node not found")
    return node


async def _get_parent_by_slug(db: AsyncSession, slug: str) -> SettingNode:
    result = await db.execute(
        select(SettingNode).where(SettingNode.slug == slug)
    )
    node = result.scalars().first()
    if not node:
        raise HTTPException(status_code=404, detail=f"Parent node '{slug}' not found")
    return node


def _active_org_id(user: User) -> UUID:
    return UUID(str(getattr(user, "_active_org_id", None) or user.default_org_id or user.org_id))


# ---------------------------------------------------------------------------
# GET /settings — list children (flat, one level)
# ---------------------------------------------------------------------------

@router.get("", response_model=List[SettingNodeResponse])
async def list_settings(
    parent: Optional[str] = Query(
        default=None,
        description="Parent node slug. Omit to get root-level nodes.",
    ),
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Returns one level of the settings hierarchy.
    - No `parent` → root-level cards (e.g. Services, Applications, ML Models)
    - `parent=services` → sub-cards under "services" (e.g. APIs, Databases)
    - `parent=databases` → leaf nodes under "databases" (e.g. PostgreSQL, MySQL)

    Visibility is resolved per the user's org and ABAC policies.
    """
    org_id = _active_org_id(current_user)

    if parent is None:
        # Root nodes: parent_id IS NULL
        stmt = (
            select(SettingNode)
            .where(SettingNode.parent_id.is_(None))
            .order_by(SettingNode.sort_order, SettingNode.display_label)
            .options(selectinload(SettingNode.children))
        )
    else:
        parent_node = await _get_parent_by_slug(db, parent)
        stmt = (
            select(SettingNode)
            .where(SettingNode.parent_id == parent_node.id)
            .order_by(SettingNode.sort_order, SettingNode.display_label)
            .options(selectinload(SettingNode.children))
        )

    result = await db.execute(stmt)
    nodes = result.scalars().all()

    resolved = await resolve_nodes(db, list(nodes), current_user, org_id)
    # Filter out globally disabled (only show enabled to regular users; admins see all)
    if not current_user.is_admin and not current_user.is_global_admin:
        resolved = [r for r in resolved if r["is_enabled"]]

    return [SettingNodeResponse(**r) for r in resolved]


# ---------------------------------------------------------------------------
# GET /settings/tree — recursive full tree
# ---------------------------------------------------------------------------

async def _build_tree(
    db: AsyncSession,
    parent_id: Optional[UUID],
    current_user: User,
    org_id: UUID,
) -> List[dict]:
    stmt = (
        select(SettingNode)
        .where(
            SettingNode.parent_id == parent_id
            if parent_id
            else SettingNode.parent_id.is_(None)
        )
        .order_by(SettingNode.sort_order, SettingNode.display_label)
        .options(selectinload(SettingNode.children))
    )
    result = await db.execute(stmt)
    nodes = result.scalars().all()

    resolved = await resolve_nodes(db, list(nodes), current_user, org_id)
    if not current_user.is_admin and not current_user.is_global_admin:
        resolved = [r for r in resolved if r["is_enabled"]]

    for item in resolved:
        item["children"] = await _build_tree(db, item["id"], current_user, org_id)

    return resolved


@router.get("/tree", response_model=List[dict])
async def get_settings_tree(
    parent: Optional[str] = Query(default=None, description="Root slug to start tree from"),
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """Returns the full recursive settings tree from root (or from a given parent slug)."""
    org_id = _active_org_id(current_user)
    parent_id = None
    if parent:
        parent_node = await _get_parent_by_slug(db, parent)
        parent_id = parent_node.id
    return await _build_tree(db, parent_id, current_user, org_id)


# ---------------------------------------------------------------------------
# GET /settings/node/{id} — single node
# ---------------------------------------------------------------------------

@router.get("/node/{node_id}", response_model=SettingNodeResponse)
async def get_setting_node(
    node_id: UUID,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """Returns a single setting node with resolved visibility."""
    org_id = _active_org_id(current_user)
    node = await _get_node_or_404(db, node_id)
    resolved = await resolve_nodes(db, [node], current_user, org_id)
    return SettingNodeResponse(**resolved[0])


# ---------------------------------------------------------------------------
# POST /settings/nodes — create (org admin+)
# ---------------------------------------------------------------------------

@router.post("/nodes", response_model=SettingNodeResponse, status_code=status.HTTP_201_CREATED)
async def create_setting_node(
    body: SettingNodeCreate,
    current_user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    """
    Create a new setting node.
    - Org admins can create nodes.
    - `parent_id` is optional (omit for root-level).
    - `slug` must be unique within the same parent.
    - `slug_path` is auto-computed if not provided.
    """
    org_id = _active_org_id(current_user)

    # Validate parent exists if provided
    if body.parent_id:
        parent_result = await db.execute(
            select(SettingNode).where(SettingNode.id == body.parent_id)
        )
        if not parent_result.scalars().first():
            raise HTTPException(status_code=404, detail="Parent node not found")

    # Enforce: leaf nodes must have nav_url
    if body.node_type == "leaf" and not body.nav_url:
        raise HTTPException(
            status_code=422,
            detail="Leaf nodes must have a nav_url.",
        )

    node = SettingNode(
        parent_id=body.parent_id,
        slug=body.slug,
        display_label=body.display_label,
        description=body.description,
        icon=body.icon,
        node_type=body.node_type,
        nav_url=body.nav_url,
        slug_path=body.slug_path,
        sort_order=body.sort_order,
        metadata_=body.metadata_,
        created_by=current_user.id,
    )
    db.add(node)
    await db.flush()  # get the id for slug_path computation

    # Auto-compute slug_path if not supplied
    if not node.slug_path:
        node.slug_path = await compute_slug_path(db, node)

    await db.commit()
    await db.refresh(node)

    # Re-load with children relationship for response
    reloaded = await _get_node_or_404(db, node.id)
    resolved = await resolve_nodes(db, [reloaded], current_user, org_id)
    return SettingNodeResponse(**resolved[0])


# ---------------------------------------------------------------------------
# PUT /settings/nodes/{id} — update (org admin+)
# ---------------------------------------------------------------------------

@router.put("/nodes/{node_id}", response_model=SettingNodeResponse)
async def update_setting_node(
    node_id: UUID,
    body: SettingNodeUpdate,
    current_user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    """Update an existing setting node. Org admins can update nodes."""
    org_id = _active_org_id(current_user)
    node = await _get_node_or_404(db, node_id)

    update_data = body.model_dump(exclude_unset=True)
    # Handle metadata alias
    if "metadata_" in update_data:
        update_data["metadata_"] = update_data.pop("metadata_")

    for field, value in update_data.items():
        setattr(node, field, value)

    # Recompute slug_path if slug changed and slug_path not explicitly set
    if "slug" in update_data and "slug_path" not in update_data:
        node.slug_path = await compute_slug_path(db, node)

    await db.commit()
    await db.refresh(node)

    reloaded = await _get_node_or_404(db, node.id)
    resolved = await resolve_nodes(db, [reloaded], current_user, org_id)
    return SettingNodeResponse(**resolved[0])


# ---------------------------------------------------------------------------
# DELETE /settings/nodes/{id} — soft delete (org admin+)
# ---------------------------------------------------------------------------

@router.delete("/nodes/{node_id}", response_model=SettingNodeResponse)
async def delete_setting_node(
    node_id: UUID,
    current_user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    """Soft-delete a setting node (sets is_active=False). Children remain but become unreachable."""
    org_id = _active_org_id(current_user)
    node = await _get_node_or_404(db, node_id)

    node.is_active = False
    await db.commit()
    await db.refresh(node)

    reloaded = await _get_node_or_404(db, node.id)
    resolved = await resolve_nodes(db, [reloaded], current_user, org_id)
    return SettingNodeResponse(**resolved[0])


# ---------------------------------------------------------------------------
# PUT /settings/nodes/{id}/org-override — org admin sets org-level toggle
# ---------------------------------------------------------------------------

@router.put("/nodes/{node_id}/org-override", response_model=OrgOverrideResponse)
async def set_org_override(
    node_id: UUID,
    body: OrgOverrideUpdate,
    current_user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    """
    Org admin enables or disables a setting node for their organization.
    Creates or updates the OrgSettingOverride row.
    """
    org_id = _active_org_id(current_user)
    await _get_node_or_404(db, node_id)  # validate node exists

    result = await db.execute(
        select(OrgSettingOverride).where(
            OrgSettingOverride.org_id == org_id,
            OrgSettingOverride.node_id == node_id,
        )
    )
    override = result.scalars().first()

    if override:
        override.is_enabled = body.is_enabled
        if body.config is not None:
            override.config = body.config
        override.updated_by = current_user.id
    else:
        override = OrgSettingOverride(
            org_id=org_id,
            node_id=node_id,
            is_enabled=body.is_enabled,
            config=body.config or {},
            updated_by=current_user.id,
        )
        db.add(override)

    await db.commit()
    await db.refresh(override)
    return OrgOverrideResponse.model_validate(override)


# ---------------------------------------------------------------------------
# DELETE /settings/nodes/{id}/org-override — reset org override
# ---------------------------------------------------------------------------

@router.delete("/nodes/{node_id}/org-override", status_code=status.HTTP_204_NO_CONTENT)
async def reset_org_override(
    node_id: UUID,
    current_user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    """Remove org-level override — node reverts to global is_active setting."""
    org_id = _active_org_id(current_user)

    result = await db.execute(
        select(OrgSettingOverride).where(
            OrgSettingOverride.org_id == org_id,
            OrgSettingOverride.node_id == node_id,
        )
    )
    override = result.scalars().first()
    if override:
        await db.delete(override)
        await db.commit()


# ---------------------------------------------------------------------------
# PUT /settings/nodes/{id}/user-override — user sets their own toggle
# ---------------------------------------------------------------------------

@router.put("/nodes/{node_id}/user-override", response_model=UserOverrideResponse)
async def set_user_override(
    node_id: UUID,
    body: UserOverrideUpdate,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """User enables or disables a setting node for themselves."""
    await _get_node_or_404(db, node_id)

    result = await db.execute(
        select(UserSettingOverride).where(
            UserSettingOverride.user_id == current_user.id,
            UserSettingOverride.node_id == node_id,
        )
    )
    override = result.scalars().first()

    if override:
        override.is_enabled = body.is_enabled
    else:
        override = UserSettingOverride(
            user_id=current_user.id,
            node_id=node_id,
            is_enabled=body.is_enabled,
        )
        db.add(override)

    await db.commit()
    await db.refresh(override)
    return UserOverrideResponse.model_validate(override)


# ---------------------------------------------------------------------------
# DELETE /settings/nodes/{id}/user-override — reset user override
# ---------------------------------------------------------------------------

@router.delete("/nodes/{node_id}/user-override", status_code=status.HTTP_204_NO_CONTENT)
async def reset_user_override(
    node_id: UUID,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """Remove user-level override — node reverts to org/global setting."""
    result = await db.execute(
        select(UserSettingOverride).where(
            UserSettingOverride.user_id == current_user.id,
            UserSettingOverride.node_id == node_id,
        )
    )
    override = result.scalars().first()
    if override:
        await db.delete(override)
        await db.commit()


# ---------------------------------------------------------------------------
# GET /settings/nodes/{id}/policies — list ABAC policies on this node
# ---------------------------------------------------------------------------

@router.get("/nodes/{node_id}/policies", response_model=List[SettingPolicyResponse])
async def list_node_policies(
    node_id: UUID,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """List all ABAC policies attached to a setting node."""
    await _get_node_or_404(db, node_id)
    result = await db.execute(
        select(SettingPolicy).where(SettingPolicy.node_id == node_id)
    )
    return [SettingPolicyResponse.model_validate(r) for r in result.scalars().all()]


# ---------------------------------------------------------------------------
# POST /settings/nodes/{id}/policies — attach ABAC policy (org admin+)
# ---------------------------------------------------------------------------

@router.post(
    "/nodes/{node_id}/policies",
    response_model=SettingPolicyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def attach_policy_to_node(
    node_id: UUID,
    body: SettingPolicyAttach,
    current_user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    """Attach an existing ABAC policy to a setting node (controls who can see it)."""
    await _get_node_or_404(db, node_id)

    # Validate policy exists
    pol_result = await db.execute(select(Policy).where(Policy.id == body.policy_id))
    if not pol_result.scalars().first():
        raise HTTPException(status_code=404, detail="Policy not found")

    # Check not already attached
    existing = await db.execute(
        select(SettingPolicy).where(
            SettingPolicy.node_id == node_id,
            SettingPolicy.policy_id == body.policy_id,
        )
    )
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="Policy already attached to this node")

    sp = SettingPolicy(node_id=node_id, policy_id=body.policy_id)
    db.add(sp)
    await db.commit()
    await db.refresh(sp)
    return SettingPolicyResponse.model_validate(sp)


# ---------------------------------------------------------------------------
# DELETE /settings/nodes/{id}/policies/{policy_id} — detach ABAC policy
# ---------------------------------------------------------------------------

@router.delete(
    "/nodes/{node_id}/policies/{policy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def detach_policy_from_node(
    node_id: UUID,
    policy_id: UUID,
    current_user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    """Detach an ABAC policy from a setting node."""
    result = await db.execute(
        select(SettingPolicy).where(
            SettingPolicy.node_id == node_id,
            SettingPolicy.policy_id == policy_id,
        )
    )
    sp = result.scalars().first()
    if not sp:
        raise HTTPException(status_code=404, detail="Policy not attached to this node")
    await db.delete(sp)
    await db.commit()
