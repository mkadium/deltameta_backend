"""
Pydantic schemas for the main navigation API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# NavItem schemas
# ---------------------------------------------------------------------------

class NavItemCreate(BaseModel):
    parent_id: Optional[UUID] = None
    slug: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-z0-9\-_]+$")
    display_name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    icon: Optional[str] = None
    nav_url: Optional[str] = None
    slug_path: Optional[str] = None
    resource_key: Optional[str] = None
    sort_order: int = Field(default=0, ge=0)
    metadata_: Optional[Dict[str, Any]] = Field(default=None, alias="metadata")

    model_config = {"populate_by_name": True}


class NavItemUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    icon: Optional[str] = None
    nav_url: Optional[str] = None
    slug_path: Optional[str] = None
    resource_key: Optional[str] = None
    sort_order: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None
    metadata_: Optional[Dict[str, Any]] = Field(default=None, alias="metadata")

    model_config = {"populate_by_name": True}


class NavItemResponse(BaseModel):
    id: UUID
    parent_id: Optional[UUID]
    slug: str
    display_name: str
    description: Optional[str]
    icon: Optional[str]
    nav_url: Optional[str]
    slug_path: Optional[str]
    resource_key: Optional[str]
    sort_order: int
    is_active: bool

    has_children: bool = False
    is_enabled: bool = True
    is_enabled_globally: bool = True
    org_override: Optional[bool] = None
    user_override: Optional[bool] = None

    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Nav tree node (recursive) — for GET /nav response
# ---------------------------------------------------------------------------

class NavTreeNode(BaseModel):
    id: UUID
    slug: str
    display_name: str
    description: Optional[str]
    icon: Optional[str]
    nav_url: Optional[str]
    resource_key: Optional[str]
    sort_order: int
    children: List["NavTreeNode"] = []

    model_config = {"from_attributes": True}


NavTreeNode.model_rebuild()


# ---------------------------------------------------------------------------
# Org/User override schemas
# ---------------------------------------------------------------------------

class NavOrgOverrideUpdate(BaseModel):
    is_enabled: bool
    config: Optional[Dict[str, Any]] = None


class NavOrgOverrideResponse(BaseModel):
    id: UUID
    org_id: UUID
    node_id: UUID
    is_enabled: bool
    config: Optional[Dict[str, Any]]
    updated_at: datetime

    model_config = {"from_attributes": True}


class NavUserOverrideUpdate(BaseModel):
    is_enabled: bool


class NavUserOverrideResponse(BaseModel):
    id: UUID
    user_id: UUID
    node_id: UUID
    is_enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# NavItemPolicy schemas
# ---------------------------------------------------------------------------

class NavPolicyAttach(BaseModel):
    policy_id: UUID


class NavPolicyResponse(BaseModel):
    id: UUID
    node_id: UUID
    policy_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}
