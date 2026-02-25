"""
Organization Preferences API router.

Provides read/write access to the current user's organization settings,
and an aggregate stats endpoint.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.auth.models import Domain, Organization, Policy, Role, Subscription, Team, User
from app.auth.schemas import (
    OrgPreferencesResponse,
    OrgPreferencesUpdate,
    OrgStatsResponse,
)
from app.auth.dependencies import require_active_user, require_org_admin

router = APIRouter(prefix="/org", tags=["Organization"])


@router.get("/preferences", response_model=OrgPreferencesResponse, summary="Get organization preferences")
async def get_org_preferences(
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    org = await _get_org_or_404(current_user.org_id, session)
    return _org_to_response(org)


@router.put("/preferences", response_model=OrgPreferencesResponse, summary="Update organization preferences")
async def update_org_preferences(
    body: OrgPreferencesUpdate,
    current_user=Depends(require_org_admin),
    session: AsyncSession = Depends(get_session),
):
    org = await _get_org_or_404(current_user.org_id, session)

    if body.description is not None:
        org.description = body.description
    if body.contact_email is not None:
        org.contact_email = body.contact_email
    if body.owner_id is not None:
        # Validate owner exists in this org
        owner_result = await session.execute(
            select(User).where(User.id == body.owner_id, User.org_id == current_user.org_id)
        )
        if not owner_result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner user not found in this organization")
        org.owner_id = body.owner_id

    org.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(org)
    return _org_to_response(org)


@router.get("/preferences/stats", response_model=OrgStatsResponse, summary="Get organization aggregate stats")
async def get_org_stats(
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    org_id = current_user.org_id

    async def count(model, extra=None):
        q = select(func.count()).select_from(model).where(model.org_id == org_id)
        if extra is not None:
            q = q.where(extra)
        result = await session.execute(q)
        return result.scalar_one()

    total_users = await count(User)
    total_teams = await count(Team)
    total_roles = await count(Role)
    total_policies = await count(Policy)
    total_domains = await count(Domain)
    total_subscriptions = await count(Subscription)

    return OrgStatsResponse(
        total_users=total_users,
        total_teams=total_teams,
        total_roles=total_roles,
        total_policies=total_policies,
        total_domains=total_domains,
        total_subscriptions=total_subscriptions,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_org_or_404(org_id: uuid.UUID, session: AsyncSession) -> Organization:
    result = await session.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org


def _org_to_response(org: Organization) -> OrgPreferencesResponse:
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
