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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.auth.models import Team, User, user_teams
from app.auth.schemas import (
    MessageResponse,
    TeamCreate,
    TeamResponse,
    TeamSummary,
    TeamUpdate,
    UserResponse,
)
from app.auth.dependencies import require_active_user, require_org_admin

router = APIRouter(prefix="/teams", tags=["Teams"])


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.get("", response_model=List[TeamResponse], summary="List teams (filterable by type / parent)")
async def list_teams(
    team_type: Optional[str] = Query(None, description="Filter by team_type: business_unit | division | department | group"),
    parent_team_id: Optional[uuid.UUID] = Query(None, description="Filter by parent team ID. Pass null to get root teams."),
    root_only: bool = Query(False, description="Return only top-level teams (no parent)"),
    is_active: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    q = select(Team).where(Team.org_id == current_user.org_id)
    if team_type:
        q = q.where(Team.team_type == team_type)
    if parent_team_id:
        q = q.where(Team.parent_team_id == parent_team_id)
    if root_only:
        q = q.where(Team.parent_team_id.is_(None))
    if is_active is not None:
        q = q.where(Team.is_active == is_active)
    q = q.order_by(Team.name).offset(skip).limit(limit)
    result = await session.execute(q)
    return result.scalars().all()


@router.post("", response_model=TeamResponse, status_code=status.HTTP_201_CREATED, summary="Create a team")
async def create_team(
    body: TeamCreate,
    current_user=Depends(require_org_admin),
    session: AsyncSession = Depends(get_session),
):
    existing = await session.execute(
        select(Team).where(Team.org_id == current_user.org_id, Team.name == body.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Team name already exists in this organization")

    if body.parent_team_id:
        parent = await session.execute(
            select(Team).where(Team.id == body.parent_team_id, Team.org_id == current_user.org_id)
        )
        if not parent.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent team not found")

    team = Team(
        id=uuid.uuid4(),
        org_id=current_user.org_id,
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
    return await _get_team_or_404(team_id, current_user.org_id, session)


@router.put("/{team_id}", response_model=TeamResponse, summary="Update a team")
async def update_team(
    team_id: uuid.UUID,
    body: TeamUpdate,
    current_user=Depends(require_org_admin),
    session: AsyncSession = Depends(get_session),
):
    team = await _get_team_or_404(team_id, current_user.org_id, session)

    if body.name is not None and body.name != team.name:
        existing = await session.execute(
            select(Team).where(Team.org_id == current_user.org_id, Team.name == body.name)
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
            select(Team).where(Team.id == body.parent_team_id, Team.org_id == current_user.org_id)
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
    team = await _get_team_or_404(team_id, current_user.org_id, session)
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
    root = await _get_team_or_404(team_id, current_user.org_id, session)

    # Load all teams for this org (one query, build tree in Python)
    result = await session.execute(
        select(Team).where(Team.org_id == current_user.org_id, Team.is_active == True)
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
        .where(Team.id == team_id, Team.org_id == current_user.org_id)
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
    team = await _get_team_or_404(team_id, current_user.org_id, session)
    user_result = await session.execute(
        select(User).where(User.id == user_id, User.org_id == current_user.org_id)
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
        .where(Team.id == team_id, Team.org_id == current_user.org_id)
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
