"""
Navigation API — dynamic main left navigation with ABAC + flag-based access control.

Endpoints:
  GET    /nav                              resolved nav tree for current user (Home + policy-filtered)
  GET    /nav/tree                         alias for GET /nav
  GET    /nav/nodes                        admin: list all nav nodes
  GET    /nav/nodes?parent=<slug>         admin: list children of parent
  GET    /nav/node/{id}                    single node detail
  POST   /nav/nodes                        admin: create nav node
  PUT    /nav/nodes/{id}                   admin: update nav node
  DELETE /nav/nodes/{id}                   admin: soft-delete nav node

  PUT    /nav/nodes/{id}/org-override      org-level enable/disable
  DELETE /nav/nodes/{id}/org-override      reset org override
  PUT    /nav/nodes/{id}/user-override     user-level enable/disable
  DELETE /nav/nodes/{id}/user-override     reset user override

  GET    /nav/nodes/{id}/policies          list ABAC policies on node
  POST   /nav/nodes/{id}/policies          attach policy (admin)
  DELETE /nav/nodes/{id}/policies/{policy_id}  detach policy (admin)
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
from app.nav_items.models import (
    NavItem,
    NavItemOrgOverride,
    NavItemPolicy,
    NavItemUserOverride,
)
from app.nav_items.schemas import (
    NavItemCreate,
    NavItemResponse,
    NavItemUpdate,
    NavOrgOverrideResponse,
    NavOrgOverrideUpdate,
    NavPolicyAttach,
    NavPolicyResponse,
    NavUserOverrideResponse,
    NavUserOverrideUpdate,
)
from app.nav_items.service import compute_slug_path, resolve_nav_nodes, resolve_nav_tree

router = APIRouter(prefix="/nav", tags=["Navigation"])


def _active_org_id(user: User) -> UUID:
    return UUID(str(getattr(user, "_active_org_id", None) or user.default_org_id or user.org_id))


async def _get_node_or_404(db: AsyncSession, node_id: UUID) -> NavItem:
    result = await db.execute(
        select(NavItem)
        .where(NavItem.id == node_id)
        .options(selectinload(NavItem.children))
    )
    node = result.scalars().first()
    if not node:
        raise HTTPException(status_code=404, detail="Nav node not found")
    return node


async def _get_parent_by_slug(db: AsyncSession, slug: str) -> NavItem:
    result = await db.execute(select(NavItem).where(NavItem.slug == slug))
    node = result.scalars().first()
    if not node:
        raise HTTPException(status_code=404, detail=f"Parent node '{slug}' not found")
    return node


# ---------------------------------------------------------------------------
# GET /nav — resolved nav tree for current user (Home + policy-filtered)
# ---------------------------------------------------------------------------

@router.get("", response_model=List[dict])
@router.get("/tree", response_model=List[dict])
async def get_nav_tree(
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Returns the main left navigation tree for the current user.
    - Home is always first (everyone sees it)
    - Other items are filtered by: global is_active, org override, user override, ABAC policies
    """
    org_id = _active_org_id(current_user)
    return await resolve_nav_tree(db, current_user, org_id)


# ---------------------------------------------------------------------------
# GET /nav/nodes — admin list nav nodes (flat, one level)
# ---------------------------------------------------------------------------

@router.get("/nodes", response_model=List[NavItemResponse])
async def list_nav_nodes(
    parent: Optional[str] = Query(
        default=None,
        description="Parent slug. Omit for root-level nodes.",
    ),
    current_user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    """Admin: list nav nodes at one level. Visibility resolved for org."""
    org_id = _active_org_id(current_user)

    if parent is None:
        stmt = (
            select(NavItem)
            .where(NavItem.parent_id.is_(None))
            .order_by(NavItem.sort_order, NavItem.display_name)
            .options(selectinload(NavItem.children))
        )
    else:
        parent_node = await _get_parent_by_slug(db, parent)
        stmt = (
            select(NavItem)
            .where(NavItem.parent_id == parent_node.id)
            .order_by(NavItem.sort_order, NavItem.display_name)
            .options(selectinload(NavItem.children))
        )

    result = await db.execute(stmt)
    nodes = result.scalars().all()
    resolved = await resolve_nav_nodes(db, list(nodes), current_user, org_id)

    return [
        NavItemResponse(
            id=r["id"],
            parent_id=r["parent_id"],
            slug=r["slug"],
            display_name=r["display_name"],
            description=r["description"],
            icon=r["icon"],
            nav_url=r["nav_url"],
            slug_path=r["slug_path"],
            resource_key=r["resource_key"],
            sort_order=r["sort_order"],
            is_active=r["is_active"],
            has_children=r["has_children"],
            is_enabled=r["is_enabled"],
            is_enabled_globally=r["is_active"],
            org_override=r["org_override"],
            user_override=r["user_override"],
            metadata=r.get("metadata"),
            created_at=r.get("created_at"),
            updated_at=r.get("updated_at"),
        )
        for r in resolved
    ]


# ---------------------------------------------------------------------------
# GET /nav/node/{id} — single node
# ---------------------------------------------------------------------------

@router.get("/node/{node_id}", response_model=NavItemResponse)
async def get_nav_node(
    node_id: UUID,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """Returns a single nav node with resolved visibility."""
    org_id = _active_org_id(current_user)
    node = await _get_node_or_404(db, node_id)
    resolved = await resolve_nav_nodes(db, [node], current_user, org_id)
    r = resolved[0]
    return NavItemResponse(
        id=r["id"],
        parent_id=r["parent_id"],
        slug=r["slug"],
        display_name=r["display_name"],
        description=r["description"],
        icon=r["icon"],
        nav_url=r["nav_url"],
        slug_path=r["slug_path"],
        resource_key=r["resource_key"],
        sort_order=r["sort_order"],
        is_active=r["is_active"],
        has_children=r["has_children"],
        is_enabled=r["is_enabled"],
        is_enabled_globally=r["is_active"],
        org_override=r["org_override"],
        user_override=r["user_override"],
        metadata=r.get("metadata"),
        created_at=r.get("created_at"),
        updated_at=r.get("updated_at"),
    )


# ---------------------------------------------------------------------------
# POST /nav/nodes — create (org admin+)
# ---------------------------------------------------------------------------

@router.post("/nodes", response_model=NavItemResponse, status_code=status.HTTP_201_CREATED)
async def create_nav_node(
    body: NavItemCreate,
    current_user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    """Create a new nav node. Org admins only."""
    org_id = _active_org_id(current_user)

    if body.parent_id:
        parent_result = await db.execute(select(NavItem).where(NavItem.id == body.parent_id))
        if not parent_result.scalars().first():
            raise HTTPException(status_code=404, detail="Parent node not found")

    node = NavItem(
        parent_id=body.parent_id,
        slug=body.slug,
        display_name=body.display_name,
        description=body.description,
        icon=body.icon,
        nav_url=body.nav_url,
        slug_path=body.slug_path,
        resource_key=body.resource_key,
        sort_order=body.sort_order,
        metadata_=body.metadata_,
        created_by=current_user.id,
    )
    db.add(node)
    await db.flush()

    if not node.slug_path:
        node.slug_path = await compute_slug_path(db, node)

    await db.commit()
    await db.refresh(node)

    # New node has no children; build response directly to avoid lazy load
    return NavItemResponse(
        id=node.id,
        parent_id=node.parent_id,
        slug=node.slug,
        display_name=node.display_name,
        description=node.description,
        icon=node.icon,
        nav_url=node.nav_url,
        slug_path=node.slug_path,
        resource_key=node.resource_key,
        sort_order=node.sort_order,
        is_active=node.is_active,
        has_children=False,
        is_enabled=True,
        is_enabled_globally=node.is_active,
        org_override=None,
        user_override=None,
        metadata=node.metadata_,
        created_at=node.created_at,
        updated_at=node.updated_at,
    )


# ---------------------------------------------------------------------------
# PUT /nav/nodes/{id} — update (org admin+)
# ---------------------------------------------------------------------------

@router.put("/nodes/{node_id}", response_model=NavItemResponse)
async def update_nav_node(
    node_id: UUID,
    body: NavItemUpdate,
    current_user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    """Update an existing nav node."""
    org_id = _active_org_id(current_user)
    node = await _get_node_or_404(db, node_id)

    update_data = body.model_dump(exclude_unset=True)
    if "metadata_" in update_data:
        update_data["metadata_"] = update_data.pop("metadata_")

    for field, value in update_data.items():
        setattr(node, field, value)

    if "slug" in update_data and "slug_path" not in update_data:
        node.slug_path = await compute_slug_path(db, node)

    await db.commit()
    await db.refresh(node)

    result = await db.execute(
        select(NavItem)
        .where(NavItem.id == node_id)
        .options(selectinload(NavItem.children))
    )
    reloaded = result.scalars().first()
    resolved = await resolve_nav_nodes(db, [reloaded], current_user, org_id)
    r = resolved[0]
    return NavItemResponse(
        id=r["id"],
        parent_id=r["parent_id"],
        slug=r["slug"],
        display_name=r["display_name"],
        description=r["description"],
        icon=r["icon"],
        nav_url=r["nav_url"],
        slug_path=r["slug_path"],
        resource_key=r["resource_key"],
        sort_order=r["sort_order"],
        is_active=r["is_active"],
        has_children=r["has_children"],
        is_enabled=r["is_enabled"],
        is_enabled_globally=r["is_active"],
        org_override=r["org_override"],
        user_override=r["user_override"],
        metadata=r.get("metadata"),
        created_at=r.get("created_at"),
        updated_at=r.get("updated_at"),
    )


# ---------------------------------------------------------------------------
# DELETE /nav/nodes/{id} — soft delete (org admin+)
# ---------------------------------------------------------------------------

@router.delete("/nodes/{node_id}", response_model=NavItemResponse)
async def delete_nav_node(
    node_id: UUID,
    current_user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    """Soft-delete a nav node (sets is_active=False)."""
    org_id = _active_org_id(current_user)
    node = await _get_node_or_404(db, node_id)

    node.is_active = False
    await db.commit()
    await db.refresh(node)

    return NavItemResponse(
        id=node.id,
        parent_id=node.parent_id,
        slug=node.slug,
        display_name=node.display_name,
        description=node.description,
        icon=node.icon,
        nav_url=node.nav_url,
        slug_path=node.slug_path,
        resource_key=node.resource_key,
        sort_order=node.sort_order,
        is_active=False,
        has_children=False,
        is_enabled=False,
        is_enabled_globally=False,
        org_override=None,
        user_override=None,
        metadata=node.metadata_,
        created_at=node.created_at,
        updated_at=node.updated_at,
    )


# ---------------------------------------------------------------------------
# Org override
# ---------------------------------------------------------------------------

@router.put("/nodes/{node_id}/org-override", response_model=NavOrgOverrideResponse)
async def set_nav_org_override(
    node_id: UUID,
    body: NavOrgOverrideUpdate,
    current_user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    """Org admin enables or disables a nav item for their organization."""
    org_id = _active_org_id(current_user)
    await _get_node_or_404(db, node_id)

    result = await db.execute(
        select(NavItemOrgOverride).where(
            NavItemOrgOverride.org_id == org_id,
            NavItemOrgOverride.node_id == node_id,
        )
    )
    override = result.scalars().first()

    if override:
        override.is_enabled = body.is_enabled
        if body.config is not None:
            override.config = body.config
        override.updated_by = current_user.id
    else:
        override = NavItemOrgOverride(
            org_id=org_id,
            node_id=node_id,
            is_enabled=body.is_enabled,
            config=body.config or {},
            updated_by=current_user.id,
        )
        db.add(override)

    await db.commit()
    await db.refresh(override)
    return NavOrgOverrideResponse.model_validate(override)


@router.delete("/nodes/{node_id}/org-override", status_code=status.HTTP_204_NO_CONTENT)
async def reset_nav_org_override(
    node_id: UUID,
    current_user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    org_id = _active_org_id(current_user)
    result = await db.execute(
        select(NavItemOrgOverride).where(
            NavItemOrgOverride.org_id == org_id,
            NavItemOrgOverride.node_id == node_id,
        )
    )
    override = result.scalars().first()
    if override:
        await db.delete(override)
        await db.commit()


# ---------------------------------------------------------------------------
# User override
# ---------------------------------------------------------------------------

@router.put("/nodes/{node_id}/user-override", response_model=NavUserOverrideResponse)
async def set_nav_user_override(
    node_id: UUID,
    body: NavUserOverrideUpdate,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """User enables or disables a nav item for themselves."""
    await _get_node_or_404(db, node_id)

    result = await db.execute(
        select(NavItemUserOverride).where(
            NavItemUserOverride.user_id == current_user.id,
            NavItemUserOverride.node_id == node_id,
        )
    )
    override = result.scalars().first()

    if override:
        override.is_enabled = body.is_enabled
    else:
        override = NavItemUserOverride(
            user_id=current_user.id,
            node_id=node_id,
            is_enabled=body.is_enabled,
        )
        db.add(override)

    await db.commit()
    await db.refresh(override)
    return NavUserOverrideResponse.model_validate(override)


@router.delete("/nodes/{node_id}/user-override", status_code=status.HTTP_204_NO_CONTENT)
async def reset_nav_user_override(
    node_id: UUID,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(NavItemUserOverride).where(
            NavItemUserOverride.user_id == current_user.id,
            NavItemUserOverride.node_id == node_id,
        )
    )
    override = result.scalars().first()
    if override:
        await db.delete(override)
        await db.commit()


# ---------------------------------------------------------------------------
# Policies
# ---------------------------------------------------------------------------

@router.get("/nodes/{node_id}/policies", response_model=List[NavPolicyResponse])
async def list_nav_node_policies(
    node_id: UUID,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """List all ABAC policies attached to a nav node."""
    await _get_node_or_404(db, node_id)
    result = await db.execute(select(NavItemPolicy).where(NavItemPolicy.node_id == node_id))
    return [NavPolicyResponse.model_validate(r) for r in result.scalars().all()]


@router.post(
    "/nodes/{node_id}/policies",
    response_model=NavPolicyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def attach_policy_to_nav_node(
    node_id: UUID,
    body: NavPolicyAttach,
    current_user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    """Attach an existing ABAC policy to a nav node."""
    await _get_node_or_404(db, node_id)

    pol_result = await db.execute(select(Policy).where(Policy.id == body.policy_id))
    if not pol_result.scalars().first():
        raise HTTPException(status_code=404, detail="Policy not found")

    existing = await db.execute(
        select(NavItemPolicy).where(
            NavItemPolicy.node_id == node_id,
            NavItemPolicy.policy_id == body.policy_id,
        )
    )
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="Policy already attached to this node")

    np = NavItemPolicy(node_id=node_id, policy_id=body.policy_id)
    db.add(np)
    await db.commit()
    await db.refresh(np)
    return NavPolicyResponse.model_validate(np)


@router.delete("/nodes/{node_id}/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def detach_policy_from_nav_node(
    node_id: UUID,
    policy_id: UUID,
    current_user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(NavItemPolicy).where(
            NavItemPolicy.node_id == node_id,
            NavItemPolicy.policy_id == policy_id,
        )
    )
    np = result.scalars().first()
    if not np:
        raise HTTPException(status_code=404, detail="Policy not attached to this node")
    await db.delete(np)
    await db.commit()
