# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Celery configuration for Mailler."""

from celery import Celery
from celery.schedules import crontab

from mailler.config import settings

celery_app = Celery(
    "mailler",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Task tracking
    task_track_started=True,
    task_time_limit=300,  # 5 minutes max per task
    task_soft_time_limit=270,  # Soft limit at 4.5 minutes
    # Worker settings
    worker_prefetch_multiplier=1,  # One task at a time
    task_acks_late=True,  # Acknowledge after completion
    task_reject_on_worker_lost=True,  # Re-queue if worker dies
    # Broker settings
    broker_connection_retry_on_startup=True,
    # Queue configuration
    task_default_queue=settings.celery_queue,
    task_queues={
        settings.celery_queue: {
            "exchange": settings.celery_queue,
            "routing_key": settings.celery_queue,
        },
    },
    # Beat schedule for periodic tasks
    beat_schedule={
        "requeue-stuck-emails": {
            "task": "mailler.tasks.scheduler.requeue_stuck_emails",
            "schedule": crontab(minute="*/2"),  # Every 2 minutes
        },
        "process-scheduled-emails": {
            "task": "mailler.tasks.scheduler.process_scheduled_emails",
            "schedule": crontab(minute="*"),  # Every minute
        },
        "cleanup-old-emails": {
            "task": "mailler.tasks.scheduler.cleanup_old_emails",
            "schedule": crontab(hour=3, minute=0),  # Daily at 3 AM
        },
        "aggregate-daily-stats": {
            "task": "mailler.tasks.scheduler.aggregate_daily_stats",
            "schedule": crontab(hour=0, minute=5),  # Daily at 00:05
        },
        "check-scheduled-campaigns": {
            "task": "mailler.tasks.scheduler.check_scheduled_campaigns",
            "schedule": crontab(minute="*"),  # Every minute
        },
        "cleanup-expired-attachments": {
            "task": "mailler.tasks.inbound.cleanup_expired_attachments",
            "schedule": crontab(hour=4, minute=0),  # Daily at 4 AM
        },
    },
)

# Conditionally add inbound polling schedule
if settings.inbound_enabled:
    celery_app.conf.beat_schedule["poll-inbound-emails"] = {
        "task": "mailler.tasks.inbound.poll_inbound_emails",
        "schedule": settings.inbound_poll_interval,  # seconds
    }
    celery_app.conf.beat_schedule["retry-failed-inbound"] = {
        "task": "mailler.tasks.inbound.retry_failed_inbound",
        "schedule": crontab(minute="*/5"),  # Every 5 minutes
    }

# Auto-discover tasks in the mailler.tasks module
celery_app.autodiscover_tasks(["mailler.tasks"])
