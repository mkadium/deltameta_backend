"""
Pydantic v2 schemas for Auth & Organization Hierarchy API.
"""
from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_password_strength(v: str) -> str:
    if len(v) < 8:
        raise ValueError("Password must be at least 8 characters")
    if not re.search(r"[A-Z]", v):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", v):
        raise ValueError("Password must contain at least one lowercase letter")
    if not re.search(r"\d", v):
        raise ValueError("Password must contain at least one digit")
    return v


# ---------------------------------------------------------------------------
# Auth — Register / Login / Token
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255, description="Full name")
    display_name: Optional[str] = Field(None, max_length=255, description="Displayed name in UI")
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=128, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(..., min_length=8)
    org_name: Optional[str] = Field(None, max_length=255, description="Organization name. Auto-generated from email domain if omitted.")

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return _validate_password_strength(v)


class LoginRequest(BaseModel):
    login: str = Field(..., description="Email address or username")
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Token validity in seconds")


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    reset_token: str
    new_password: str = Field(..., min_length=8)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return _validate_password_strength(v)


# ---------------------------------------------------------------------------
# User schemas
# ---------------------------------------------------------------------------

class TeamSummary(BaseModel):
    id: UUID
    name: str
    display_name: Optional[str] = None
    team_type: str

    model_config = {"from_attributes": True}


class RoleSummary(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None

    model_config = {"from_attributes": True}


class UserResponse(BaseModel):
    id: UUID
    org_id: UUID
    default_org_id: Optional[UUID] = None
    domain_id: Optional[UUID] = None
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    email: str
    username: str
    image: Optional[str] = None
    is_admin: bool
    is_global_admin: bool
    is_active: bool
    is_verified: bool
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    teams: List[TeamSummary] = []
    roles: List[RoleSummary] = []

    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    display_name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    image: Optional[str] = Field(None, max_length=512)
    default_org_id: Optional[UUID] = Field(None, description="Switch active organization context (must be an org the user belongs to)")


# ---------------------------------------------------------------------------
# Organization schemas
# ---------------------------------------------------------------------------

class OrgCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None
    contact_email: Optional[str] = Field(None, max_length=255)


class OrgUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = None
    contact_email: Optional[str] = Field(None, max_length=255)
    owner_id: Optional[UUID] = None
    is_active: Optional[bool] = None


class OrgResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    description: Optional[str] = None
    contact_email: Optional[str] = None
    owner_id: Optional[UUID] = None
    is_active: bool
    is_default: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OrgMemberResponse(BaseModel):
    """A user's membership record in a specific org."""
    user_id: UUID
    org_id: UUID
    is_org_admin: bool
    is_active: bool
    joined_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Auth Config (JWT + lockout settings)
# ---------------------------------------------------------------------------

class AuthConfigResponse(BaseModel):
    org_id: UUID
    jwt_expiry_minutes: int
    max_failed_attempts: int
    lockout_duration_minutes: int
    sso_provider: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class AuthConfigUpdate(BaseModel):
    jwt_expiry_minutes: Optional[int] = Field(None, ge=1, le=10080, description="Token expiry in minutes (1 min – 7 days)")
    max_failed_attempts: Optional[int] = Field(None, ge=1, le=100)
    lockout_duration_minutes: Optional[int] = Field(None, ge=1, le=1440, description="Lockout duration in minutes (max 24h)")


# ---------------------------------------------------------------------------
# Policy schemas
# ---------------------------------------------------------------------------

class ConditionSchema(BaseModel):
    attr: str = Field(..., description="Attribute name: isAdmin, team, organization, domain, role, policy")
    op: str = Field(..., description="Operator: =, !=, in, not_in")
    value: Any = Field(..., description="Value to compare against")


class PolicyCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None
    rule_name: str = Field(..., min_length=2, max_length=255)
    resource: str = Field(..., description="Resource path/identifier this rule governs")
    operations: List[str] = Field(..., description="Allowed operations: view, create, update, delete, allow, deny")
    conditions: List[ConditionSchema] = Field(default_factory=list)


class PolicyResponse(BaseModel):
    id: UUID
    org_id: UUID
    name: str
    description: Optional[str] = None
    rule_name: str
    resource: str
    operations: List[str]
    conditions: List[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PolicyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = None
    rule_name: Optional[str] = None
    resource: Optional[str] = None
    operations: Optional[List[str]] = None
    conditions: Optional[List[ConditionSchema]] = None


# ---------------------------------------------------------------------------
# Role schemas
# ---------------------------------------------------------------------------

class RoleCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None
    policy_ids: List[UUID] = Field(default_factory=list, description="Policies to attach to this role")


class RoleResponse(BaseModel):
    id: UUID
    org_id: UUID
    name: str
    description: Optional[str] = None
    is_system_role: bool
    policies: List[PolicyResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RoleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = None
    policy_ids: Optional[List[UUID]] = None


# ---------------------------------------------------------------------------
# Team schemas
# ---------------------------------------------------------------------------

class TeamCreate(BaseModel):
    org_id: UUID = Field(..., description="Organization this team belongs to. Must be an org the caller is a member of.")
    name: str = Field(..., min_length=2, max_length=255)
    display_name: Optional[str] = Field(None, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    team_type: str = Field("group", description="business_unit | division | department | group")
    description: Optional[str] = None
    domain_id: Optional[UUID] = None
    public_team_view: bool = False
    parent_team_id: Optional[UUID] = None

    @field_validator("team_type")
    @classmethod
    def valid_team_type(cls, v: str) -> str:
        allowed = {"business_unit", "division", "department", "group"}
        if v not in allowed:
            raise ValueError(f"team_type must be one of {allowed}")
        return v


class TeamResponse(BaseModel):
    id: UUID
    org_id: UUID
    parent_team_id: Optional[UUID] = None
    domain_id: Optional[UUID] = None
    name: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    team_type: str
    description: Optional[str] = None
    public_team_view: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TeamUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    display_name: Optional[str] = None
    email: Optional[str] = None
    team_type: Optional[str] = None
    description: Optional[str] = None
    domain_id: Optional[UUID] = None
    public_team_view: Optional[bool] = None
    parent_team_id: Optional[UUID] = None


# ---------------------------------------------------------------------------
# Domain schemas
# ---------------------------------------------------------------------------

class DomainCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None
    domain_type: Optional[str] = Field(None, max_length=100, description="e.g. Engineering, Finance, Sales")
    owner_id: Optional[UUID] = None


class DomainResponse(BaseModel):
    id: UUID
    org_id: UUID
    name: str
    description: Optional[str] = None
    domain_type: Optional[str] = None
    owner_id: Optional[UUID] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DomainUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = None
    domain_type: Optional[str] = None
    owner_id: Optional[UUID] = None
    is_active: Optional[bool] = None


# ---------------------------------------------------------------------------
# Org Preferences schemas
# ---------------------------------------------------------------------------

class OrgPreferencesUpdate(BaseModel):
    description: Optional[str] = None
    contact_email: Optional[str] = Field(None, max_length=255)
    owner_id: Optional[UUID] = None


class OrgPreferencesResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    description: Optional[str] = None
    contact_email: Optional[str] = None
    owner_id: Optional[UUID] = None
    is_active: bool
    is_default: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OrgStatsResponse(BaseModel):
    total_users: int
    total_teams: int
    total_roles: int
    total_policies: int
    total_domains: int
    total_subscriptions: int


# ---------------------------------------------------------------------------
# Subscription schemas
# ---------------------------------------------------------------------------

class SubscriptionResourceType(str, Enum):
    dataset = "dataset"
    data_asset = "data_asset"
    data_product = "data_product"
    team = "team"
    user = "user"
    organization = "organization"
    business_unit = "business_unit"
    division = "division"
    department = "department"
    group = "group"


class SubscriptionCreate(BaseModel):
    resource_type: SubscriptionResourceType
    resource_id: UUID = Field(..., description="ID of the resource being subscribed to")
    subscriber_user_id: Optional[UUID] = Field(None, description="User subscribing (null = org-level subscription)")
    notify_on_update: bool = True


class SubscriptionResponse(BaseModel):
    id: UUID
    org_id: Optional[UUID] = None
    resource_type: str
    resource_id: UUID
    subscriber_user_id: Optional[UUID] = None
    notify_on_update: bool
    subscribed_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Generic responses
# ---------------------------------------------------------------------------

class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    detail: str
