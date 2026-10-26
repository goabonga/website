# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Celery application configuration."""

from celery import Celery
from celery.schedules import crontab

from auth.config import settings

# Create Celery app with optional result backend
# Result backend is disabled by default for fire-and-forget tasks (emails)
celery_kwargs = {
    "main": "auth",
    "broker": settings.celery_broker_url,
}
if settings.celery_result_backend:
    celery_kwargs["backend"] = settings.celery_result_backend

celery_app = Celery(**celery_kwargs)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes max per task
    task_soft_time_limit=240,  # Soft limit at 4 minutes
    worker_prefetch_multiplier=1,  # Fair task distribution
    task_acks_late=True,  # Ack after task completion
    task_reject_on_worker_lost=True,  # Re-queue if worker dies
    broker_connection_retry_on_startup=True,
    # Use dedicated queue to avoid task conflicts with other apps
    task_default_queue="auth",
    task_queues={
        "auth": {"exchange": "auth", "routing_key": "auth"},
    },
    # Beat schedule for periodic tasks
    beat_schedule={
        "retry-pending-webhooks": {
            "task": "retry_pending_webhooks",
            "schedule": crontab(minute="*"),  # Every minute
        },
        "cleanup-webhook-deliveries": {
            "task": "cleanup_webhook_deliveries",
            "schedule": crontab(minute=15, hour=3),  # Every day at 03:15
        },
    },
)

# Auto-discover tasks in auth.tasks module
celery_app.autodiscover_tasks(["auth.tasks"])
