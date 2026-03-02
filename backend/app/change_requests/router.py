"""Change Requests — request description/field updates on any entity, used by Glossary Tasks."""
from __future__ import annotations
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from app.db import get_session
from app.auth.dependencies import get_active_org_id, require_active_user, require_org_admin
from app.auth.models import User
from app.govern.models import ChangeRequest, change_request_assignees
from app.govern.activity import emit

router = APIRouter(prefix="/change-requests", tags=["Change Requests"])

VALID_STATUSES = {"open", "in_review", "approved", "rejected", "withdrawn"}
VALID_ENTITY_TYPES = {
    "glossary_term", "catalog_domain", "data_product",
    "classification", "classification_tag", "govern_metric",
    "dataset", "schema", "table", "column",
}


# ── Schemas ──────────────────────────────────────────────────────────────────

class UserRef(BaseModel):
    id: uuid.UUID
    name: Optional[str] = None

    class Config:
        from_attributes = True


class ChangeRequestCreate(BaseModel):
    entity_type: str
    entity_id: uuid.UUID
    field_name: str
    current_value: Optional[str] = None
    new_value: str
    title: Optional[str] = None
    description: Optional[str] = None
    assignee_ids: List[uuid.UUID] = []


class ChangeRequestUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    new_value: Optional[str] = None
    assignee_ids: Optional[List[uuid.UUID]] = None


class ChangeRequestOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    field_name: str
    current_value: Optional[str]
    new_value: str
    title: Optional[str]
    description: Optional[str]
    status: str
    requested_by: Optional[uuid.UUID]
    resolved_by: Optional[uuid.UUID]
    resolved_at: Optional[datetime]
    assignees: List[UserRef] = []

    class Config:
        from_attributes = True


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _sync_assignees(db, cr_id, ids):
    await db.execute(change_request_assignees.delete().where(
        change_request_assignees.c.change_request_id == cr_id
    ))
    for uid in ids:
        await db.execute(change_request_assignees.insert().values(
            change_request_id=cr_id, user_id=uid
        ))


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_model=List[ChangeRequestOut])
async def list_change_requests(
    entity_type: Optional[str] = Query(None, description="Filter by entity type."),
    entity_id: Optional[uuid.UUID] = Query(None, description="Filter by entity ID."),
    cr_status: Optional[str] = Query(None, alias="status", description="Filter by status (open/in_review/approved/rejected/withdrawn)."),
    requested_by: Optional[uuid.UUID] = Query(None, description="Filter by requester user ID."),
    resolved_by: Optional[uuid.UUID] = Query(None, description="Filter by resolver user ID."),
    field_name: Optional[str] = Query(None, description="Filter by field name that was changed."),
    # Relational filters
    assignee_id: Optional[uuid.UUID] = Query(None, description="Filter change requests assigned to this user (M2M)."),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    stmt = select(ChangeRequest).where(ChangeRequest.org_id == get_active_org_id(user)).distinct()
    if entity_type:
        stmt = stmt.where(ChangeRequest.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(ChangeRequest.entity_id == entity_id)
    if cr_status:
        stmt = stmt.where(ChangeRequest.status == cr_status)
    if requested_by:
        stmt = stmt.where(ChangeRequest.requested_by == requested_by)
    if resolved_by:
        stmt = stmt.where(ChangeRequest.resolved_by == resolved_by)
    if field_name:
        stmt = stmt.where(ChangeRequest.field_name == field_name)
    # Relational JOIN filter
    if assignee_id is not None:
        stmt = stmt.join(change_request_assignees, change_request_assignees.c.change_request_id == ChangeRequest.id).where(change_request_assignees.c.user_id == assignee_id)
    stmt = stmt.order_by(ChangeRequest.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=ChangeRequestOut, status_code=status.HTTP_201_CREATED)
async def create_change_request(
    body: ChangeRequestCreate,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    if body.entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(status_code=422, detail=f"Invalid entity_type. Allowed: {sorted(VALID_ENTITY_TYPES)}")
    payload = body.model_dump(exclude={"assignee_ids"})
    obj = ChangeRequest(org_id=get_active_org_id(user), requested_by=user.id, **payload)
    db.add(obj)
    await db.flush([obj])
    if body.assignee_ids:
        await _sync_assignees(db, obj.id, body.assignee_ids)
    await emit(db, entity_type="change_request", action="created", entity_id=obj.id,
               org_id=get_active_org_id(user), actor_id=user.id,
               details={"entity_type": obj.entity_type, "entity_id": str(obj.entity_id), "field": obj.field_name})
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{cr_id}", response_model=ChangeRequestOut)
async def get_change_request(
    cr_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(ChangeRequest, cr_id)
    if not obj or obj.org_id != get_active_org_id(user):
        raise HTTPException(status_code=404, detail="Change request not found")
    return obj


@router.put("/{cr_id}", response_model=ChangeRequestOut)
async def update_change_request(
    cr_id: uuid.UUID,
    body: ChangeRequestUpdate,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(ChangeRequest, cr_id)
    if not obj or obj.org_id != get_active_org_id(user):
        raise HTTPException(status_code=404, detail="Change request not found")
    if obj.status not in ("open", "in_review"):
        raise HTTPException(status_code=400, detail="Cannot update a resolved change request")
    data = body.model_dump(exclude_unset=True)
    assignee_ids = data.pop("assignee_ids", None)
    for k, v in data.items():
        setattr(obj, k, v)
    if assignee_ids is not None:
        await _sync_assignees(db, obj.id, assignee_ids)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.post("/{cr_id}/approve", response_model=ChangeRequestOut)
async def approve_change_request(
    cr_id: uuid.UUID,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(ChangeRequest, cr_id)
    if not obj or obj.org_id != get_active_org_id(user):
        raise HTTPException(status_code=404, detail="Change request not found")
    if obj.status not in ("open", "in_review"):
        raise HTTPException(status_code=400, detail="Already resolved")
    obj.status = "approved"
    obj.resolved_by = user.id
    obj.resolved_at = datetime.now(timezone.utc)
    await emit(db, entity_type="change_request", action="approved", entity_id=obj.id,
               org_id=get_active_org_id(user), actor_id=user.id)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.post("/{cr_id}/reject", response_model=ChangeRequestOut)
async def reject_change_request(
    cr_id: uuid.UUID,
    user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(ChangeRequest, cr_id)
    if not obj or obj.org_id != get_active_org_id(user):
        raise HTTPException(status_code=404, detail="Change request not found")
    if obj.status not in ("open", "in_review"):
        raise HTTPException(status_code=400, detail="Already resolved")
    obj.status = "rejected"
    obj.resolved_by = user.id
    obj.resolved_at = datetime.now(timezone.utc)
    await emit(db, entity_type="change_request", action="rejected", entity_id=obj.id,
               org_id=get_active_org_id(user), actor_id=user.id)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.post("/{cr_id}/withdraw", response_model=ChangeRequestOut)
async def withdraw_change_request(
    cr_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(ChangeRequest, cr_id)
    if not obj or obj.org_id != get_active_org_id(user):
        raise HTTPException(status_code=404, detail="Change request not found")
    if obj.requested_by != user.id and not getattr(user, "_is_org_admin", False) and not user.is_admin:
        raise HTTPException(status_code=403, detail="Only the requester or admin can withdraw")
    if obj.status not in ("open", "in_review"):
        raise HTTPException(status_code=400, detail="Already resolved")
    obj.status = "withdrawn"
    obj.resolved_by = user.id
    obj.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{cr_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_change_request(
    cr_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(ChangeRequest, cr_id)
    if not obj or obj.org_id != get_active_org_id(user):
        raise HTTPException(status_code=404, detail="Change request not found")
    await db.delete(obj)
    await db.commit()
