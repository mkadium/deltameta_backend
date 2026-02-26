"""
Navigation service — resolution logic for nav item visibility.

Resolves the final is_enabled state by combining:
  1. Global flag (NavItem.is_active)
  2. Org override
  3. User override
  4. ABAC policies attached to the node
"""
from __future__ import annotations

from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.inspection import inspect as sa_inspect

from app.auth.models import User
from app.nav_items.models import (
    NavItem,
    NavItemOrgOverride,
    NavItemPolicy,
    NavItemUserOverride,
)


# ---------------------------------------------------------------------------
# Bulk fetch helpers
# ---------------------------------------------------------------------------

async def get_org_overrides_map(
    db: AsyncSession,
    org_id: UUID,
    node_ids: List[UUID],
) -> Dict[UUID, NavItemOrgOverride]:
    if not node_ids:
        return {}
    result = await db.execute(
        select(NavItemOrgOverride).where(
            NavItemOrgOverride.org_id == org_id,
            NavItemOrgOverride.node_id.in_(node_ids),
        )
    )
    return {row.node_id: row for row in result.scalars().all()}


async def get_user_overrides_map(
    db: AsyncSession,
    user_id: UUID,
    node_ids: List[UUID],
) -> Dict[UUID, NavItemUserOverride]:
    if not node_ids:
        return {}
    result = await db.execute(
        select(NavItemUserOverride).where(
            NavItemUserOverride.user_id == user_id,
            NavItemUserOverride.node_id.in_(node_ids),
        )
    )
    return {row.node_id: row for row in result.scalars().all()}


async def get_node_policies_map(
    db: AsyncSession,
    node_ids: List[UUID],
) -> Dict[UUID, List[NavItemPolicy]]:
    if not node_ids:
        return {}
    result = await db.execute(
        select(NavItemPolicy).where(NavItemPolicy.node_id.in_(node_ids))
    )
    mapping: Dict[UUID, List[NavItemPolicy]] = {}
    for row in result.scalars().all():
        mapping.setdefault(row.node_id, []).append(row)
    return mapping


async def get_user_policy_ids(db: AsyncSession, user: User) -> set:
    """Return set of policy_ids the user has (via direct assignment or roles)."""
    from app.auth.models import role_policies, user_policies, user_roles

    policy_ids: set = set()

    # Direct user->policy assignments
    q_direct = select(user_policies.c.policy_id).where(user_policies.c.user_id == user.id)
    result = await db.execute(q_direct)
    policy_ids.update(str(r) for r in result.scalars().all())

    # Via roles: user_roles -> role_policies
    q_role = (
        select(role_policies.c.policy_id)
        .select_from(user_roles.join(role_policies, user_roles.c.role_id == role_policies.c.role_id))
        .where(user_roles.c.user_id == user.id)
    )
    result = await db.execute(q_role)
    policy_ids.update(str(r) for r in result.scalars().all())

    return policy_ids


# ---------------------------------------------------------------------------
# Single-node visibility resolution
# ---------------------------------------------------------------------------

def resolve_nav_enabled(
    node: NavItem,
    org_override: Optional[NavItemOrgOverride],
    user_override: Optional[NavItemUserOverride],
    node_policy_rows: List[NavItemPolicy],
    user_policy_ids: set,
) -> tuple[bool, Optional[bool], Optional[bool]]:
    """Returns (is_enabled, org_override_value, user_override_value)."""
    if not node.is_active:
        return False, (org_override.is_enabled if org_override else None), (user_override.is_enabled if user_override else None)

    org_val = org_override.is_enabled if org_override else None
    user_val = user_override.is_enabled if user_override else None

    if user_val is not None:
        effective = user_val
    elif org_val is not None:
        effective = org_val
    else:
        effective = True

    # ABAC: if policies attached, user must have at least one
    if node_policy_rows and effective:
        policy_ids_on_node = {str(sp.policy_id) for sp in node_policy_rows}
        if not policy_ids_on_node.intersection(user_policy_ids):
            effective = False

    return effective, org_val, user_val


# ---------------------------------------------------------------------------
# Resolve a list of nav nodes (batch)
# ---------------------------------------------------------------------------

async def resolve_nav_nodes(
    db: AsyncSession,
    nodes: List[NavItem],
    user: User,
    org_id: UUID,
) -> List[dict]:
    """For each node, compute resolved visibility and return enriched dicts."""
    node_ids = [n.id for n in nodes]

    org_map = await get_org_overrides_map(db, org_id, node_ids)
    user_map = await get_user_overrides_map(db, user.id, node_ids)
    policy_map = await get_node_policies_map(db, node_ids)
    user_policy_ids = await get_user_policy_ids(db, user)

    results = []
    for node in nodes:
        org_ov = org_map.get(node.id)
        user_ov = user_map.get(node.id)
        node_policies = policy_map.get(node.id, [])

        is_enabled, org_val, user_val = resolve_nav_enabled(
            node, org_ov, user_ov, node_policies, user_policy_ids
        )

        # Avoid async lazy load: only access children if already eagerly loaded
        insp = sa_inspect(node)
        if "children" in insp.unloaded:
            children: List[NavItem] = []
            has_children = False
        else:
            children = list(node.children)
            has_children = len(children) > 0

        results.append({
            "id": node.id,
            "parent_id": node.parent_id,
            "slug": node.slug,
            "display_name": node.display_name,
            "description": node.description,
            "icon": node.icon,
            "nav_url": node.nav_url,
            "slug_path": node.slug_path,
            "resource_key": node.resource_key,
            "sort_order": node.sort_order,
            "is_active": node.is_active,
            "has_children": has_children,
            "is_enabled": is_enabled,
            "org_override": org_val,
            "user_override": user_val,
            "metadata": node.metadata_,
            "created_at": node.created_at,
            "updated_at": node.updated_at,
            "children": list(children) if children is not None else [],
        })

    return results


# ---------------------------------------------------------------------------
# Build resolved nav tree (Home always first, then policy-filtered items)
# ---------------------------------------------------------------------------

# Well-known UUID for Home (always visible)
HOME_UUID = "00000000-0000-0000-0000-000000000001"

HOME_NODE = {
    "id": HOME_UUID,
    "slug": "home",
    "display_name": "Home",
    "description": "Portal home with stats and global search",
    "icon": "home",
    "nav_url": "/",
    "resource_key": "home",
    "sort_order": -1,
    "children": [],
}


async def resolve_nav_tree(
    db: AsyncSession,
    user: User,
    org_id: UUID,
) -> List[dict]:
    """
    Fetch root nav items, resolve visibility, recursively build tree.
    Returns list with Home first, then only enabled nav items.
    """
    # Fetch root nav items with full hierarchy (3 levels; avoids async lazy load)
    result = await db.execute(
        select(NavItem)
        .where(NavItem.parent_id.is_(None))
        .where(NavItem.is_active.is_(True))
        .order_by(NavItem.sort_order, NavItem.display_name)
        .options(
            selectinload(NavItem.children).selectinload(NavItem.children)
        )
    )
    root_nodes = result.scalars().all()
    if not root_nodes:
        return [HOME_NODE]

    # Resolve visibility for roots
    resolved = await resolve_nav_nodes(db, root_nodes, user, org_id)

    # Build tree recursively (only include enabled nodes)
    tree = [HOME_NODE]

    for r in resolved:
        if not r["is_enabled"]:
            continue
        child_list = await _build_nav_children(db, r["children"], user, org_id)
        tree.append({
            "id": str(r["id"]),
            "slug": r["slug"],
            "display_name": r["display_name"],
            "description": r["description"],
            "icon": r["icon"],
            "nav_url": r["nav_url"],
            "resource_key": r["resource_key"],
            "sort_order": r["sort_order"],
            "children": child_list,
        })

    return tree


async def _build_nav_children(
    db: AsyncSession,
    children: List[NavItem],
    user: User,
    org_id: UUID,
) -> List[dict]:
    """Recursively resolve and build child list (only enabled)."""
    if not children:
        return []

    resolved = await resolve_nav_nodes(db, children, user, org_id)
    out = []
    for r in resolved:
        if not r["is_enabled"]:
            continue
        sub_children = await _build_nav_children(db, r["children"], user, org_id)
        out.append({
            "id": str(r["id"]),
            "slug": r["slug"],
            "display_name": r["display_name"],
            "description": r["description"],
            "icon": r["icon"],
            "nav_url": r["nav_url"],
            "resource_key": r["resource_key"],
            "sort_order": r["sort_order"],
            "children": sub_children,
        })
    return sorted(out, key=lambda x: (x["sort_order"], x["display_name"]))


# ---------------------------------------------------------------------------
# Compute slug_path for a nav item
# ---------------------------------------------------------------------------

async def compute_slug_path(db: AsyncSession, node: NavItem) -> str:
    """Walk up parent chain and build dot-separated slug path."""
    parts = [node.slug]
    current = node
    while current.parent_id:
        result = await db.execute(
            select(NavItem).where(NavItem.id == current.parent_id)
        )
        parent = result.scalars().first()
        if not parent:
            break
        parts.insert(0, parent.slug)
        current = parent
    return ".".join(parts)
