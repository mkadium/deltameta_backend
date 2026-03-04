"""Bots API — manage automated scanner/agent configurations."""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.auth.dependencies import get_active_org_id, require_active_user, require_org_admin
from app.auth.abac import require_permission
from app.auth.models import User
from app.govern.models import Bot, BotRun
from app.govern.activity import emit

router = APIRouter(prefix="/bots", tags=["Bots"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class BotCreate(BaseModel):
    name: str
    description: Optional[str] = None
    bot_type: str  # metadata | profiler | lineage | usage | classification | search_index | test_suite | rdf_export | embedding
    mode: str = "self"  # self | external
    trigger_mode: str = "on_demand"  # on_demand | scheduled
    cron_expr: Optional[str] = None
    service_endpoint_id: Optional[uuid.UUID] = None
    model_name: Optional[str] = None


class BotUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    bot_type: Optional[str] = None
    mode: Optional[str] = None
    trigger_mode: Optional[str] = None
    cron_expr: Optional[str] = None
    service_endpoint_id: Optional[uuid.UUID] = None
    model_name: Optional[str] = None


class BotOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    description: Optional[str]
    bot_type: str
    mode: str
    is_enabled: bool
    trigger_mode: str
    cron_expr: Optional[str]
    service_endpoint_id: Optional[uuid.UUID]
    model_name: Optional[str]
    last_run_at: Optional[datetime]
    last_run_status: Optional[str]
    last_run_message: Optional[str]
    created_by: Optional[uuid.UUID]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BotRunOut(BaseModel):
    bot_id: uuid.UUID
    message: str
    triggered_at: datetime


class BotRunRecord(BaseModel):
    id: uuid.UUID
    bot_id: uuid.UUID
    org_id: uuid.UUID
    triggered_by: Optional[uuid.UUID]
    trigger_source: str
    status: str
    message: Optional[str]
    output: dict
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


VALID_BOT_TYPES = {
    "metadata", "profiler", "lineage", "usage",
    "classification", "search_index", "test_suite",
    "rdf_export", "embedding",
}
VALID_MODES = {"self", "external"}
VALID_TRIGGER_MODES = {"on_demand", "scheduled"}


def _validate_bot(body: BotCreate | BotUpdate) -> None:
    if hasattr(body, "bot_type") and body.bot_type and body.bot_type not in VALID_BOT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"bot_type must be one of: {', '.join(sorted(VALID_BOT_TYPES))}",
        )
    if hasattr(body, "mode") and body.mode and body.mode not in VALID_MODES:
        raise HTTPException(status_code=422, detail="mode must be 'self' or 'external'")
    if hasattr(body, "trigger_mode") and body.trigger_mode and body.trigger_mode not in VALID_TRIGGER_MODES:
        raise HTTPException(status_code=422, detail="trigger_mode must be 'on_demand' or 'scheduled'")
    if hasattr(body, "trigger_mode") and body.trigger_mode == "scheduled":
        cron = getattr(body, "cron_expr", None)
        if not cron:
            raise HTTPException(status_code=422, detail="cron_expr is required when trigger_mode is 'scheduled'")
    if hasattr(body, "mode") and body.mode == "external":
        ep = getattr(body, "service_endpoint_id", None)
        if not ep:
            raise HTTPException(status_code=422, detail="service_endpoint_id is required when mode is 'external'")


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=List[BotOut])
async def list_bots(
    bot_type: Optional[str] = Query(None, description="Filter by bot_type."),
    mode: Optional[str] = Query(None, description="Filter by mode (self/external)."),
    is_enabled: Optional[bool] = Query(None, description="Filter by enabled state."),
    trigger_mode: Optional[str] = Query(None, description="Filter by trigger_mode."),
    search: Optional[str] = Query(None, description="Search by name."),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    stmt = select(Bot).where(Bot.org_id == get_active_org_id(user))
    if bot_type:
        stmt = stmt.where(Bot.bot_type == bot_type)
    if mode:
        stmt = stmt.where(Bot.mode == mode)
    if is_enabled is not None:
        stmt = stmt.where(Bot.is_enabled == is_enabled)
    if trigger_mode:
        stmt = stmt.where(Bot.trigger_mode == trigger_mode)
    if search:
        stmt = stmt.where(Bot.name.ilike(f"%{search}%"))
    stmt = stmt.order_by(Bot.name).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=BotOut, status_code=status.HTTP_201_CREATED)
async def create_bot(
    body: BotCreate,
    user: User = Depends(require_permission("bot", "create")),
    db: AsyncSession = Depends(get_session),
):
    _validate_bot(body)
    bot = Bot(
        org_id=get_active_org_id(user),
        created_by=user.id,
        **body.model_dump(),
    )
    db.add(bot)
    await db.flush([bot])
    await emit(db, entity_type="bot", action="created", entity_id=bot.id,
               org_id=get_active_org_id(user), actor_id=user.id, details={"name": bot.name, "bot_type": bot.bot_type})
    await db.commit()
    await db.refresh(bot)
    return bot


@router.get("/{bot_id}", response_model=BotOut)
async def get_bot(
    bot_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    bot = await db.get(Bot, bot_id)
    if not bot or bot.org_id != get_active_org_id(user):
        raise HTTPException(status_code=404, detail="Bot not found")
    return bot


@router.put("/{bot_id}", response_model=BotOut)
async def update_bot(
    bot_id: uuid.UUID,
    body: BotUpdate,
    user: User = Depends(require_permission("bot", "update")),
    db: AsyncSession = Depends(get_session),
):
    bot = await db.get(Bot, bot_id)
    if not bot or bot.org_id != get_active_org_id(user):
        raise HTTPException(status_code=404, detail="Bot not found")
    _validate_bot(body)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(bot, k, v)
    await db.commit()
    await db.refresh(bot)
    return bot


@router.delete("/{bot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bot(
    bot_id: uuid.UUID,
    user: User = Depends(require_permission("bot", "delete")),
    db: AsyncSession = Depends(get_session),
):
    bot = await db.get(Bot, bot_id)
    if not bot or bot.org_id != get_active_org_id(user):
        raise HTTPException(status_code=404, detail="Bot not found")
    await db.delete(bot)
    await db.commit()


# ── Enable / Disable ──────────────────────────────────────────────────────────

@router.patch("/{bot_id}/enable", response_model=BotOut)
async def enable_bot(
    bot_id: uuid.UUID,
    user: User = Depends(require_permission("bot", "enable")),
    db: AsyncSession = Depends(get_session),
):
    bot = await db.get(Bot, bot_id)
    if not bot or bot.org_id != get_active_org_id(user):
        raise HTTPException(status_code=404, detail="Bot not found")
    bot.is_enabled = True
    await db.commit()
    await db.refresh(bot)
    return bot


@router.patch("/{bot_id}/disable", response_model=BotOut)
async def disable_bot(
    bot_id: uuid.UUID,
    user: User = Depends(require_permission("bot", "disable")),
    db: AsyncSession = Depends(get_session),
):
    bot = await db.get(Bot, bot_id)
    if not bot or bot.org_id != get_active_org_id(user):
        raise HTTPException(status_code=404, detail="Bot not found")
    bot.is_enabled = False
    await db.commit()
    await db.refresh(bot)
    return bot


# ── On-demand Run ─────────────────────────────────────────────────────────────

@router.post("/{bot_id}/run", response_model=BotRunOut)
async def run_bot(
    bot_id: uuid.UUID,
    user: User = Depends(require_permission("bot", "run")),
    db: AsyncSession = Depends(get_session),
):
    """
    Trigger an on-demand run for a bot.

    Accessible by org admins and data asset owners (ABAC enforcement
    will be wired in Phase 2 Module 5). For now any active user in the
    org can trigger a run on an enabled bot.
    """
    bot = await db.get(Bot, bot_id)
    if not bot or bot.org_id != get_active_org_id(user):
        raise HTTPException(status_code=404, detail="Bot not found")
    if not bot.is_enabled:
        raise HTTPException(status_code=400, detail="Bot is disabled. Enable it before running.")

    now = datetime.utcnow()
    bot.last_run_at = now
    bot.last_run_status = "running"
    bot.last_run_message = f"Triggered on-demand by user {user.id}"

    bot_run = BotRun(
        id=uuid.uuid4(),
        bot_id=bot.id,
        org_id=get_active_org_id(user),
        triggered_by=user.id,
        trigger_source="on_demand",
        status="running",
        message=f"Triggered on-demand by user {user.id}",
        output={},
        started_at=now,
    )
    db.add(bot_run)
    await db.commit()
    await db.refresh(bot)

    await emit(db, entity_type="bot", action="run_triggered", entity_id=bot.id,
               org_id=get_active_org_id(user), actor_id=user.id,
               details={"bot_type": bot.bot_type, "mode": bot.mode, "run_id": str(bot_run.id)})
    await db.commit()

    return BotRunOut(
        bot_id=bot.id,
        message=f"Bot '{bot.name}' ({bot.bot_type}) run triggered. Status: running.",
        triggered_at=now,
    )


@router.get("/{bot_id}/runs", response_model=List[BotRunRecord])
async def list_bot_runs(
    bot_id: uuid.UUID,
    status_filter: Optional[str] = Query(None, alias="status", description="pending | running | success | failed | aborted"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    """List all individual run records for a bot (most recent first)."""
    bot = await db.get(Bot, bot_id)
    if not bot or bot.org_id != get_active_org_id(user):
        raise HTTPException(status_code=404, detail="Bot not found")
    stmt = select(BotRun).where(BotRun.bot_id == bot_id, BotRun.org_id == get_active_org_id(user))
    if status_filter:
        stmt = stmt.where(BotRun.status == status_filter)
    stmt = stmt.order_by(BotRun.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()
