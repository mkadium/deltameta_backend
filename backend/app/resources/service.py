"""
Resource Registry sync service.

Responsibilities:
  1. sync_static_registry()  — upsert RESOURCE_GROUPS + RESOURCE_REGISTRY into DB
  2. sync_leaf_nodes()        — upsert all active leaf SettingNodes as ResourceDefinitions
  3. sync_all()               — runs both, returns SyncResult
  4. upsert_leaf_node()       — called on single leaf node create/update/delete
  5. deactivate_leaf_node()   — called when a leaf node is soft-deleted
  6. validate_resource_key()  — used by policy endpoints to check key exists in DB
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.resources.models import ResourceDefinition, ResourceGroup
from app.resources.registry import (
    LEAF_NODE_DEFAULT_OPERATIONS,
    RESOURCE_GROUPS,
    RESOURCE_REGISTRY,
)
from app.resources.schemas import SyncResult
from app.setting_nodes.models import SettingNode


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _get_or_create_group(db: AsyncSession, slug: str, defaults: dict) -> ResourceGroup:
    result = await db.execute(
        select(ResourceGroup).where(ResourceGroup.slug == slug)
    )
    group = result.scalars().first()
    if group:
        group.name = defaults["name"]
        group.description = defaults.get("description")
        group.sort_order = defaults.get("sort_order", 0)
        group.is_active = True
        return group, False
    group = ResourceGroup(
        slug=slug,
        name=defaults["name"],
        description=defaults.get("description"),
        sort_order=defaults.get("sort_order", 0),
    )
    db.add(group)
    await db.flush()
    return group, True


async def _get_or_create_resource(
    db: AsyncSession,
    key: str,
    group_id: UUID,
    defaults: dict,
    is_static: bool = True,
    setting_node_id: Optional[UUID] = None,
) -> tuple[ResourceDefinition, bool]:
    result = await db.execute(
        select(ResourceDefinition).where(ResourceDefinition.key == key)
    )
    resource = result.scalars().first()
    if resource:
        resource.group_id = group_id
        resource.label = defaults["label"]
        resource.description = defaults.get("description")
        resource.operations = defaults["operations"]
        resource.is_static = is_static
        resource.is_active = True
        if setting_node_id is not None:
            resource.setting_node_id = setting_node_id
        return resource, False
    resource = ResourceDefinition(
        key=key,
        group_id=group_id,
        label=defaults["label"],
        description=defaults.get("description"),
        operations=defaults["operations"],
        is_static=is_static,
        setting_node_id=setting_node_id,
    )
    db.add(resource)
    return resource, True


# ---------------------------------------------------------------------------
# 1. Sync static registry (RESOURCE_GROUPS + RESOURCE_REGISTRY)
# ---------------------------------------------------------------------------

async def sync_static_registry(db: AsyncSession) -> dict:
    """Upsert all groups and static resources from the code registry."""
    groups_created = 0
    groups_updated = 0
    resources_created = 0
    resources_updated = 0

    # Build group slug → id map
    group_id_map: dict[str, UUID] = {}

    for g in RESOURCE_GROUPS:
        group, created = await _get_or_create_group(db, g["slug"], g)
        group_id_map[g["slug"]] = group.id
        if created:
            groups_created += 1
        else:
            groups_updated += 1

    await db.flush()

    for r in RESOURCE_REGISTRY:
        group_id = group_id_map.get(r["group_slug"])
        if not group_id:
            continue
        _, created = await _get_or_create_resource(
            db, r["key"], group_id,
            defaults={
                "label": r["label"],
                "description": r.get("description"),
                "operations": r["operations"],
            },
            is_static=True,
        )
        if created:
            resources_created += 1
        else:
            resources_updated += 1

    return {
        "groups_created": groups_created,
        "groups_updated": groups_updated,
        "resources_created": resources_created,
        "resources_updated": resources_updated,
    }


# ---------------------------------------------------------------------------
# 2. Sync all active leaf SettingNodes as ResourceDefinitions
# ---------------------------------------------------------------------------

async def sync_leaf_nodes(db: AsyncSession) -> int:
    """
    For every active leaf SettingNode, ensure a ResourceDefinition exists
    under the "integrations" group (or a matching group if the slug_path
    prefix maps to a known group).
    Returns count of leaf nodes synced.
    """
    # Ensure integrations group exists
    integrations_group, _ = await _get_or_create_group(db, "integrations", {
        "name": "Integrations",
        "description": "External service and database integrations",
        "sort_order": 5,
    })
    await db.flush()

    stmt = select(SettingNode).where(
        SettingNode.node_type == "leaf",
        SettingNode.is_active.is_(True),
    )
    result = await db.execute(stmt)
    leaf_nodes = result.scalars().all()

    synced = 0
    for node in leaf_nodes:
        key = node.slug_path or node.slug
        label = node.display_label
        description = node.description
        await _get_or_create_resource(
            db, key, integrations_group.id,
            defaults={
                "label": label,
                "description": description,
                "operations": LEAF_NODE_DEFAULT_OPERATIONS,
            },
            is_static=False,
            setting_node_id=node.id,
        )
        synced += 1

    return synced


# ---------------------------------------------------------------------------
# 3. Full sync
# ---------------------------------------------------------------------------

async def sync_all(db: AsyncSession) -> SyncResult:
    """Run full sync: static registry + all leaf nodes."""
    static = await sync_static_registry(db)
    leaf_count = await sync_leaf_nodes(db)
    await db.commit()

    total_result = await db.execute(
        select(ResourceDefinition).where(ResourceDefinition.is_active.is_(True))
    )
    total = len(total_result.scalars().all())

    return SyncResult(
        groups_created=static["groups_created"],
        groups_updated=static["groups_updated"],
        resources_created=static["resources_created"],
        resources_updated=static["resources_updated"],
        leaf_nodes_synced=leaf_count,
        total_resources=total,
    )


# ---------------------------------------------------------------------------
# 4. Upsert a single leaf node (called after create/update)
# ---------------------------------------------------------------------------

async def upsert_leaf_node_resource(db: AsyncSession, node: SettingNode) -> ResourceDefinition:
    """
    Create or update the ResourceDefinition for a single leaf SettingNode.
    Called automatically when a leaf node is created or updated.
    """
    result = await db.execute(
        select(ResourceGroup).where(ResourceGroup.slug == "integrations")
    )
    integrations_group = result.scalars().first()
    if not integrations_group:
        integrations_group = ResourceGroup(
            slug="integrations",
            name="Integrations",
            description="External service and database integrations",
            sort_order=5,
        )
        db.add(integrations_group)
        await db.flush()

    key = node.slug_path or node.slug
    resource, _ = await _get_or_create_resource(
        db, key, integrations_group.id,
        defaults={
            "label": node.display_label,
            "description": node.description,
            "operations": LEAF_NODE_DEFAULT_OPERATIONS,
        },
        is_static=False,
        setting_node_id=node.id,
    )
    await db.flush()
    return resource


# ---------------------------------------------------------------------------
# 5. Deactivate resource when leaf node is soft-deleted
# ---------------------------------------------------------------------------

async def deactivate_leaf_node_resource(db: AsyncSession, node: SettingNode) -> None:
    """
    Mark the ResourceDefinition for a leaf node as inactive when the node
    is soft-deleted. Does not delete — policies referencing it still work.
    """
    key = node.slug_path or node.slug
    result = await db.execute(
        select(ResourceDefinition).where(
            ResourceDefinition.key == key,
            ResourceDefinition.is_static.is_(False),
        )
    )
    resource = result.scalars().first()
    if resource:
        resource.is_active = False
        await db.flush()


# ---------------------------------------------------------------------------
# 6. Validate a resource key exists and is active
# ---------------------------------------------------------------------------

async def validate_resource_key(db: AsyncSession, key: str) -> ResourceDefinition | None:
    """
    Returns the ResourceDefinition if the key is valid and active, else None.
    Used by policy creation/update endpoints.
    """
    result = await db.execute(
        select(ResourceDefinition).where(
            ResourceDefinition.key == key,
            ResourceDefinition.is_active.is_(True),
        )
    )
    return result.scalars().first()


async def get_operations_for_key(db: AsyncSession, key: str) -> list[str]:
    """Returns valid operations list for a resource key, or empty list if not found."""
    resource = await validate_resource_key(db, key)
    return resource.operations if resource else []
