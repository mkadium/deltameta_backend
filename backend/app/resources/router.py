"""
Resource Registry API.

Endpoints:
  GET  /resources                        list all groups with their resources (for policy dropdowns)
  GET  /resources/flat                   flat list of all active resources
  GET  /resources/{key}/operations       get valid operations for a specific resource key
  POST /resources/sync                   admin triggers full sync from code registry + leaf nodes
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import require_active_user, require_org_admin
from app.auth.models import User
from app.db import get_session
from app.resources.models import ResourceDefinition, ResourceGroup
from app.resources.schemas import (
    ResourceDefinitionResponse,
    ResourceGroupResponse,
    ResourceOperationsResponse,
    SyncResult,
)
from app.resources.service import get_operations_for_key, sync_all, validate_resource_key

router = APIRouter(prefix="/resources", tags=["Resources"])


# ---------------------------------------------------------------------------
# GET /resources — all groups with nested resources (used for policy dropdowns)
# ---------------------------------------------------------------------------

@router.get("", response_model=List[ResourceGroupResponse])
async def list_resource_groups(
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Returns all active resource groups with their resource definitions.
    Used by frontend to populate the resource + operations dropdowns when creating policies.

    Response shape:
    [
      {
        "slug": "identity-access",
        "name": "Identity & Access",
        "resources": [
          { "key": "user", "label": "User", "operations": ["read", "create", ...] },
          ...
        ]
      },
      ...
    ]
    """
    result = await db.execute(
        select(ResourceGroup)
        .where(ResourceGroup.is_active.is_(True))
        .order_by(ResourceGroup.sort_order, ResourceGroup.name)
        .options(
            selectinload(ResourceGroup.resources)
        )
    )
    groups = result.scalars().all()

    # Filter resources to only active ones within each group
    output = []
    for group in groups:
        active_resources = [r for r in group.resources if r.is_active]
        # Sort resources alphabetically
        active_resources.sort(key=lambda r: r.label)
        output.append(ResourceGroupResponse(
            id=group.id,
            slug=group.slug,
            name=group.name,
            description=group.description,
            sort_order=group.sort_order,
            is_active=group.is_active,
            resources=[ResourceDefinitionResponse.model_validate(r) for r in active_resources],
        ))

    return output


# ---------------------------------------------------------------------------
# GET /resources/flat — flat list of all active resources (simpler dropdown)
# ---------------------------------------------------------------------------

@router.get("/flat", response_model=List[ResourceDefinitionResponse])
async def list_resources_flat(
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Flat list of all active resource definitions sorted by group + label.
    Useful for a simple searchable dropdown.
    """
    result = await db.execute(
        select(ResourceDefinition)
        .where(ResourceDefinition.is_active.is_(True))
        .order_by(ResourceDefinition.key)
    )
    return [
        ResourceDefinitionResponse.model_validate(r)
        for r in result.scalars().all()
    ]


# ---------------------------------------------------------------------------
# GET /resources/{key}/operations — get valid operations for a resource key
# ---------------------------------------------------------------------------

@router.get("/{key:path}/operations", response_model=ResourceOperationsResponse)
async def get_resource_operations(
    key: str,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Returns the valid operations for a given resource key.
    Frontend calls this when the admin selects a resource to populate
    the operations checkboxes.

    Example:
      GET /resources/user/operations
      → { "key": "user", "operations": ["read", "create", "update", "delete", "impersonate"] }

      GET /resources/services.databases.postgres/operations
      → { "key": "services.databases.postgres", "operations": ["read", "configure"] }
    """
    result = await db.execute(
        select(ResourceDefinition, ResourceGroup)
        .join(ResourceGroup, ResourceDefinition.group_id == ResourceGroup.id)
        .where(
            ResourceDefinition.key == key,
            ResourceDefinition.is_active.is_(True),
        )
    )
    row = result.first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource '{key}' not found or inactive",
        )
    resource, group = row
    return ResourceOperationsResponse(
        key=resource.key,
        label=resource.label,
        operations=resource.operations,
        group_slug=group.slug,
        group_name=group.name,
    )


# ---------------------------------------------------------------------------
# POST /resources/sync — admin triggers sync from code registry + leaf nodes
# ---------------------------------------------------------------------------

@router.post("/sync", response_model=SyncResult)
async def sync_resources(
    current_user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    """
    Sync the resource registry from:
    1. Static code registry (RESOURCE_GROUPS + RESOURCE_REGISTRY in registry.py)
    2. All active leaf SettingNodes (keyed by slug_path)

    Returns a summary of what was created/updated.
    Should be run by an admin after:
    - New platform features are deployed (code registry updated)
    - New leaf setting nodes are added
    - After initial deployment to populate the DB

    Idempotent — safe to run multiple times.
    """
    return await sync_all(db)
