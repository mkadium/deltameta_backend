"""Activity Feed — read-only API to get activity entries."""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.auth.dependencies import get_active_org_id, require_active_user
from app.auth.models import User
from app.govern.models import ActivityFeed

router = APIRouter(prefix="/activity-feed", tags=["Activity Feed"])


class ActivityFeedOut(BaseModel):
    id: uuid.UUID
    org_id: Optional[uuid.UUID]
    actor_id: Optional[uuid.UUID]
    entity_type: str
    entity_id: Optional[uuid.UUID]
    action: str
    details: dict
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("", response_model=List[ActivityFeedOut])
async def list_activity(
    entity_type: Optional[str] = Query(None, description="Filter by entity type."),
    entity_id: Optional[uuid.UUID] = Query(None, description="Filter by entity ID."),
    actor_id: Optional[uuid.UUID] = Query(None, description="Filter by actor (user who performed the action)."),
    action: Optional[str] = Query(None, description="Filter by action (created/updated/deleted/approved/etc.)."),
    created_after: Optional[datetime] = Query(None, description="Filter activities after this timestamp (ISO 8601)."),
    created_before: Optional[datetime] = Query(None, description="Filter activities before this timestamp (ISO 8601)."),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    stmt = select(ActivityFeed).where(ActivityFeed.org_id == get_active_org_id(user))
    if entity_type:
        stmt = stmt.where(ActivityFeed.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(ActivityFeed.entity_id == entity_id)
    if actor_id:
        stmt = stmt.where(ActivityFeed.actor_id == actor_id)
    if action:
        stmt = stmt.where(ActivityFeed.action == action)
    if created_after:
        stmt = stmt.where(ActivityFeed.created_at >= created_after)
    if created_before:
        stmt = stmt.where(ActivityFeed.created_at <= created_before)
    stmt = stmt.order_by(ActivityFeed.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()
