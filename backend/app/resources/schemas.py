"""
Pydantic schemas for the Resource Registry API.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# ResourceDefinition schemas
# ---------------------------------------------------------------------------

class ResourceDefinitionResponse(BaseModel):
    id: UUID
    key: str
    label: str
    description: Optional[str]
    operations: List[str]
    is_static: bool
    is_active: bool
    setting_node_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# ResourceGroup schemas
# ---------------------------------------------------------------------------

class ResourceGroupResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    description: Optional[str]
    sort_order: int
    is_active: bool
    resources: List[ResourceDefinitionResponse] = []

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Sync result schema
# ---------------------------------------------------------------------------

class SyncResult(BaseModel):
    groups_created: int
    groups_updated: int
    resources_created: int
    resources_updated: int
    leaf_nodes_synced: int
    total_resources: int


# ---------------------------------------------------------------------------
# Operations lookup response
# ---------------------------------------------------------------------------

class ResourceOperationsResponse(BaseModel):
    key: str
    label: str
    operations: List[str]
    group_slug: str
    group_name: str
