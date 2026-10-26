# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Celery application configuration."""

import os

from celery import Celery  # type: ignore[import-untyped]
from celery.signals import setup_logging as celery_setup_logging  # type: ignore[import-untyped]

from team.config import settings
from team.logging import setup_logging


@celery_setup_logging.connect
def on_celery_setup_logging(**kwargs):
    """Override Celery's logging setup to use our dual-stream configuration."""
    log_level = os.environ.get("LOG_LEVEL", "INFO")
    setup_logging(level=log_level)


celery_app = Celery(
    "team",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "team.tasks.dispatch_tasks",
        "team.tasks.cleanup_tasks",
        "team.tasks.memory_tasks",
        "team.tasks.webhook_tasks",
        "team.tasks.agent_runner",
        "team.tasks.auto_orchestrate",
    ],
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Paris",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max per task
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    task_default_queue="team",
    task_queues={
        "team": {"exchange": "team", "routing_key": "team"},
    },
)

# Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    "dispatch-tasks-every-5-minutes": {
        "task": "team.tasks.dispatch_tasks.dispatch_tasks",
        "schedule": 300.0,  # Every 5 minutes
        "kwargs": {"batch_size": 50},
    },
    "cleanup-old-logs-daily": {
        "task": "team.tasks.cleanup_tasks.cleanup_old_logs",
        "schedule": 86400.0,  # Every 24 hours
        "kwargs": {"days_old": 90},
    },
    "summarize-memory-hourly": {
        "task": "team.tasks.memory_tasks.summarize_memory",
        "schedule": 3600.0,  # Every hour
    },
    "cleanup-stale-workspaces-hourly": {
        "task": "team.tasks.cleanup_tasks.cleanup_stale_workspaces",
        "schedule": 3600.0,  # Every hour
    },
    "auto-orchestrate-every-15-minutes": {
        "task": "team.tasks.auto_orchestrate.auto_orchestrate",
        "schedule": 900.0,  # Every 15 minutes
        "kwargs": {"team_slug": "goabonga"},
    },
}
