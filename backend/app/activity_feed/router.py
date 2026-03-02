"""Activity Feed — read-only API to get activity entries."""
from __future__ import annotations
import uuid
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.auth.dependencies import require_active_user
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
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[uuid.UUID] = Query(None),
    actor_id: Optional[uuid.UUID] = Query(None),
    skip: int = 0,
    limit: int = 50,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    stmt = select(ActivityFeed).where(ActivityFeed.org_id == user.org_id)
    if entity_type:
        stmt = stmt.where(ActivityFeed.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(ActivityFeed.entity_id == entity_id)
    if actor_id:
        stmt = stmt.where(ActivityFeed.actor_id == actor_id)
    stmt = stmt.order_by(ActivityFeed.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()
