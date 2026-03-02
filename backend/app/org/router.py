"""
Organization API router.

Endpoints:
  GET    /orgs                      — List all orgs the current user belongs to
  POST   /orgs                      — Create a new organization
  GET    /orgs/{org_id}             — Get org details
  PUT    /orgs/{org_id}             — Update org (org admin only)
  DELETE /orgs/{org_id}             — Soft delete org (org admin only, cannot delete default org)

  GET    /orgs/{org_id}/members     — List org members
  POST   /orgs/{org_id}/members/{user_id}   — Add user to org (org admin)
  PATCH  /orgs/{org_id}/members/{user_id}   — Update member's is_org_admin flag (org admin)
  DELETE /orgs/{org_id}/members/{user_id}   — Remove user from org (org admin)

  GET    /org/preferences           — Get preferences for current user's active org (backward compat)
  PUT    /org/preferences           — Update preferences for current user's active org
  GET    /org/preferences/stats     — Aggregate stats for current user's active org
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.auth.models import (
    AuthConfig, Domain, Organization, OrgProfilerConfig, Policy, Role,
    Subscription, Team, User, user_organizations,
    user_teams,
)
from app.govern.models import org_roles, org_policies, team_roles, team_policies
from app.auth.schemas import (
    MessageResponse,
    OrgCreate,
    OrgMemberResponse,
    OrgPreferencesResponse,
    OrgPreferencesUpdate,
    OrgResponse,
    OrgStatsResponse,
    OrgUpdate,
    UserResponse,
)
from app.auth.service import slugify
from app.auth.dependencies import get_active_org_id, require_active_user, require_org_admin

router = APIRouter(tags=["Organization"])


# ===========================================================================
# HELPERS
# ===========================================================================

async def _get_org_or_404(org_id: uuid.UUID, session: AsyncSession) -> Organization:
    result = await session.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org


async def _assert_user_in_org(user_id: uuid.UUID, org_id: uuid.UUID, session: AsyncSession) -> dict:
    """Returns the membership row dict or raises 403."""
    result = await session.execute(
        select(user_organizations).where(
            user_organizations.c.user_id == user_id,
            user_organizations.c.org_id == org_id,
            user_organizations.c.is_active == True,
        )
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization",
        )
    return dict(row)


async def _assert_org_admin(user_id: uuid.UUID, org_id: uuid.UUID, session: AsyncSession) -> None:
    """Raises 403 if user is not an org admin for this specific org."""
    result = await session.execute(
        select(user_organizations).where(
            user_organizations.c.user_id == user_id,
            user_organizations.c.org_id == org_id,
            user_organizations.c.is_active == True,
            user_organizations.c.is_org_admin == True,
        )
    )
    if not result.mappings().first():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization admin privileges required for this organization",
        )


# ===========================================================================
# ORGANIZATION CRUD
# ===========================================================================

@router.get("/orgs", response_model=List[OrgResponse], tags=["Organization"], summary="List all orgs the current user belongs to")
async def list_my_orgs(
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Organization)
        .join(user_organizations, user_organizations.c.org_id == Organization.id)
        .where(
            user_organizations.c.user_id == current_user.id,
            user_organizations.c.is_active == True,
            Organization.is_active == True,
        )
        .order_by(Organization.name)
    )
    return result.scalars().all()


@router.post("/orgs", response_model=OrgResponse, status_code=status.HTTP_201_CREATED, tags=["Organization"], summary="Create a new organization")
async def create_org(
    body: OrgCreate,
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    base_slug = slugify(body.name)
    slug = base_slug
    counter = 1
    while True:
        existing = await session.execute(select(Organization).where(Organization.slug == slug))
        if not existing.scalar_one_or_none():
            break
        slug = f"{base_slug}-{counter}"
        counter += 1

    org = Organization(
        id=uuid.uuid4(),
        name=body.name,
        slug=slug,
        description=body.description,
        contact_email=body.contact_email,
        owner_id=current_user.id,
        is_active=True,
        is_default=False,
        created_by=current_user.id,
    )
    session.add(org)
    await session.flush()

    # Create default auth config for new org
    auth_cfg = AuthConfig(
        id=uuid.uuid4(),
        org_id=org.id,
        jwt_expiry_minutes=60,
        max_failed_attempts=5,
        lockout_duration_minutes=15,
        sso_provider="default",
    )
    session.add(auth_cfg)

    # Add creator as org admin member
    await session.execute(
        insert(user_organizations).values(
            id=uuid.uuid4(),
            user_id=current_user.id,
            org_id=org.id,
            is_org_admin=True,
            is_active=True,
        )
    )

    await session.commit()
    await session.refresh(org)
    return org


@router.get("/orgs/{org_id}", response_model=OrgResponse, tags=["Organization"], summary="Get an organization by ID")
async def get_org(
    org_id: uuid.UUID,
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    await _assert_user_in_org(current_user.id, org_id, session)
    return await _get_org_or_404(org_id, session)


@router.put("/orgs/{org_id}", response_model=OrgResponse, tags=["Organization"], summary="Update organization (org admin only)")
async def update_org(
    org_id: uuid.UUID,
    body: OrgUpdate,
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    await _assert_org_admin(current_user.id, org_id, session)
    org = await _get_org_or_404(org_id, session)

    if body.name is not None and body.name != org.name:
        base_slug = slugify(body.name)
        slug = base_slug
        counter = 1
        while True:
            existing = await session.execute(
                select(Organization).where(Organization.slug == slug, Organization.id != org_id)
            )
            if not existing.scalar_one_or_none():
                break
            slug = f"{base_slug}-{counter}"
            counter += 1
        org.name = body.name
        org.slug = slug

    if body.description is not None:
        org.description = body.description
    if body.contact_email is not None:
        org.contact_email = body.contact_email
    if body.owner_id is not None:
        await _assert_user_in_org(body.owner_id, org_id, session)
        org.owner_id = body.owner_id
    if body.is_active is not None:
        org.is_active = body.is_active

    org.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(org)
    return org


@router.delete("/orgs/{org_id}", response_model=MessageResponse, tags=["Organization"], summary="Soft delete an organization (org admin only)")
async def delete_org(
    org_id: uuid.UUID,
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    await _assert_org_admin(current_user.id, org_id, session)
    org = await _get_org_or_404(org_id, session)

    # Prevent deleting the user's default org
    if current_user.default_org_id == org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your default organization. Change your default org first.",
        )

    org.is_active = False
    org.updated_at = datetime.now(timezone.utc)
    await session.commit()
    return MessageResponse(message=f"Organization '{org.name}' has been deactivated")


# ===========================================================================
# MEMBERSHIP MANAGEMENT
# ===========================================================================

@router.get("/orgs/{org_id}/members", response_model=List[UserResponse], tags=["Organization"], summary="List members of an organization")
async def list_org_members(
    org_id: uuid.UUID,
    search: Optional[str] = Query(None, description="Search by name or email."),
    is_active: Optional[bool] = Query(None, description="Filter by active/inactive users."),
    is_org_admin: Optional[bool] = Query(None, description="Filter by org-admin status."),
    domain_id: Optional[uuid.UUID] = Query(None, description="Filter members in a specific subject area."),
    # Relational filters
    team_id: Optional[uuid.UUID] = Query(None, description="Filter members who belong to this team."),
    role_id: Optional[uuid.UUID] = Query(None, description="Filter members who have this role assigned."),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    await _assert_user_in_org(current_user.id, org_id, session)
    from app.auth.models import user_roles
    q = (
        select(User)
        .join(user_organizations, user_organizations.c.user_id == User.id)
        .where(user_organizations.c.org_id == org_id)
        .options(selectinload(User.teams), selectinload(User.roles))
        .distinct()
    )
    if is_active is not None:
        q = q.where(user_organizations.c.is_active == is_active)
    else:
        q = q.where(user_organizations.c.is_active == True)
    if is_org_admin is not None:
        q = q.where(user_organizations.c.is_org_admin == is_org_admin)
    if domain_id is not None:
        q = q.where(User.domain_id == domain_id)
    if search:
        q = q.where(
            User.display_name.ilike(f"%{search}%") |
            User.email.ilike(f"%{search}%") |
            User.username.ilike(f"%{search}%")
        )
    # Relational JOIN filters
    if team_id is not None:
        q = q.join(user_teams, user_teams.c.user_id == User.id).where(user_teams.c.team_id == team_id)
    if role_id is not None:
        q = q.join(user_roles, user_roles.c.user_id == User.id).where(user_roles.c.role_id == role_id)
    q = q.order_by(User.display_name).offset(skip).limit(limit)
    result = await session.execute(q)
    return result.scalars().all()


@router.post(
    "/orgs/{org_id}/members/{user_id}",
    response_model=MessageResponse,
    tags=["Organization"],
    summary="Add a user to an organization (org admin only)",
)
async def add_member_to_org(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    is_org_admin: bool = Query(False, description="Grant org admin role to this member"),
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    await _assert_org_admin(current_user.id, org_id, session)
    await _get_org_or_404(org_id, session)

    # Check user exists
    user_result = await session.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Check already member
    existing = await session.execute(
        select(user_organizations).where(
            user_organizations.c.user_id == user_id,
            user_organizations.c.org_id == org_id,
        )
    )
    row = existing.mappings().first()
    if row:
        if row["is_active"]:
            return MessageResponse(message="User is already a member of this organization")
        # Reactivate
        await session.execute(
            update(user_organizations)
            .where(
                user_organizations.c.user_id == user_id,
                user_organizations.c.org_id == org_id,
            )
            .values(is_active=True, is_org_admin=is_org_admin)
        )
        await session.commit()
        return MessageResponse(message=f"User '{user.name}' re-added to organization")

    await session.execute(
        insert(user_organizations).values(
            id=uuid.uuid4(),
            user_id=user_id,
            org_id=org_id,
            is_org_admin=is_org_admin,
            is_active=True,
        )
    )
    await session.commit()
    return MessageResponse(message=f"User '{user.name}' added to organization")


@router.patch(
    "/orgs/{org_id}/members/{user_id}",
    response_model=OrgMemberResponse,
    tags=["Organization"],
    summary="Update a member's role in the organization (org admin only)",
    description=(
        "Toggle `is_org_admin` for an existing member. "
        "Prevents removing the last admin of an org."
    ),
)
async def update_member_role(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    is_org_admin: bool = Query(..., description="Set to true to promote to org admin, false to demote"),
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    await _assert_org_admin(current_user.id, org_id, session)

    # Fetch the membership row
    result = await session.execute(
        select(user_organizations).where(
            user_organizations.c.user_id == user_id,
            user_organizations.c.org_id == org_id,
            user_organizations.c.is_active == True,
        )
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not an active member of this organization",
        )

    # Guard: cannot demote if this person is the only admin
    if not is_org_admin and row["is_org_admin"]:
        admin_count_result = await session.execute(
            select(func.count()).select_from(user_organizations).where(
                user_organizations.c.org_id == org_id,
                user_organizations.c.is_org_admin == True,
                user_organizations.c.is_active == True,
            )
        )
        if admin_count_result.scalar_one() <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote: this user is the only admin of this organization",
            )

    await session.execute(
        update(user_organizations)
        .where(
            user_organizations.c.user_id == user_id,
            user_organizations.c.org_id == org_id,
        )
        .values(is_org_admin=is_org_admin)
    )
    await session.commit()

    # Return updated membership row
    updated = await session.execute(
        select(user_organizations).where(
            user_organizations.c.user_id == user_id,
            user_organizations.c.org_id == org_id,
        )
    )
    return dict(updated.mappings().first())


@router.delete(
    "/orgs/{org_id}/members/{user_id}",
    response_model=MessageResponse,
    tags=["Organization"],
    summary="Remove a user from an organization (org admin only)",
)
async def remove_member_from_org(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    await _assert_org_admin(current_user.id, org_id, session)

    # Prevent removing yourself if you're the only admin
    if user_id == current_user.id:
        admin_count_result = await session.execute(
            select(func.count()).select_from(user_organizations).where(
                user_organizations.c.org_id == org_id,
                user_organizations.c.is_org_admin == True,
                user_organizations.c.is_active == True,
            )
        )
        if admin_count_result.scalar_one() <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove yourself: you are the only admin of this organization",
            )

    user_result = await session.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    result = await session.execute(
        select(user_organizations).where(
            user_organizations.c.user_id == user_id,
            user_organizations.c.org_id == org_id,
            user_organizations.c.is_active == True,
        )
    )
    if not result.mappings().first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User is not a member of this organization")

    await session.execute(
        update(user_organizations)
        .where(
            user_organizations.c.user_id == user_id,
            user_organizations.c.org_id == org_id,
        )
        .values(is_active=False)
    )
    await session.commit()
    return MessageResponse(message=f"User '{user.name}' removed from organization")


# ===========================================================================
# LEGACY /org/preferences ENDPOINTS (backward compatible, uses active org from JWT)
# ===========================================================================

@router.get("/org/preferences", response_model=OrgPreferencesResponse, tags=["Organization"], summary="Get active org preferences")
async def get_org_preferences(
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    active_org_id = get_active_org_id(current_user)
    org = await _get_org_or_404(active_org_id, session)
    return _org_to_preferences_response(org)


@router.put("/org/preferences", response_model=OrgPreferencesResponse, tags=["Organization"], summary="Update active org preferences (org admin only)")
async def update_org_preferences(
    body: OrgPreferencesUpdate,
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    active_org_id = get_active_org_id(current_user)
    await _assert_org_admin(current_user.id, active_org_id, session)
    org = await _get_org_or_404(active_org_id, session)

    if body.description is not None:
        org.description = body.description
    if body.contact_email is not None:
        org.contact_email = body.contact_email
    if body.owner_id is not None:
        await _assert_user_in_org(body.owner_id, active_org_id, session)
        org.owner_id = body.owner_id

    org.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(org)
    return _org_to_preferences_response(org)


@router.get("/org/preferences/stats", response_model=OrgStatsResponse, tags=["Organization"], summary="Get aggregate stats for active org")
async def get_active_org_stats(
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    active_org_id = get_active_org_id(current_user)

    async def count(model):
        result = await session.execute(
            select(func.count()).select_from(model).where(model.org_id == active_org_id)
        )
        return result.scalar_one()

    total_subscriptions_result = await session.execute(
        select(func.count()).select_from(Subscription).where(Subscription.org_id == active_org_id)
    )
    total_members_result = await session.execute(
        select(func.count()).select_from(user_organizations).where(
            user_organizations.c.org_id == active_org_id,
            user_organizations.c.is_active == True,
        )
    )

    return OrgStatsResponse(
        total_users=total_members_result.scalar_one(),
        total_teams=await count(Team),
        total_roles=await count(Role),
        total_policies=await count(Policy),
        total_domains=await count(Domain),
        total_subscriptions=total_subscriptions_result.scalar_one(),
    )


# ===========================================================================
# ORG STATS + ROLES/POLICIES MANAGEMENT
# ===========================================================================

@router.get("/orgs/{org_id}/stats")
async def get_org_stats(
    org_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """Overview stats for an organization (caller must be a member)."""
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    await _assert_user_in_org(user.id, org_id, db)

    user_count = (await db.execute(
        select(func.count()).where(User.org_id == org_id, User.is_active == True)
    )).scalar_one()
    team_count = (await db.execute(
        select(func.count()).where(Team.org_id == org_id, Team.is_active == True)
    )).scalar_one()
    role_count = (await db.execute(
        select(func.count()).where(Role.org_id == org_id)
    )).scalar_one()
    policy_count = (await db.execute(
        select(func.count()).where(Policy.org_id == org_id)
    )).scalar_one()

    return {
        "org_id": str(org_id),
        "users": user_count,
        "teams": team_count,
        "roles": role_count,
        "policies": policy_count,
    }


@router.get("/orgs/{org_id}/teams-grouped")
async def get_org_teams_grouped(
    org_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """Return teams grouped by team_type for an org landing page (caller must be a member)."""
    await _assert_user_in_org(user.id, org_id, db)
    stmt = select(Team).where(Team.org_id == org_id, Team.is_active == True).order_by(Team.team_type, Team.name)
    result = await db.execute(stmt)
    teams = result.scalars().all()
    grouped: dict = {}
    for t in teams:
        ttype = t.team_type or "group"
        if ttype not in grouped:
            grouped[ttype] = []
        grouped[ttype].append({
            "id": str(t.id),
            "name": t.name,
            "display_name": t.display_name,
            "email": t.email,
            "parent_team_id": str(t.parent_team_id) if t.parent_team_id else None,
        })
    return grouped


@router.get("/orgs/{org_id}/roles")
async def list_org_roles(
    org_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    await _assert_user_in_org(user.id, org_id, db)
    rows = await db.execute(select(org_roles).where(org_roles.c.org_id == org_id))
    role_ids = [r["role_id"] for r in rows.mappings()]
    if not role_ids:
        return []
    result = await db.execute(select(Role).where(Role.id.in_(role_ids)))
    roles = result.scalars().all()
    return [{"id": str(r.id), "name": r.name, "description": r.description} for r in roles]


@router.post("/orgs/{org_id}/roles/{role_id}", status_code=status.HTTP_201_CREATED)
async def assign_role_to_org(
    org_id: uuid.UUID,
    role_id: uuid.UUID,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    await _assert_org_admin(user.id, org_id, db)
    role = await db.execute(select(Role).where(Role.id == role_id, Role.org_id == org_id))
    if not role.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Role not found in this organization")
    await db.execute(
        pg_insert(org_roles).values(org_id=org_id, role_id=role_id).on_conflict_do_nothing()
    )
    await db.commit()
    return {"message": "Role assigned to organization"}


@router.delete("/orgs/{org_id}/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_role_from_org(
    org_id: uuid.UUID,
    role_id: uuid.UUID,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    await _assert_org_admin(user.id, org_id, db)
    await db.execute(
        org_roles.delete().where(org_roles.c.org_id == org_id, org_roles.c.role_id == role_id)
    )
    await db.commit()


@router.get("/orgs/{org_id}/policies")
async def list_org_policies(
    org_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    await _assert_user_in_org(user.id, org_id, db)
    rows = await db.execute(select(org_policies).where(org_policies.c.org_id == org_id))
    policy_ids = [r["policy_id"] for r in rows.mappings()]
    if not policy_ids:
        return []
    result = await db.execute(select(Policy).where(Policy.id.in_(policy_ids)))
    policies = result.scalars().all()
    return [{"id": str(p.id), "name": p.name, "resource": p.resource, "operations": p.operations} for p in policies]


@router.post("/orgs/{org_id}/policies/{policy_id}", status_code=status.HTTP_201_CREATED)
async def assign_policy_to_org(
    org_id: uuid.UUID,
    policy_id: uuid.UUID,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    await _assert_org_admin(user.id, org_id, db)
    policy = await db.execute(select(Policy).where(Policy.id == policy_id, Policy.org_id == org_id))
    if not policy.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Policy not found in this organization")
    await db.execute(
        pg_insert(org_policies).values(org_id=org_id, policy_id=policy_id).on_conflict_do_nothing()
    )
    await db.commit()
    return {"message": "Policy assigned to organization"}


@router.delete("/orgs/{org_id}/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_policy_from_org(
    org_id: uuid.UUID,
    policy_id: uuid.UUID,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    await _assert_org_admin(user.id, org_id, db)
    await db.execute(
        org_policies.delete().where(org_policies.c.org_id == org_id, org_policies.c.policy_id == policy_id)
    )
    await db.commit()


# ===========================================================================
# ORG PROFILER CONFIG
# ===========================================================================

class ProfilerConfigEntry(BaseModel):
    datatype: str = Field(..., description="e.g. bigint, varchar, timestamp, boolean")
    metric_types: List[str] = Field(..., description="e.g. ['null_count', 'distinct_count', 'min', 'max', 'mean']")

    model_config = {"from_attributes": True}


class ProfilerConfigResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    datatype: str
    metric_types: List[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProfilerConfigBulkUpdate(BaseModel):
    entries: List[ProfilerConfigEntry] = Field(..., description="Full replace of all profiler config entries for the org")


@router.get("/org/profiler-config", response_model=List[ProfilerConfigResponse], tags=["Organization"])
async def get_profiler_config(
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    """Get org-level profiler config (which metrics apply to which datatypes)."""
    active_org = get_active_org_id(user)
    result = await db.execute(
        select(OrgProfilerConfig)
        .where(OrgProfilerConfig.org_id == active_org)
        .order_by(OrgProfilerConfig.datatype)
    )
    return result.scalars().all()


@router.put("/org/profiler-config", response_model=List[ProfilerConfigResponse], tags=["Organization"])
async def update_profiler_config(
    body: ProfilerConfigBulkUpdate,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    """Full replace of profiler config for the org — deletes existing, inserts new."""
    active_org = get_active_org_id(user)
    await db.execute(
        OrgProfilerConfig.__table__.delete().where(OrgProfilerConfig.org_id == active_org)
    )
    new_entries = [
        OrgProfilerConfig(
            id=uuid.uuid4(),
            org_id=active_org,
            datatype=entry.datatype,
            metric_types=entry.metric_types,
        )
        for entry in body.entries
    ]
    db.add_all(new_entries)
    await db.commit()
    result = await db.execute(
        select(OrgProfilerConfig)
        .where(OrgProfilerConfig.org_id == active_org)
        .order_by(OrgProfilerConfig.datatype)
    )
    return result.scalars().all()


# ===========================================================================
# HELPERS
# ===========================================================================

def _org_to_preferences_response(org: Organization) -> OrgPreferencesResponse:
    return OrgPreferencesResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        description=org.description,
        contact_email=getattr(org, "contact_email", None),
        owner_id=getattr(org, "owner_id", None),
        is_active=org.is_active,
        is_default=org.is_default,
        created_at=org.created_at,
        updated_at=org.updated_at,
    )
