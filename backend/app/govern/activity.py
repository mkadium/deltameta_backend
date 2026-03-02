"""Utility to emit activity feed entries from any router."""
from __future__ import annotations
from typing import Any, Dict, Optional
import uuid as _uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.govern.models import ActivityFeed


async def emit(
    db: AsyncSession,
    *,
    entity_type: str,
    action: str,
    entity_id: Optional[_uuid.UUID] = None,
    org_id: Optional[_uuid.UUID] = None,
    actor_id: Optional[_uuid.UUID] = None,
    details: Dict[str, Any] | None = None,
) -> None:
    feed = ActivityFeed(
        org_id=org_id,
        actor_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        details=details or {},
    )
    db.add(feed)
    # Flush but do not commit — the calling router owns the transaction.
    await db.flush([feed])
