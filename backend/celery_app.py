"""Celery application — task queue for bot/agent execution.

Workers pick up tasks enqueued by POST /bots/{id}/run and ScheduledTask triggers.

Usage:
  Start worker:    celery -A celery_app.celery worker --loglevel=info
  Start beat:      celery -A celery_app.celery beat   --loglevel=info
  Monitor:         celery -A celery_app.celery flower
"""
from __future__ import annotations

import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery = Celery(
    "deltameta",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks.bot_tasks"],
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=86400,  # 24 hours
    # Beat scheduler — reads from DB via ScheduledTask model (Phase 3 M6 wiring)
    beat_scheduler="celery.beat:PersistentScheduler",
)
