"""
Teams API router — CRUD, optional hierarchy display, and member management.

Key design decision:
- parent_team_id is OPTIONAL — hierarchy is not enforced.
- team_type (business_unit / division / department / group) is informational.
- The GET /{id}/hierarchy endpoint walks the children tree recursively for display only.
- Access inheritance based on hierarchy is a FUTURE phase.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.db import get_session
from app.auth.models import Team, User, Role, Policy, user_teams
from app.govern.models import team_roles, team_policies
from app.auth.schemas import (
    MessageResponse,
    TeamCreate,
    TeamResponse,
    TeamSummary,
    TeamUpdate,
    UserResponse,
)
from app.auth.dependencies import (
    get_active_org_id,
    require_active_user,
    require_org_admin,
    validate_org_membership,
)

router = APIRouter(prefix="/teams", tags=["Teams"])


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.get("", response_model=List[TeamResponse], summary="List teams (filterable by type / parent / domain / member)")
async def list_teams(
    org_id: Optional[uuid.UUID] = Query(None, description="Filter by org. Defaults to caller's active org."),
    team_type: Optional[str] = Query(None, description="Filter by team_type: business_unit | division | department | group"),
    parent_team_id: Optional[uuid.UUID] = Query(None, description="Filter by parent team ID."),
    root_only: bool = Query(False, description="Return only top-level teams (no parent)."),
    domain_id: Optional[uuid.UUID] = Query(None, description="Filter teams belonging to a subject area."),
    public_team_view: Optional[bool] = Query(None, description="Filter by public visibility flag."),
    search: Optional[str] = Query(None, description="Search by team name or display_name."),
    is_active: Optional[bool] = Query(None),
    # Relational filters
    member_user_id: Optional[uuid.UUID] = Query(None, description="Filter teams that a specific user belongs to."),
    role_id: Optional[uuid.UUID] = Query(None, description="Filter teams that have a specific role assigned."),
    policy_id: Optional[uuid.UUID] = Query(None, description="Filter teams that have a specific policy assigned."),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    effective_org = org_id or get_active_org_id(current_user)
    q = select(Team).where(Team.org_id == effective_org).distinct()
    if team_type:
        q = q.where(Team.team_type == team_type)
    if parent_team_id:
        q = q.where(Team.parent_team_id == parent_team_id)
    if root_only:
        q = q.where(Team.parent_team_id.is_(None))
    if domain_id:
        q = q.where(Team.domain_id == domain_id)
    if public_team_view is not None:
        q = q.where(Team.public_team_view == public_team_view)
    if search:
        q = q.where(Team.name.ilike(f"%{search}%") | Team.display_name.ilike(f"%{search}%"))
    if is_active is not None:
        q = q.where(Team.is_active == is_active)
    # Relational JOIN filters
    if member_user_id is not None:
        q = q.join(user_teams, user_teams.c.team_id == Team.id).where(user_teams.c.user_id == member_user_id)
    if role_id is not None:
        q = q.join(team_roles, team_roles.c.team_id == Team.id).where(team_roles.c.role_id == role_id)
    if policy_id is not None:
        q = q.join(team_policies, team_policies.c.team_id == Team.id).where(team_policies.c.policy_id == policy_id)
    q = q.order_by(Team.name).offset(skip).limit(limit)
    result = await session.execute(q)
    return result.scalars().all()


@router.post("", response_model=TeamResponse, status_code=status.HTTP_201_CREATED, summary="Create a team")
async def create_team(
    body: TeamCreate,
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    # Validate caller is at least a member of (and ideally admin of) the target org
    await validate_org_membership(current_user, body.org_id, session, require_admin=True)

    existing = await session.execute(
        select(Team).where(Team.org_id == body.org_id, Team.name == body.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Team name already exists in this organization")

    if body.parent_team_id:
        parent = await session.execute(
            select(Team).where(Team.id == body.parent_team_id, Team.org_id == body.org_id)
        )
        if not parent.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent team not found")

    team = Team(
        id=uuid.uuid4(),
        org_id=body.org_id,
        parent_team_id=body.parent_team_id,
        domain_id=body.domain_id,
        name=body.name,
        display_name=body.display_name,
        email=body.email,
        team_type=body.team_type,
        description=body.description,
        public_team_view=body.public_team_view,
        is_active=True,
    )
    session.add(team)
    await session.commit()
    await session.refresh(team)
    return team


@router.get("/{team_id}", response_model=TeamResponse, summary="Get a team by ID")
async def get_team(
    team_id: uuid.UUID,
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    return await _get_team_or_404(team_id, get_active_org_id(current_user), session)


@router.put("/{team_id}", response_model=TeamResponse, summary="Update a team")
async def update_team(
    team_id: uuid.UUID,
    body: TeamUpdate,
    current_user=Depends(require_org_admin),
    session: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(current_user)
    team = await _get_team_or_404(team_id, active_org, session)

    if body.name is not None and body.name != team.name:
        existing = await session.execute(
            select(Team).where(Team.org_id == active_org, Team.name == body.name)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Team name already exists")
        team.name = body.name

    if body.display_name is not None:
        team.display_name = body.display_name
    if body.email is not None:
        team.email = body.email
    if body.team_type is not None:
        team.team_type = body.team_type
    if body.description is not None:
        team.description = body.description
    if body.domain_id is not None:
        team.domain_id = body.domain_id
    if body.public_team_view is not None:
        team.public_team_view = body.public_team_view
    if body.parent_team_id is not None:
        if body.parent_team_id == team_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A team cannot be its own parent")
        parent = await session.execute(
            select(Team).where(Team.id == body.parent_team_id, Team.org_id == active_org)
        )
        if not parent.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent team not found")
        team.parent_team_id = body.parent_team_id

    team.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(team)
    return team


@router.delete("/{team_id}", response_model=MessageResponse, summary="Delete a team")
async def delete_team(
    team_id: uuid.UUID,
    current_user=Depends(require_org_admin),
    session: AsyncSession = Depends(get_session),
):
    team = await _get_team_or_404(team_id, get_active_org_id(current_user), session)
    await session.delete(team)
    await session.commit()
    return MessageResponse(message=f"Team '{team.name}' deleted successfully")


# ---------------------------------------------------------------------------
# Hierarchy sub-tree
# ---------------------------------------------------------------------------

@router.get("/{team_id}/hierarchy", summary="Get full hierarchy sub-tree rooted at this team")
async def get_team_hierarchy(
    team_id: uuid.UUID,
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """
    Returns the team and all its descendants as a nested tree.
    Hierarchy is informational only — access inheritance is a future phase.
    """
    active_org = get_active_org_id(current_user)
    root = await _get_team_or_404(team_id, active_org, session)

    # Load all teams for this org (one query, build tree in Python)
    result = await session.execute(
        select(Team).where(Team.org_id == active_org, Team.is_active == True)
    )
    all_teams = result.scalars().all()
    return _build_tree(root.id, all_teams)


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------

@router.get("/{team_id}/members", response_model=List[UserResponse], summary="List team members")
async def list_members(
    team_id: uuid.UUID,
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    team = await session.execute(
        select(Team)
        .where(Team.id == team_id, Team.org_id == get_active_org_id(current_user))
        .options(selectinload(Team.members).selectinload(User.teams), selectinload(Team.members).selectinload(User.roles))
    )
    team = team.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return team.members


@router.post("/{team_id}/members/{user_id}", response_model=MessageResponse, summary="Add a user to a team")
async def add_member(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user=Depends(require_org_admin),
    session: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(current_user)
    team = await _get_team_or_404(team_id, active_org, session)
    user_result = await session.execute(
        select(User).where(User.id == user_id, User.org_id == active_org)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Reload team with members to check duplicates
    team_with_members = await session.execute(
        select(Team).where(Team.id == team_id).options(selectinload(Team.members))
    )
    team_obj = team_with_members.scalar_one()
    if any(m.id == user_id for m in team_obj.members):
        return MessageResponse(message="User is already a member of this team")

    team_obj.members.append(user)
    await session.commit()
    return MessageResponse(message=f"User '{user.name}' added to team '{team.name}'")


@router.delete("/{team_id}/members/{user_id}", response_model=MessageResponse, summary="Remove a user from a team")
async def remove_member(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user=Depends(require_org_admin),
    session: AsyncSession = Depends(get_session),
):
    team_with_members = await session.execute(
        select(Team)
        .where(Team.id == team_id, Team.org_id == get_active_org_id(current_user))
        .options(selectinload(Team.members))
    )
    team = team_with_members.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    member = next((m for m in team.members if m.id == user_id), None)
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User is not a member of this team")

    team.members.remove(member)
    await session.commit()
    return MessageResponse(message=f"User removed from team '{team.name}'")


# ---------------------------------------------------------------------------
# Team Stats + Roles/Policies Management
# ---------------------------------------------------------------------------

@router.get("/{team_id}/stats")
async def get_team_stats(
    team_id: uuid.UUID,
    current_user: User = Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    team = await _get_team_or_404(team_id, get_active_org_id(current_user), session)
    member_count = (await session.execute(
        select(func.count()).select_from(user_teams).where(user_teams.c.team_id == team_id)
    )).scalar_one()
    sub_team_count = (await session.execute(
        select(func.count()).select_from(Team).where(Team.parent_team_id == team_id, Team.is_active == True)
    )).scalar_one()
    return {
        "team_id": str(team_id),
        "name": team.name,
        "team_type": team.team_type,
        "members": member_count,
        "sub_teams": sub_team_count,
    }


@router.get("/{team_id}/roles")
async def list_team_roles(
    team_id: uuid.UUID,
    current_user: User = Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    await _get_team_or_404(team_id, get_active_org_id(current_user), session)
    rows = await session.execute(select(team_roles).where(team_roles.c.team_id == team_id))
    role_ids = [r["role_id"] for r in rows.mappings()]
    if not role_ids:
        return []
    result = await session.execute(select(Role).where(Role.id.in_(role_ids)))
    roles = result.scalars().all()
    return [{"id": str(r.id), "name": r.name, "description": r.description} for r in roles]


@router.post("/{team_id}/roles/{role_id}", status_code=status.HTTP_201_CREATED)
async def assign_role_to_team(
    team_id: uuid.UUID,
    role_id: uuid.UUID,
    current_user: User = Depends(require_org_admin),
    session: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(current_user)
    await _get_team_or_404(team_id, active_org, session)
    role = (await session.execute(select(Role).where(Role.id == role_id, Role.org_id == active_org))).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found in this organization")
    await session.execute(
        pg_insert(team_roles).values(team_id=team_id, role_id=role_id).on_conflict_do_nothing()
    )
    await session.commit()
    return {"message": "Role assigned to team"}


@router.delete("/{team_id}/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_role_from_team(
    team_id: uuid.UUID,
    role_id: uuid.UUID,
    current_user: User = Depends(require_org_admin),
    session: AsyncSession = Depends(get_session),
):
    await session.execute(
        team_roles.delete().where(team_roles.c.team_id == team_id, team_roles.c.role_id == role_id)
    )
    await session.commit()


@router.get("/{team_id}/policies")
async def list_team_policies(
    team_id: uuid.UUID,
    current_user: User = Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    await _get_team_or_404(team_id, get_active_org_id(current_user), session)
    rows = await session.execute(select(team_policies).where(team_policies.c.team_id == team_id))
    policy_ids = [r["policy_id"] for r in rows.mappings()]
    if not policy_ids:
        return []
    result = await session.execute(select(Policy).where(Policy.id.in_(policy_ids)))
    policies = result.scalars().all()
    return [{"id": str(p.id), "name": p.name, "resource": p.resource, "operations": p.operations} for p in policies]


@router.post("/{team_id}/policies/{policy_id}", status_code=status.HTTP_201_CREATED)
async def assign_policy_to_team(
    team_id: uuid.UUID,
    policy_id: uuid.UUID,
    current_user: User = Depends(require_org_admin),
    session: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(current_user)
    await _get_team_or_404(team_id, active_org, session)
    policy = (await session.execute(select(Policy).where(Policy.id == policy_id, Policy.org_id == active_org))).scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found in this organization")
    await session.execute(
        pg_insert(team_policies).values(team_id=team_id, policy_id=policy_id).on_conflict_do_nothing()
    )
    await session.commit()
    return {"message": "Policy assigned to team"}


@router.delete("/{team_id}/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_policy_from_team(
    team_id: uuid.UUID,
    policy_id: uuid.UUID,
    current_user: User = Depends(require_org_admin),
    session: AsyncSession = Depends(get_session),
):
    await session.execute(
        team_policies.delete().where(team_policies.c.team_id == team_id, team_policies.c.policy_id == policy_id)
    )
    await session.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_team_or_404(team_id: uuid.UUID, org_id: uuid.UUID, session: AsyncSession) -> Team:
    result = await session.execute(
        select(Team).where(Team.id == team_id, Team.org_id == org_id)
    )
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return team


def _build_tree(root_id: uuid.UUID, all_teams: List[Team]) -> Dict[str, Any]:
    team_map: Dict[uuid.UUID, Dict] = {}
    for t in all_teams:
        team_map[t.id] = {
            "id": str(t.id),
            "name": t.name,
            "display_name": t.display_name,
            "team_type": str(t.team_type),
            "parent_team_id": str(t.parent_team_id) if t.parent_team_id else None,
            "children": [],
        }

    root = team_map.get(root_id)
    if not root:
        return {}

    for t in all_teams:
        if t.parent_team_id and t.parent_team_id in team_map and t.id != root_id:
            team_map[t.parent_team_id]["children"].append(team_map[t.id])

    return root
