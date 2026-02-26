"""
Settings service — resolution logic for node visibility.

Resolves the final `is_enabled` state for each SettingNode by combining:
  1. Global flag    : SettingNode.is_active
  2. Org override   : OrgSettingOverride.is_enabled (if row exists for org)
  3. User override  : UserSettingOverride.is_enabled (if row exists for user)
  4. ABAC policies  : SettingPolicy rows attached to the node (resource_type="setting")

Resolution order (most-specific wins, but global=false always wins):
  - is_active=False → always hidden (global off, cannot be overridden)
  - user_override exists → use user value
  - org_override exists → use org value
  - else → use global is_active (True at this point)
  - ABAC policy attached → user must have "read" operation in at least one policy on this node
"""
from __future__ import annotations

from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.setting_nodes.models import (
    OrgSettingOverride, SettingNode, SettingPolicy, UserSettingOverride,
)
from app.auth.models import Policy, User


# ---------------------------------------------------------------------------
# Bulk fetch helpers
# ---------------------------------------------------------------------------

async def get_org_overrides_map(
    db: AsyncSession,
    org_id: UUID,
    node_ids: List[UUID],
) -> Dict[UUID, OrgSettingOverride]:
    """Return {node_id: OrgSettingOverride} for the given org and node list."""
    if not node_ids:
        return {}
    result = await db.execute(
        select(OrgSettingOverride).where(
            OrgSettingOverride.org_id == org_id,
            OrgSettingOverride.node_id.in_(node_ids),
        )
    )
    return {row.node_id: row for row in result.scalars().all()}


async def get_user_overrides_map(
    db: AsyncSession,
    user_id: UUID,
    node_ids: List[UUID],
) -> Dict[UUID, UserSettingOverride]:
    """Return {node_id: UserSettingOverride} for the given user and node list."""
    if not node_ids:
        return {}
    result = await db.execute(
        select(UserSettingOverride).where(
            UserSettingOverride.user_id == user_id,
            UserSettingOverride.node_id.in_(node_ids),
        )
    )
    return {row.node_id: row for row in result.scalars().all()}


async def get_node_policies_map(
    db: AsyncSession,
    node_ids: List[UUID],
) -> Dict[UUID, List[SettingPolicy]]:
    """Return {node_id: [SettingPolicy, ...]} for the given nodes."""
    if not node_ids:
        return {}
    result = await db.execute(
        select(SettingPolicy).where(SettingPolicy.node_id.in_(node_ids))
    )
    mapping: Dict[UUID, List[SettingPolicy]] = {}
    for row in result.scalars().all():
        mapping.setdefault(row.node_id, []).append(row)
    return mapping


async def get_user_policy_ids(db: AsyncSession, user: User) -> set:
    """Return set of policy_ids the user has (via direct assignment or roles)."""
    # Direct user policies
    direct_ids = {str(p.id) for p in (user.policies or [])}
    # Role policies
    for role in (user.roles or []):
        for p in (role.policies or []):
            direct_ids.add(str(p.id))
    return direct_ids


# ---------------------------------------------------------------------------
# Single-node visibility resolution
# ---------------------------------------------------------------------------

def resolve_node_enabled(
    node: SettingNode,
    org_override: Optional[OrgSettingOverride],
    user_override: Optional[UserSettingOverride],
    node_policy_rows: List[SettingPolicy],
    user_policy_ids: set,
) -> tuple[bool, Optional[bool], Optional[bool]]:
    """
    Returns (is_enabled, org_override_value, user_override_value).

    is_enabled: final resolved boolean
    org_override_value: the org's explicit setting (None if no override)
    user_override_value: the user's explicit setting (None if no override)
    """
    # 1. Global flag — cannot be overridden
    if not node.is_active:
        return False, (org_override.is_enabled if org_override else None), (user_override.is_enabled if user_override else None)

    org_val = org_override.is_enabled if org_override else None
    user_val = user_override.is_enabled if user_override else None

    # 2. User override (most specific)
    if user_val is not None:
        effective = user_val
    # 3. Org override
    elif org_val is not None:
        effective = org_val
    # 4. Default: inherit global (True, since we passed step 1)
    else:
        effective = True

    # 5. ABAC check: if policies are attached, user must satisfy at least one
    if node_policy_rows and effective:
        policy_ids_on_node = {str(sp.policy_id) for sp in node_policy_rows}
        if not policy_ids_on_node.intersection(user_policy_ids):
            effective = False

    return effective, org_val, user_val


# ---------------------------------------------------------------------------
# Resolve a list of nodes (batch) for a user
# ---------------------------------------------------------------------------

async def resolve_nodes(
    db: AsyncSession,
    nodes: List[SettingNode],
    user: User,
    org_id: UUID,
) -> List[dict]:
    """
    For each node, compute resolved visibility fields and return enriched dicts.
    Excludes nodes where is_active=False AND no admin context (always filter globally off).
    """
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

        is_enabled, org_val, user_val = resolve_node_enabled(
            node, org_ov, user_ov, node_policies, user_policy_ids
        )

        results.append({
            "id": node.id,
            "parent_id": node.parent_id,
            "slug": node.slug,
            "display_label": node.display_label,
            "description": node.description,
            "icon": node.icon,
            "node_type": node.node_type,
            "nav_url": node.nav_url,
            "slug_path": node.slug_path,
            "sort_order": node.sort_order,
            "is_active": node.is_active,
            "has_children": len(node.children) > 0,
            "is_enabled": is_enabled,
            "is_enabled_globally": node.is_active,
            "org_override": org_val,
            "user_override": user_val,
            "metadata": node.metadata_,
            "created_at": node.created_at,
            "updated_at": node.updated_at,
        })

    return results


# ---------------------------------------------------------------------------
# Compute and auto-fill slug_path for a node
# ---------------------------------------------------------------------------

async def compute_slug_path(db: AsyncSession, node: SettingNode) -> str:
    """Walk up the parent chain and build a dot-separated slug path."""
    parts = [node.slug]
    current = node
    while current.parent_id:
        result = await db.execute(
            select(SettingNode).where(SettingNode.id == current.parent_id)
        )
        parent = result.scalars().first()
        if not parent:
            break
        parts.insert(0, parent.slug)
        current = parent
    return ".".join(parts)
