"""
Policies API router — ABAC policy CRUD.

Policy structure:
  - resource: key from resource_definitions (e.g. "user", "team",
              "services.databases.postgres") — validated against registry
  - operations: subset of the resource's valid operations — validated against registry
  - conditions: list of attribute-based conditions [{attr, op, value}]

Policies are stored in the DB. Enforcement is a FUTURE phase.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.auth.models import Policy, User, user_policies, role_policies
from app.auth.schemas import (
    MessageResponse,
    PolicyCreate,
    PolicyResponse,
    PolicyUpdate,
)
from app.auth.dependencies import get_active_org_id, require_active_user, require_org_admin
from app.resources.service import validate_resource_key, get_operations_for_key
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import selectinload
from app.govern.models import team_policies, org_policies

router = APIRouter(prefix="/policies", tags=["Policies"])


# ---------------------------------------------------------------------------
# Internal validation helper
# ---------------------------------------------------------------------------

async def _validate_resource_and_operations(
    resource: str,
    operations: List[str],
    session: AsyncSession,
) -> None:
    """
    Validate that:
    1. resource key exists in resource_definitions and is active
    2. every operation is in the resource's valid operations list
    Raises 422 if invalid.
    """
    resource_def = await validate_resource_key(session, resource)
    if not resource_def:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Resource '{resource}' is not a valid resource key. "
                "Call GET /resources to see all available resources."
            ),
        )
    valid_ops = set(resource_def.operations)
    invalid_ops = [op for op in operations if op not in valid_ops]
    if invalid_ops:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid operations {invalid_ops} for resource '{resource}'. "
                f"Valid operations: {sorted(valid_ops)}"
            ),
        )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.get("", response_model=List[PolicyResponse], summary="List policies for the current org")
async def list_policies(
    resource: Optional[str] = Query(None, description="Filter by resource path (substring match)."),
    search: Optional[str] = Query(None, description="Search by policy name or rule_name."),
    # Relational filters
    role_id: Optional[uuid.UUID] = Query(None, description="Filter policies assigned to a specific role."),
    team_id: Optional[uuid.UUID] = Query(None, description="Filter policies assigned to a specific team."),
    user_id: Optional[uuid.UUID] = Query(None, description="Filter policies directly assigned to a specific user."),
    org_id_filter: Optional[uuid.UUID] = Query(None, alias="org_id_assigned", description="Filter policies assigned to a specific org."),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    q = select(Policy).where(Policy.org_id == get_active_org_id(current_user)).distinct()
    if resource:
        q = q.where(Policy.resource.ilike(f"%{resource}%"))
    if search:
        q = q.where(Policy.name.ilike(f"%{search}%") | Policy.rule_name.ilike(f"%{search}%"))
    # Relational JOIN filters
    if role_id is not None:
        q = q.join(role_policies, role_policies.c.policy_id == Policy.id).where(role_policies.c.role_id == role_id)
    if team_id is not None:
        q = q.join(team_policies, team_policies.c.policy_id == Policy.id).where(team_policies.c.team_id == team_id)
    if user_id is not None:
        q = q.join(user_policies, user_policies.c.policy_id == Policy.id).where(user_policies.c.user_id == user_id)
    if org_id_filter is not None:
        q = q.join(org_policies, org_policies.c.policy_id == Policy.id).where(org_policies.c.org_id == org_id_filter)
    q = q.order_by(Policy.name).offset(skip).limit(limit)
    result = await session.execute(q)
    return result.scalars().all()


@router.post("", response_model=PolicyResponse, status_code=status.HTTP_201_CREATED, summary="Create a policy")
async def create_policy(
    body: PolicyCreate,
    current_user=Depends(require_org_admin),
    session: AsyncSession = Depends(get_session),
):
    # Validate resource key and operations against the registry
    await _validate_resource_and_operations(body.resource, body.operations, session)

    existing = await session.execute(
        select(Policy).where(Policy.org_id == get_active_org_id(current_user), Policy.name == body.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Policy name already exists in this organization")

    policy = Policy(
        id=uuid.uuid4(),
        org_id=get_active_org_id(current_user),
        name=body.name,
        description=body.description,
        rule_name=body.rule_name,
        resource=body.resource,
        operations=body.operations,
        conditions=[c.model_dump() for c in body.conditions],
    )
    session.add(policy)
    await session.commit()
    await session.refresh(policy)
    return policy


@router.get("/{policy_id}", response_model=PolicyResponse, summary="Get a policy by ID")
async def get_policy(
    policy_id: uuid.UUID,
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    return await _get_policy_or_404(policy_id, get_active_org_id(current_user), session)


@router.put("/{policy_id}", response_model=PolicyResponse, summary="Update a policy")
async def update_policy(
    policy_id: uuid.UUID,
    body: PolicyUpdate,
    current_user=Depends(require_org_admin),
    session: AsyncSession = Depends(get_session),
):
    policy = await _get_policy_or_404(policy_id, get_active_org_id(current_user), session)

    # Validate resource/operations if being updated
    new_resource = body.resource if body.resource is not None else policy.resource
    new_operations = body.operations if body.operations is not None else policy.operations
    await _validate_resource_and_operations(new_resource, new_operations, session)

    if body.name is not None and body.name != policy.name:
        existing = await session.execute(
            select(Policy).where(Policy.org_id == get_active_org_id(current_user), Policy.name == body.name)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Policy name already exists")
        policy.name = body.name

    if body.description is not None:
        policy.description = body.description
    if body.rule_name is not None:
        policy.rule_name = body.rule_name
    if body.resource is not None:
        policy.resource = body.resource
    if body.operations is not None:
        policy.operations = body.operations
    if body.conditions is not None:
        policy.conditions = [c.model_dump() for c in body.conditions]

    policy.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(policy)
    return policy


@router.delete("/{policy_id}", response_model=MessageResponse, summary="Delete a policy")
async def delete_policy(
    policy_id: uuid.UUID,
    current_user=Depends(require_org_admin),
    session: AsyncSession = Depends(get_session),
):
    policy = await _get_policy_or_404(policy_id, get_active_org_id(current_user), session)
    await session.delete(policy)
    await session.commit()
    return MessageResponse(message=f"Policy '{policy.name}' deleted successfully")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_policy_or_404(policy_id: uuid.UUID, org_id: uuid.UUID, session: AsyncSession) -> Policy:
    result = await session.execute(
        select(Policy).where(Policy.id == policy_id, Policy.org_id == org_id)
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    return policy


async def _get_user_in_org(user_id: uuid.UUID, org_id: uuid.UUID, session: AsyncSession) -> User:
    result = await session.execute(
        select(User)
        .where(User.id == user_id, User.org_id == org_id)
        .options(selectinload(User.policies))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found in this organization")
    return user


# ---------------------------------------------------------------------------
# User ↔ Policy management
# ---------------------------------------------------------------------------

@router.get(
    "/{policy_id}/users",
    response_model=List[dict],
    summary="List users who have this policy directly assigned",
)
async def list_policy_users(
    policy_id: uuid.UUID,
    current_user=Depends(require_org_admin),
    session: AsyncSession = Depends(get_session),
):
    policy = await _get_policy_or_404(policy_id, get_active_org_id(current_user), session)
    rows = await session.execute(
        select(user_policies).where(user_policies.c.policy_id == policy.id)
    )
    user_ids = [r["user_id"] for r in rows.mappings()]
    if not user_ids:
        return []
    result = await session.execute(
        select(User).where(User.id.in_(user_ids))
    )
    users = result.scalars().all()
    return [{"id": str(u.id), "name": u.name, "email": u.email, "username": u.username} for u in users]


class BulkUserIds(BaseModel):
    user_ids: List[uuid.UUID]


@router.post(
    "/{policy_id}/assign",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Bulk assign a policy directly to users",
)
async def assign_policy_to_users(
    policy_id: uuid.UUID,
    body: BulkUserIds,
    current_user=Depends(require_org_admin),
    session: AsyncSession = Depends(get_session),
):
    """Assign this policy to one or more users at once."""
    policy = await _get_policy_or_404(policy_id, get_active_org_id(current_user), session)
    assigned = 0
    for uid in body.user_ids:
        user = await _get_user_in_org(uid, get_active_org_id(current_user), session)
        if not any(p.id == policy_id for p in user.policies):
            await session.execute(
                pg_insert(user_policies)
                .values(user_id=uid, policy_id=policy_id)
                .on_conflict_do_nothing()
            )
            assigned += 1
    await session.commit()
    return MessageResponse(message=f"Policy '{policy.name}' assigned to {assigned} user(s)")


@router.delete(
    "/{policy_id}/assign/{user_id}",
    response_model=MessageResponse,
    summary="Remove a directly-assigned policy from a user",
)
async def remove_policy_from_user(
    policy_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user=Depends(require_org_admin),
    session: AsyncSession = Depends(get_session),
):
    policy = await _get_policy_or_404(policy_id, get_active_org_id(current_user), session)
    user = await _get_user_in_org(user_id, get_active_org_id(current_user), session)

    if not any(p.id == policy_id for p in user.policies):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User does not have this policy directly assigned",
        )

    await session.execute(
        user_policies.delete().where(
            user_policies.c.user_id == user_id,
            user_policies.c.policy_id == policy_id,
        )
    )
    await session.commit()
    return MessageResponse(message=f"Policy '{policy.name}' removed from user '{user.name}'")


# ---------------------------------------------------------------------------
# User-centric policy view
# ---------------------------------------------------------------------------

@router.get(
    "/user/{user_id}",
    response_model=List[PolicyResponse],
    summary="List policies directly assigned to a user",
)
async def list_user_policies(
    user_id: uuid.UUID,
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    user = await _get_user_in_org(user_id, get_active_org_id(current_user), session)
    return user.policies
