# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Celery application configuration."""

from celery import Celery
from celery.schedules import crontab

from custom_domain.config import settings

celery_app = Celery(
    "custom-domain",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=settings.celery_task_soft_time_limit_seconds,
    task_time_limit=settings.celery_task_time_limit_seconds,
    # The worker is started on this queue (``--queues``): publish every task to it.
    task_default_queue=settings.celery_queue,
    task_routes={"custom_domain.tasks.*": {"queue": settings.celery_queue}},
)


def periodic(task_name: str, schedule) -> dict:
    """Build a beat entry that publishes to the queue the worker consumes."""
    return {
        "task": task_name,
        "schedule": schedule,
        "options": {"queue": settings.celery_queue},
    }


# Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    "check-pending-domains": periodic(
        "custom_domain.tasks.verification.check_pending_domains",
        crontab(minute=f"*/{settings.dns_check_interval_minutes}"),
    ),
}

# Auto-discover tasks
celery_app.autodiscover_tasks(["custom_domain.tasks"])
