"""
Roles API router — CRUD for roles and assigning roles to users.
System roles (is_system_role=True) cannot be deleted or modified by org admins.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.auth.models import Policy, Role, Team, User, user_roles
from app.auth.schemas import MessageResponse, PolicyResponse, RoleCreate, RoleResponse, RoleUpdate, TeamResponse, UserResponse
from app.auth.dependencies import get_active_org_id, require_active_user, require_org_admin
from app.govern.models import team_roles, org_roles

router = APIRouter(prefix="/roles", tags=["Roles"])


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.get("", response_model=List[RoleResponse], summary="List roles for the current org")
async def list_roles(
    search: Optional[str] = Query(None, description="Search by role name."),
    is_system_role: Optional[bool] = Query(None, description="Filter system roles vs custom roles."),
    # Relational filters
    user_id: Optional[uuid.UUID] = Query(None, description="Filter roles assigned to a specific user."),
    team_id: Optional[uuid.UUID] = Query(None, description="Filter roles assigned to a specific team."),
    org_id_filter: Optional[uuid.UUID] = Query(None, alias="org_id_assigned", description="Filter roles assigned to a specific org."),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    q = (
        select(Role)
        .where(Role.org_id == get_active_org_id(current_user))
        .options(selectinload(Role.policies))
        .order_by(Role.name)
        .distinct()
    )
    if search:
        q = q.where(Role.name.ilike(f"%{search}%"))
    if is_system_role is not None:
        q = q.where(Role.is_system_role == is_system_role)
    # Relational JOIN filters
    if user_id is not None:
        q = q.join(user_roles, user_roles.c.role_id == Role.id).where(user_roles.c.user_id == user_id)
    if team_id is not None:
        q = q.join(team_roles, team_roles.c.role_id == Role.id).where(team_roles.c.team_id == team_id)
    if org_id_filter is not None:
        q = q.join(org_roles, org_roles.c.role_id == Role.id).where(org_roles.c.org_id == org_id_filter)
    q = q.offset(skip).limit(limit)
    result = await session.execute(q)
    return result.scalars().all()


@router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED, summary="Create a role")
async def create_role(
    body: RoleCreate,
    current_user=Depends(require_org_admin),
    session: AsyncSession = Depends(get_session),
):
    existing = await session.execute(
        select(Role).where(Role.org_id == get_active_org_id(current_user), Role.name == body.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Role name already exists in this organization")

    role = Role(
        id=uuid.uuid4(),
        org_id=get_active_org_id(current_user),
        name=body.name,
        description=body.description,
        is_system_role=False,
    )

    if body.policy_ids:
        policies = await _load_policies(body.policy_ids, get_active_org_id(current_user), session)
        role.policies = policies

    session.add(role)
    await session.commit()

    # Reload with relationships
    result = await session.execute(
        select(Role).where(Role.id == role.id).options(selectinload(Role.policies))
    )
    return result.scalar_one()


@router.get("/{role_id}", response_model=RoleResponse, summary="Get a role by ID")
async def get_role(
    role_id: uuid.UUID,
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    return await _get_role_or_404(role_id, get_active_org_id(current_user), session, load_policies=True)


@router.put("/{role_id}", response_model=RoleResponse, summary="Update a role (system roles are protected)")
async def update_role(
    role_id: uuid.UUID,
    body: RoleUpdate,
    current_user=Depends(require_org_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Role)
        .where(Role.id == role_id, Role.org_id == get_active_org_id(current_user))
        .options(selectinload(Role.policies))
    )
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.is_system_role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="System roles cannot be modified")

    if body.name is not None and body.name != role.name:
        existing = await session.execute(
            select(Role).where(Role.org_id == get_active_org_id(current_user), Role.name == body.name)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Role name already exists")
        role.name = body.name

    if body.description is not None:
        role.description = body.description

    if body.policy_ids is not None:
        role.policies = await _load_policies(body.policy_ids, get_active_org_id(current_user), session)

    role.updated_at = datetime.now(timezone.utc)
    await session.commit()

    result = await session.execute(
        select(Role).where(Role.id == role_id).options(selectinload(Role.policies))
    )
    return result.scalar_one()


@router.delete("/{role_id}", response_model=MessageResponse, summary="Delete a role (system roles are protected)")
async def delete_role(
    role_id: uuid.UUID,
    current_user=Depends(require_org_admin),
    session: AsyncSession = Depends(get_session),
):
    role = await _get_role_or_404(role_id, get_active_org_id(current_user), session)
    if role.is_system_role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="System roles cannot be deleted")
    await session.delete(role)
    await session.commit()
    return MessageResponse(message=f"Role '{role.name}' deleted successfully")


# ---------------------------------------------------------------------------
# Role Assignment
# ---------------------------------------------------------------------------

class BulkUserIds(BaseModel):
    user_ids: List[uuid.UUID]


@router.post("/{role_id}/assign", response_model=MessageResponse, status_code=status.HTTP_201_CREATED, summary="Bulk assign a role to users")
async def assign_role_to_users(
    role_id: uuid.UUID,
    body: BulkUserIds,
    current_user=Depends(require_org_admin),
    session: AsyncSession = Depends(get_session),
):
    """Assign this role to one or more users at once."""
    role = await _get_role_or_404(role_id, get_active_org_id(current_user), session)
    assigned = []
    for uid in body.user_ids:
        user_result = await session.execute(
            select(User).where(User.id == uid, User.org_id == get_active_org_id(current_user)).options(selectinload(User.roles))
        )
        user = user_result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User {uid} not found")
        if not any(r.id == role_id for r in user.roles):
            user.roles.append(role)
            assigned.append(str(uid))
    await session.commit()
    return MessageResponse(message=f"Role '{role.name}' assigned to {len(assigned)} user(s)")


@router.delete("/{role_id}/assign/{user_id}", response_model=MessageResponse, summary="Remove a role from a user")
async def remove_role_from_user(
    role_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user=Depends(require_org_admin),
    session: AsyncSession = Depends(get_session),
):
    user_result = await session.execute(
        select(User)
        .where(User.id == user_id, User.org_id == get_active_org_id(current_user))
        .options(selectinload(User.roles))
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    role = next((r for r in user.roles if r.id == role_id), None)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User does not have this role")

    user.roles.remove(role)
    await session.commit()
    return MessageResponse(message=f"Role removed from user '{user.name}'")


# ---------------------------------------------------------------------------
# Teams by Role
# ---------------------------------------------------------------------------

@router.get("/{role_id}/teams", response_model=List[TeamResponse], summary="List teams that have this role assigned")
async def list_role_teams(
    role_id: uuid.UUID,
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    """Return all teams in the active org that have been assigned this role."""
    await _get_role_or_404(role_id, get_active_org_id(current_user), session)
    rows = await session.execute(
        select(team_roles).where(team_roles.c.role_id == role_id)
    )
    team_ids = [r["team_id"] for r in rows.mappings()]
    if not team_ids:
        return []
    result = await session.execute(
        select(Team).where(Team.id.in_(team_ids), Team.org_id == get_active_org_id(current_user))
    )
    return result.scalars().all()


# ---------------------------------------------------------------------------
# Users by Role
# ---------------------------------------------------------------------------

@router.get("/{role_id}/users", response_model=List[UserResponse], summary="List users with this role")
async def list_role_users(
    role_id: uuid.UUID,
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    """List all users in the active org who have been assigned this role."""
    await _get_role_or_404(role_id, get_active_org_id(current_user), session)
    result = await session.execute(
        select(User)
        .where(User.org_id == get_active_org_id(current_user))
        .options(selectinload(User.roles))
    )
    users = result.scalars().all()
    return [u for u in users if any(r.id == role_id for r in u.roles)]


# ---------------------------------------------------------------------------
# Role ↔ Policy (list / add / remove)
# ---------------------------------------------------------------------------

class BulkPolicyIds(BaseModel):
    policy_ids: List[uuid.UUID]


@router.get("/{role_id}/policies", response_model=List[PolicyResponse], summary="List policies assigned to a role")
async def list_role_policies(
    role_id: uuid.UUID,
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    """Return all policies currently assigned to the given role."""
    role = await _get_role_or_404(role_id, get_active_org_id(current_user), session, load_policies=True)
    return role.policies


@router.post("/{role_id}/policies", response_model=MessageResponse, status_code=status.HTTP_201_CREATED, summary="Bulk assign policies to a role")
async def add_policies_to_role(
    role_id: uuid.UUID,
    body: BulkPolicyIds,
    current_user=Depends(require_org_admin),
    session: AsyncSession = Depends(get_session),
):
    """Assign one or more policies to this role at once."""
    active_org = get_active_org_id(current_user)
    role = await _get_role_or_404(role_id, active_org, session, load_policies=True)
    if role.is_system_role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="System roles cannot be modified")
    policies = await _load_policies(body.policy_ids, active_org, session)
    added = 0
    for policy in policies:
        if not any(p.id == policy.id for p in role.policies):
            role.policies.append(policy)
            added += 1
    role.updated_at = datetime.now(timezone.utc)
    await session.commit()
    return MessageResponse(message=f"{added} policy(ies) added to role '{role.name}'")


@router.delete("/{role_id}/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove a policy from a role")
async def remove_policy_from_role(
    role_id: uuid.UUID,
    policy_id: uuid.UUID,
    current_user=Depends(require_org_admin),
    session: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(current_user)
    role = await _get_role_or_404(role_id, active_org, session, load_policies=True)
    if role.is_system_role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="System roles cannot be modified")
    policy = next((p for p in role.policies if p.id == policy_id), None)
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not assigned to this role")
    role.policies.remove(policy)
    role.updated_at = datetime.now(timezone.utc)
    await session.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_role_or_404(
    role_id: uuid.UUID,
    org_id: uuid.UUID,
    session: AsyncSession,
    load_policies: bool = False,
) -> Role:
    q = select(Role).where(Role.id == role_id, Role.org_id == org_id)
    if load_policies:
        q = q.options(selectinload(Role.policies))
    result = await session.execute(q)
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    return role


async def _load_policies(policy_ids: List[uuid.UUID], org_id: uuid.UUID, session: AsyncSession) -> List[Policy]:
    result = await session.execute(
        select(Policy).where(Policy.id.in_(policy_ids), Policy.org_id == org_id)
    )
    policies = result.scalars().all()
    if len(policies) != len(policy_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more policy IDs not found in this organization",
        )
    return list(policies)
