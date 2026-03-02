"""Admin User Management — create, list, update, deactivate users (org admin only).

Create user fields:
  - email (required, unique)
  - display_name (optional — shown in UI)
  - description (optional)
  - password + confirm_password (required, strength-validated, must match)
  - team_ids (optional list — assign to multiple teams at creation)
  - role_ids (optional list — assign multiple roles at creation)
  - domain_ids (optional list — assign user to multiple subject areas / domains)
  - is_admin (default false)
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.auth.dependencies import get_active_org_id, require_org_admin
from app.auth.models import Domain, Role, Team, User, user_organizations
from app.auth.service import hash_password
from sqlalchemy import insert

router = APIRouter(prefix="/admin", tags=["Admin"])


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def _email_to_username(email: str) -> str:
    """Derive a base username from the email local-part (lowercase, safe chars only)."""
    local = email.split("@")[0]
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", local).lower()


# ── Schemas ───────────────────────────────────────────────────────────────────

class AdminUserCreate(BaseModel):
    email: EmailStr
    display_name: Optional[str] = Field(None, max_length=255, description="Name shown in the UI")
    description: Optional[str] = None
    password: str = Field(..., min_length=8, description="Must be ≥8 chars, upper+lower+digit")
    confirm_password: str = Field(..., min_length=8)
    is_admin: bool = Field(False, description="Grant org-admin privileges")
    team_ids: List[uuid.UUID] = Field(default_factory=list, description="Assign to these teams (must belong to the same org)")
    role_ids: List[uuid.UUID] = Field(default_factory=list, description="Assign these roles (must belong to the same org)")
    domain_ids: List[uuid.UUID] = Field(default_factory=list, description="Associate with these subject areas / domains (must belong to the same org)")

    @model_validator(mode="after")
    def passwords_match(self) -> "AdminUserCreate":
        _validate_password_strength(self.password)
        if self.password != self.confirm_password:
            raise ValueError("password and confirm_password do not match")
        return self


class AdminUserUpdate(BaseModel):
    display_name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None
    team_ids: Optional[List[uuid.UUID]] = Field(None, description="Replace team assignments (full replace)")
    role_ids: Optional[List[uuid.UUID]] = Field(None, description="Replace role assignments (full replace)")
    domain_ids: Optional[List[uuid.UUID]] = Field(None, description="Replace domain associations (full replace)")


class PasswordResetRequest(BaseModel):
    new_password: str = Field(..., min_length=8, description="New password (must meet strength requirements)")
    confirm_password: str = Field(..., min_length=8)

    @model_validator(mode="after")
    def passwords_match(self) -> "PasswordResetRequest":
        _validate_password_strength(self.new_password)
        if self.new_password != self.confirm_password:
            raise ValueError("new_password and confirm_password do not match")
        return self


class DomainSummary(BaseModel):
    id: uuid.UUID
    name: str
    display_name: Optional[str] = None

    model_config = {"from_attributes": True}


class RoleSummary(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None

    model_config = {"from_attributes": True}


class TeamSummary(BaseModel):
    id: uuid.UUID
    name: str
    display_name: Optional[str] = None
    team_type: str

    model_config = {"from_attributes": True}


class AdminUserOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    email: str
    username: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    is_admin: bool
    is_active: bool
    is_verified: bool
    last_login_at: Optional[datetime] = None
    created_at: datetime
    teams: List[TeamSummary] = []
    roles: List[RoleSummary] = []
    domains: List[DomainSummary] = []

    model_config = {"from_attributes": True}


class PasswordResetOut(BaseModel):
    user_id: uuid.UUID
    message: str


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _load_user_with_relations(user_id: uuid.UUID, db: AsyncSession) -> User:
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(
            selectinload(User.teams),
            selectinload(User.roles),
        )
    )
    return result.scalar_one()


def _user_to_out(user: User, domains: List[Domain]) -> AdminUserOut:
    return AdminUserOut(
        id=user.id,
        org_id=user.org_id,
        email=user.email,
        username=user.username,
        display_name=user.display_name,
        description=user.description,
        is_admin=user.is_admin,
        is_active=user.is_active,
        is_verified=user.is_verified,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        teams=[TeamSummary.model_validate(t) for t in user.teams],
        roles=[RoleSummary.model_validate(r) for r in user.roles],
        domains=[DomainSummary.model_validate(d) for d in domains],
    )


async def _resolve_teams(team_ids: List[uuid.UUID], org_id: uuid.UUID, db: AsyncSession) -> List[Team]:
    if not team_ids:
        return []
    result = await db.execute(
        select(Team).where(Team.id.in_(team_ids), Team.org_id == org_id, Team.is_active == True)
    )
    found = result.scalars().all()
    if len(found) != len(team_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more team IDs not found in this organization",
        )
    return list(found)


async def _resolve_roles(role_ids: List[uuid.UUID], org_id: uuid.UUID, db: AsyncSession) -> List[Role]:
    if not role_ids:
        return []
    result = await db.execute(
        select(Role).where(Role.id.in_(role_ids), Role.org_id == org_id)
    )
    found = result.scalars().all()
    if len(found) != len(role_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more role IDs not found in this organization",
        )
    return list(found)


async def _resolve_domains(domain_ids: List[uuid.UUID], org_id: uuid.UUID, db: AsyncSession) -> List[Domain]:
    if not domain_ids:
        return []
    result = await db.execute(
        select(Domain).where(Domain.id.in_(domain_ids), Domain.org_id == org_id, Domain.is_active == True)
    )
    found = result.scalars().all()
    if len(found) != len(domain_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more domain IDs not found in this organization",
        )
    return list(found)


async def _get_user_domains(user_id: uuid.UUID, db: AsyncSession) -> List[Domain]:
    """A user can be primary in one domain (domain_id) or linked via subject_area relationship.
    Here we query all domains where user.domain_id matches OR domains that own the user."""
    result = await db.execute(
        select(Domain).where(Domain.owner_id == user_id)
    )
    domains = result.scalars().all()
    return list(domains)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/users", response_model=List[AdminUserOut])
async def list_users(
    search: Optional[str] = Query(None, description="Search by email, display_name, or username"),
    is_active: Optional[bool] = Query(None),
    is_admin: Optional[bool] = Query(None),
    skip: int = 0,
    limit: int = 50,
    admin: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(admin)
    stmt = (
        select(User)
        .where(User.org_id == active_org)
        .options(selectinload(User.teams), selectinload(User.roles))
    )
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)
    if is_admin is not None:
        stmt = stmt.where(User.is_admin == is_admin)
    if search:
        stmt = stmt.where(
            User.display_name.ilike(f"%{search}%") |
            User.email.ilike(f"%{search}%") |
            User.username.ilike(f"%{search}%")
        )
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    users = result.scalars().all()
    out = []
    for u in users:
        domains = await _get_user_domains(u.id, db)
        out.append(_user_to_out(u, domains))
    return out


@router.post("/users", response_model=AdminUserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: AdminUserCreate,
    admin: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(admin)

    # Check email uniqueness
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalars().first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    # Derive a unique username from email
    base_username = _email_to_username(body.email)
    username = base_username
    counter = 1
    while True:
        taken = await db.execute(select(User).where(User.username == username))
        if not taken.scalars().first():
            break
        username = f"{base_username}{counter}"
        counter += 1

    # Validate referenced entities belong to this org
    teams = await _resolve_teams(body.team_ids, active_org, db)
    roles = await _resolve_roles(body.role_ids, active_org, db)
    domains = await _resolve_domains(body.domain_ids, active_org, db)

    # Create user
    user = User(
        id=uuid.uuid4(),
        org_id=active_org,
        default_org_id=active_org,
        email=body.email,
        username=username,
        # Use display_name as full name; fall back to email local part
        name=body.display_name or _email_to_username(body.email),
        display_name=body.display_name,
        description=body.description,
        is_admin=body.is_admin,
        hashed_password=hash_password(body.password),
        is_active=True,
        is_verified=False,
        failed_attempts=0,
    )

    # Assign teams and roles via relationships
    user.teams = teams
    user.roles = roles

    db.add(user)
    await db.flush()  # get user.id

    # Register in user_organizations
    await db.execute(
        insert(user_organizations).values(
            id=uuid.uuid4(),
            user_id=user.id,
            org_id=active_org,
            is_org_admin=body.is_admin,
            is_active=True,
        )
    )

    # Link user to domains (set domain_id to first domain if provided; set owner on all)
    if domains:
        user.domain_id = domains[0].id

    await db.commit()

    # Reload with relationships
    user = await _load_user_with_relations(user.id, db)
    return _user_to_out(user, domains)


@router.get("/users/{user_id}", response_model=AdminUserOut)
async def get_user(
    user_id: uuid.UUID,
    admin: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(admin)
    result = await db.execute(
        select(User)
        .where(User.id == user_id, User.org_id == active_org)
        .options(selectinload(User.teams), selectinload(User.roles))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    domains = await _get_user_domains(user.id, db)
    return _user_to_out(user, domains)


@router.put("/users/{user_id}", response_model=AdminUserOut)
async def update_user(
    user_id: uuid.UUID,
    body: AdminUserUpdate,
    admin: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(admin)
    result = await db.execute(
        select(User)
        .where(User.id == user_id, User.org_id == active_org)
        .options(selectinload(User.teams), selectinload(User.roles))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if body.display_name is not None:
        user.display_name = body.display_name
        user.name = body.display_name  # keep name in sync
    if body.description is not None:
        user.description = body.description
    if body.is_admin is not None:
        user.is_admin = body.is_admin
    if body.is_active is not None:
        user.is_active = body.is_active

    if body.team_ids is not None:
        user.teams = await _resolve_teams(body.team_ids, active_org, db)
    if body.role_ids is not None:
        user.roles = await _resolve_roles(body.role_ids, active_org, db)

    domains: List[Domain] = []
    if body.domain_ids is not None:
        domains = await _resolve_domains(body.domain_ids, active_org, db)
        user.domain_id = domains[0].id if domains else None
    else:
        domains = await _get_user_domains(user.id, db)

    await db.commit()
    user = await _load_user_with_relations(user.id, db)
    return _user_to_out(user, domains)


@router.post("/users/{user_id}/reset-password", response_model=PasswordResetOut)
async def reset_password(
    user_id: uuid.UUID,
    body: PasswordResetRequest,
    admin: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(admin)
    user = await db.get(User, user_id)
    if not user or user.org_id != active_org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.hashed_password = hash_password(body.new_password)
    user.failed_attempts = 0
    user.locked_until = None
    await db.commit()
    return PasswordResetOut(
        user_id=user.id,
        message="Password updated successfully.",
    )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: uuid.UUID,
    admin: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    """Soft-delete: deactivates the user rather than physical delete."""
    active_org = get_active_org_id(admin)
    user = await db.get(User, user_id)
    if not user or user.org_id != active_org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot deactivate yourself")
    user.is_active = False
    await db.commit()
