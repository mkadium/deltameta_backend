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
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.auth.models import (
    AuthConfig, Domain, Organization, Policy, Role,
    Subscription, Team, User, user_organizations,
)
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
from app.auth.dependencies import require_active_user, require_org_admin

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
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    await _assert_user_in_org(current_user.id, org_id, session)
    result = await session.execute(
        select(User)
        .join(user_organizations, user_organizations.c.user_id == User.id)
        .where(
            user_organizations.c.org_id == org_id,
            user_organizations.c.is_active == True,
        )
        .options(selectinload(User.teams), selectinload(User.roles))
        .offset(skip)
        .limit(limit)
    )
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
    active_org_id = current_user.default_org_id or current_user.org_id
    org = await _get_org_or_404(active_org_id, session)
    return _org_to_preferences_response(org)


@router.put("/org/preferences", response_model=OrgPreferencesResponse, tags=["Organization"], summary="Update active org preferences (org admin only)")
async def update_org_preferences(
    body: OrgPreferencesUpdate,
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    active_org_id = current_user.default_org_id or current_user.org_id
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
async def get_org_stats(
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    active_org_id = current_user.default_org_id or current_user.org_id

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
