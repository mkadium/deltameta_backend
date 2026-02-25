"""
Pydantic schemas for the dynamic Settings hierarchy API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# SettingNode schemas
# ---------------------------------------------------------------------------

class SettingNodeCreate(BaseModel):
    parent_id: Optional[UUID] = None
    slug: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-z0-9\-_]+$")
    display_label: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    icon: Optional[str] = None
    node_type: str = Field(default="category", pattern=r"^(category|leaf)$")
    nav_url: Optional[str] = None
    slug_path: Optional[str] = None
    sort_order: int = Field(default=0, ge=0)
    metadata_: Optional[Dict[str, Any]] = Field(default=None, alias="metadata")

    model_config = {"populate_by_name": True}


class SettingNodeUpdate(BaseModel):
    display_label: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    icon: Optional[str] = None
    node_type: Optional[str] = Field(default=None, pattern=r"^(category|leaf)$")
    nav_url: Optional[str] = None
    slug_path: Optional[str] = None
    sort_order: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None
    metadata_: Optional[Dict[str, Any]] = Field(default=None, alias="metadata")

    model_config = {"populate_by_name": True}


class SettingNodeResponse(BaseModel):
    id: UUID
    parent_id: Optional[UUID]
    slug: str
    display_label: str
    description: Optional[str]
    icon: Optional[str]
    node_type: str
    nav_url: Optional[str]
    slug_path: Optional[str]
    sort_order: int
    is_active: bool

    # Resolved visibility fields
    has_children: bool = False
    is_enabled: bool = True              # resolved: global AND org override AND policy
    is_enabled_globally: bool = True     # raw global is_active flag
    org_override: Optional[bool] = None  # None = no override; True/False = explicit org setting
    user_override: Optional[bool] = None # None = no override; True/False = explicit user setting

    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# OrgSettingOverride schemas
# ---------------------------------------------------------------------------

class OrgOverrideUpdate(BaseModel):
    is_enabled: bool
    config: Optional[Dict[str, Any]] = None


class OrgOverrideResponse(BaseModel):
    id: UUID
    org_id: UUID
    node_id: UUID
    is_enabled: bool
    config: Optional[Dict[str, Any]]
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# UserSettingOverride schemas
# ---------------------------------------------------------------------------

class UserOverrideUpdate(BaseModel):
    is_enabled: bool


class UserOverrideResponse(BaseModel):
    id: UUID
    user_id: UUID
    node_id: UUID
    is_enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# SettingPolicy schemas
# ---------------------------------------------------------------------------

class SettingPolicyAttach(BaseModel):
    policy_id: UUID


class SettingPolicyResponse(BaseModel):
    id: UUID
    node_id: UUID
    policy_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Breadcrumb for slug-path navigation
# ---------------------------------------------------------------------------

class SettingBreadcrumb(BaseModel):
    slug: str
    display_label: str
    slug_path: Optional[str]
    nav_url: Optional[str]
