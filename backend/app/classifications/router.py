"""Classifications & Tags — CRUD API including PersonalData."""
from __future__ import annotations
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.auth.dependencies import require_active_user
from app.auth.models import User
from app.govern.models import (
    Classification, ClassificationTag,
    classification_owners, classification_domain_refs,
    classification_tag_owners, classification_tag_domain_refs,
)
from app.govern.activity import emit

router = APIRouter(prefix="/classifications", tags=["Classifications"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class UserRef(BaseModel):
    id: uuid.UUID
    name: Optional[str] = None

    class Config:
        from_attributes = True


class DomainRef(BaseModel):
    id: uuid.UUID
    name: Optional[str] = None

    class Config:
        from_attributes = True


class ClassificationCreate(BaseModel):
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    mutually_exclusive: bool = False
    owner_ids: List[uuid.UUID] = []
    domain_ids: List[uuid.UUID] = []


class ClassificationUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    mutually_exclusive: Optional[bool] = None
    owner_ids: Optional[List[uuid.UUID]] = None
    domain_ids: Optional[List[uuid.UUID]] = None
    is_active: Optional[bool] = None


class ClassificationOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    display_name: Optional[str]
    description: Optional[str]
    mutually_exclusive: bool
    is_active: bool
    owners: List[UserRef] = []
    domains: List[DomainRef] = []

    class Config:
        from_attributes = True


class TagCreate(BaseModel):
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    icon_url: Optional[str] = None
    color: Optional[str] = None
    owner_ids: List[uuid.UUID] = []
    domain_ids: List[uuid.UUID] = []


class TagUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    icon_url: Optional[str] = None
    color: Optional[str] = None
    owner_ids: Optional[List[uuid.UUID]] = None
    domain_ids: Optional[List[uuid.UUID]] = None
    is_active: Optional[bool] = None


class TagOut(BaseModel):
    id: uuid.UUID
    classification_id: uuid.UUID
    org_id: uuid.UUID
    name: str
    display_name: Optional[str]
    description: Optional[str]
    icon_url: Optional[str]
    color: Optional[str]
    is_active: bool
    owners: List[UserRef] = []
    domains: List[DomainRef] = []

    class Config:
        from_attributes = True


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _sync_m2m(db, table, col_a, val_a, col_b, ids):
    await db.execute(table.delete().where(table.c[col_a] == val_a))
    for id_ in ids:
        await db.execute(table.insert().values({col_a: val_a, col_b: id_}))


# ── Classification CRUD ───────────────────────────────────────────────────────

@router.get("", response_model=List[ClassificationOut])
async def list_classifications(
    search: Optional[str] = Query(None),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    stmt = select(Classification).where(Classification.org_id == user.org_id)
    if search:
        stmt = stmt.where(Classification.name.ilike(f"%{search}%"))
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=ClassificationOut, status_code=status.HTTP_201_CREATED)
async def create_classification(
    body: ClassificationCreate,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    payload = body.model_dump(exclude={"owner_ids", "domain_ids"})
    obj = Classification(org_id=user.org_id, created_by=user.id, **payload)
    db.add(obj)
    await db.flush([obj])
    if body.owner_ids:
        await _sync_m2m(db, classification_owners, "classification_id", obj.id, "user_id", body.owner_ids)
    if body.domain_ids:
        await _sync_m2m(db, classification_domain_refs, "classification_id", obj.id, "domain_id", body.domain_ids)
    await emit(db, entity_type="classification", action="created", entity_id=obj.id,
               org_id=user.org_id, actor_id=user.id, details={"name": obj.name})
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{classification_id}", response_model=ClassificationOut)
async def get_classification(
    classification_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(Classification, classification_id)
    if not obj or obj.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Classification not found")
    return obj


@router.put("/{classification_id}", response_model=ClassificationOut)
async def update_classification(
    classification_id: uuid.UUID,
    body: ClassificationUpdate,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(Classification, classification_id)
    if not obj or obj.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Classification not found")
    data = body.model_dump(exclude_unset=True)
    owner_ids = data.pop("owner_ids", None)
    domain_ids = data.pop("domain_ids", None)
    for k, v in data.items():
        setattr(obj, k, v)
    if owner_ids is not None:
        await _sync_m2m(db, classification_owners, "classification_id", obj.id, "user_id", owner_ids)
    if domain_ids is not None:
        await _sync_m2m(db, classification_domain_refs, "classification_id", obj.id, "domain_id", domain_ids)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{classification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_classification(
    classification_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(Classification, classification_id)
    if not obj or obj.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Classification not found")
    await db.delete(obj)
    await db.commit()


# ── Tag CRUD ──────────────────────────────────────────────────────────────────

@router.get("/{classification_id}/tags", response_model=List[TagOut])
async def list_tags(
    classification_id: uuid.UUID,
    search: Optional[str] = Query(None),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    stmt = select(ClassificationTag).where(
        ClassificationTag.classification_id == classification_id,
        ClassificationTag.org_id == user.org_id,
    )
    if search:
        stmt = stmt.where(ClassificationTag.name.ilike(f"%{search}%"))
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/{classification_id}/tags", response_model=TagOut, status_code=status.HTTP_201_CREATED)
async def create_tag(
    classification_id: uuid.UUID,
    body: TagCreate,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    cls = await db.get(Classification, classification_id)
    if not cls or cls.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Classification not found")
    payload = body.model_dump(exclude={"owner_ids", "domain_ids"})
    tag = ClassificationTag(
        classification_id=classification_id, org_id=user.org_id, created_by=user.id, **payload
    )
    db.add(tag)
    await db.flush([tag])
    if body.owner_ids:
        await _sync_m2m(db, classification_tag_owners, "tag_id", tag.id, "user_id", body.owner_ids)
    if body.domain_ids:
        await _sync_m2m(db, classification_tag_domain_refs, "tag_id", tag.id, "domain_id", body.domain_ids)
    await emit(db, entity_type="classification_tag", action="created", entity_id=tag.id,
               org_id=user.org_id, actor_id=user.id, details={"name": tag.name})
    await db.commit()
    await db.refresh(tag)
    return tag


@router.get("/{classification_id}/tags/{tag_id}", response_model=TagOut)
async def get_tag(
    classification_id: uuid.UUID,
    tag_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    tag = await db.get(ClassificationTag, tag_id)
    if not tag or tag.org_id != user.org_id or tag.classification_id != classification_id:
        raise HTTPException(status_code=404, detail="Tag not found")
    return tag


@router.put("/{classification_id}/tags/{tag_id}", response_model=TagOut)
async def update_tag(
    classification_id: uuid.UUID,
    tag_id: uuid.UUID,
    body: TagUpdate,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    tag = await db.get(ClassificationTag, tag_id)
    if not tag or tag.org_id != user.org_id or tag.classification_id != classification_id:
        raise HTTPException(status_code=404, detail="Tag not found")
    data = body.model_dump(exclude_unset=True)
    owner_ids = data.pop("owner_ids", None)
    domain_ids = data.pop("domain_ids", None)
    for k, v in data.items():
        setattr(tag, k, v)
    if owner_ids is not None:
        await _sync_m2m(db, classification_tag_owners, "tag_id", tag.id, "user_id", owner_ids)
    if domain_ids is not None:
        await _sync_m2m(db, classification_tag_domain_refs, "tag_id", tag.id, "domain_id", domain_ids)
    await db.commit()
    await db.refresh(tag)
    return tag


@router.delete("/{classification_id}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    classification_id: uuid.UUID,
    tag_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    tag = await db.get(ClassificationTag, tag_id)
    if not tag or tag.org_id != user.org_id or tag.classification_id != classification_id:
        raise HTTPException(status_code=404, detail="Tag not found")
    await db.delete(tag)
    await db.commit()
