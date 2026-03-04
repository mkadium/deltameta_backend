"""Celery tasks for bot/agent execution.

When POST /bots/{id}/run is called, a BotRun record is created with status=running.
The actual agent logic runs here asynchronously via Celery.

Each bot_type dispatches to its agent module in backend/agents/.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from celery_app import celery


@celery.task(bind=True, name="bot_tasks.run_bot", max_retries=2, default_retry_delay=30)
def run_bot_task(self, bot_run_id: str, bot_id: str, org_id: str, bot_type: str, mode: str, config: dict):
    """
    Execute a bot run.

    Args:
        bot_run_id: UUID of the BotRun record to update
        bot_id:     UUID of the Bot configuration
        org_id:     UUID of the organization
        bot_type:   e.g. "metadata", "profiler", "lineage", "classification", etc.
        mode:       "self" or "external"
        config:     Dict with service_endpoint url/key, model_name, etc.
    """
    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import select
    from app.govern.models import BotRun, Bot

    db_url = _build_db_url()
    engine = create_async_engine(db_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _execute():
        async with Session() as session:
            run = await session.get(BotRun, uuid.UUID(bot_run_id))
            if not run:
                return

            run.started_at = datetime.now(timezone.utc)
            run.status = "running"
            await session.commit()

            try:
                result = await _dispatch(bot_type, mode, config, org_id, session)
                run.status = "success"
                run.message = result.get("message", "Completed successfully")
                run.output = result
            except Exception as exc:
                run.status = "failed"
                run.message = str(exc)[:500]
                run.output = {"error": str(exc)}

            run.completed_at = datetime.now(timezone.utc)

            # Update parent Bot last_run_*
            bot = await session.get(Bot, uuid.UUID(bot_id))
            if bot:
                bot.last_run_at = run.completed_at
                bot.last_run_status = run.status
                bot.last_run_message = run.message

            await session.commit()

    asyncio.run(_execute())
    engine.sync_engine.dispose()


async def _dispatch(bot_type: str, mode: str, config: dict, org_id: str, session) -> dict:
    """Route to the correct agent module based on bot_type."""
    # Phase 3 M7: agent modules live in backend/agents/
    # Each is imported lazily to avoid loading all dependencies at startup.
    if bot_type == "metadata":
        from agents.postgres_metadata import run as agent_run
        return await agent_run(mode=mode, config=config, org_id=org_id, session=session)

    elif bot_type == "profiler":
        from agents.postgres_profiler import run as agent_run
        return await agent_run(mode=mode, config=config, org_id=org_id, session=session)

    elif bot_type == "lineage":
        from agents.postgres_lineage import run as agent_run
        return await agent_run(mode=mode, config=config, org_id=org_id, session=session)

    elif bot_type == "classification":
        from agents.postgres_classifier import run as agent_run
        return await agent_run(mode=mode, config=config, org_id=org_id, session=session)

    elif bot_type == "usage":
        from agents.postgres_usage import run as agent_run
        return await agent_run(mode=mode, config=config, org_id=org_id, session=session)

    elif bot_type == "search_index":
        from agents.search_indexer import run as agent_run
        return await agent_run(mode=mode, config=config, org_id=org_id, session=session)

    elif bot_type == "test_suite":
        from agents.test_suite_runner import run as agent_run
        return await agent_run(mode=mode, config=config, org_id=org_id, session=session)

    elif bot_type == "rdf_export":
        from agents.rdf_exporter import run as agent_run
        return await agent_run(mode=mode, config=config, org_id=org_id, session=session)

    elif bot_type == "embedding":
        from agents.embedding_bot import run as agent_run
        return await agent_run(mode=mode, config=config, org_id=org_id, session=session)

    else:
        return {"message": f"Bot type '{bot_type}' not yet implemented. Skipped.", "skipped": True}


def _build_db_url() -> str:
    host = os.getenv("PRIMARY_DB_HOST", "localhost")
    port = os.getenv("PRIMARY_DB_PORT", "5432")
    user = os.getenv("PRIMARY_DB_USER", "postgres")
    password = os.getenv("PRIMARY_DB_PASSWORD", "")
    name = os.getenv("PRIMARY_DB_NAME", "deltameta")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"
