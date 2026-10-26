# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Celery configuration for background task processing."""

from celery import Celery

from backend.config import settings

celery_app = Celery(
    "backend",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["backend.tasks.sync_conversations"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,
    worker_prefetch_multiplier=1,
    # Use dedicated queue to avoid task conflicts with other apps
    task_default_queue="backend",
    task_queues={
        "backend": {"exchange": "backend", "routing_key": "backend"},
    },
    # Beat schedule for periodic tasks
    beat_schedule={
        "sync-dirty-conversations": {
            "task": "sync_dirty_conversations",
            "schedule": settings.conversation_sync_interval,  # every N seconds
            "options": {"expires": settings.conversation_sync_interval},
        },
    },
)

# Auto-discover tasks from backend.tasks module
celery_app.autodiscover_tasks(["backend.tasks"])
