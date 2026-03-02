"""Subject Areas (formerly Domains) — CRUD API."""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.auth.dependencies import get_active_org_id, require_active_user, require_org_admin
from app.auth.models import User, Domain as SubjectArea, Team

router = APIRouter(prefix="/subject-areas", tags=["Subject Areas"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class SubjectAreaCreate(BaseModel):
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    domain_type: Optional[str] = None
    owner_id: Optional[uuid.UUID] = None


class SubjectAreaUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    domain_type: Optional[str] = None
    owner_id: Optional[uuid.UUID] = None
    is_active: Optional[bool] = None


class SubjectAreaOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    display_name: Optional[str]
    description: Optional[str]
    domain_type: Optional[str]
    owner_id: Optional[uuid.UUID]
    is_active: bool
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_model=List[SubjectAreaOut])
async def list_subject_areas(
    search: Optional[str] = Query(None, description="Search by name or display_name."),
    is_active: Optional[bool] = Query(True),
    domain_type: Optional[str] = Query(None, description="Filter by domain_type."),
    owner_id: Optional[uuid.UUID] = Query(None, description="Filter by owner user ID."),
    # Relational filter
    team_id: Optional[uuid.UUID] = Query(None, description="Filter subject areas that the given team belongs to (Team.domain_id)."),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    stmt = select(SubjectArea).where(SubjectArea.org_id == get_active_org_id(user)).distinct()
    if is_active is not None:
        stmt = stmt.where(SubjectArea.is_active == is_active)
    if search:
        stmt = stmt.where(SubjectArea.name.ilike(f"%{search}%") | SubjectArea.display_name.ilike(f"%{search}%"))
    if domain_type:
        stmt = stmt.where(SubjectArea.domain_type == domain_type)
    if owner_id:
        stmt = stmt.where(SubjectArea.owner_id == owner_id)
    # Relational JOIN filter: find subject areas where teams with this team_id exist
    if team_id is not None:
        stmt = stmt.join(Team, Team.domain_id == SubjectArea.id).where(Team.id == team_id)
    stmt = stmt.order_by(SubjectArea.name).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=SubjectAreaOut, status_code=status.HTTP_201_CREATED)
async def create_subject_area(
    body: SubjectAreaCreate,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    active_org = get_active_org_id(user)
    existing = await db.execute(
        select(SubjectArea).where(SubjectArea.org_id == active_org, SubjectArea.name == body.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Subject area name already exists in this organization")
    obj = SubjectArea(org_id=active_org, **body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{subject_area_id}", response_model=SubjectAreaOut)
async def get_subject_area(
    subject_area_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(SubjectArea, subject_area_id)
    if not obj or obj.org_id != get_active_org_id(user):
        raise HTTPException(status_code=404, detail="Subject area not found")
    return obj


@router.put("/{subject_area_id}", response_model=SubjectAreaOut)
async def update_subject_area(
    subject_area_id: uuid.UUID,
    body: SubjectAreaUpdate,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(SubjectArea, subject_area_id)
    if not obj or obj.org_id != get_active_org_id(user):
        raise HTTPException(status_code=404, detail="Subject area not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{subject_area_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subject_area(
    subject_area_id: uuid.UUID,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(SubjectArea, subject_area_id)
    if not obj or obj.org_id != get_active_org_id(user):
        raise HTTPException(status_code=404, detail="Subject area not found")
    await db.delete(obj)
    await db.commit()
