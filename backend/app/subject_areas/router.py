"""Subject Areas (formerly Domains) — CRUD API."""
from __future__ import annotations
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.auth.dependencies import require_active_user
from app.auth.models import User, Domain as SubjectArea

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

    class Config:
        from_attributes = True


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_model=List[SubjectAreaOut])
async def list_subject_areas(
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(True),
    skip: int = 0,
    limit: int = 50,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    stmt = select(SubjectArea).where(SubjectArea.org_id == user.org_id)
    if is_active is not None:
        stmt = stmt.where(SubjectArea.is_active == is_active)
    if search:
        stmt = stmt.where(SubjectArea.name.ilike(f"%{search}%"))
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=SubjectAreaOut, status_code=status.HTTP_201_CREATED)
async def create_subject_area(
    body: SubjectAreaCreate,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    obj = SubjectArea(org_id=user.org_id, **body.model_dump())
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
    if not obj or obj.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Subject area not found")
    return obj


@router.put("/{subject_area_id}", response_model=SubjectAreaOut)
async def update_subject_area(
    subject_area_id: uuid.UUID,
    body: SubjectAreaUpdate,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(SubjectArea, subject_area_id)
    if not obj or obj.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Subject area not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{subject_area_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subject_area(
    subject_area_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(SubjectArea, subject_area_id)
    if not obj or obj.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Subject area not found")
    await db.delete(obj)
    await db.commit()
