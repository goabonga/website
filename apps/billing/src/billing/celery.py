# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Celery application configuration."""

import os

from celery import Celery  # type: ignore[import-untyped]
from celery.signals import setup_logging as celery_setup_logging  # type: ignore[import-untyped]

from billing.config import settings
from billing.logging import setup_logging


@celery_setup_logging.connect
def on_celery_setup_logging(**kwargs):
    """Override Celery's logging setup to use our dual-stream configuration."""
    log_level = os.environ.get("LOG_LEVEL", "INFO")
    setup_logging(level=log_level)


celery_app = Celery(
    "billing",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["billing.tasks.usage_tasks", "billing.tasks.stripe_sync_tasks"],
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.celery_timezone,
    enable_utc=True,
    task_track_started=True,
    task_time_limit=settings.celery_task_time_limit,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    task_default_queue=settings.celery_queue,
    task_queues={
        settings.celery_queue: {
            "exchange": settings.celery_queue,
            "routing_key": settings.celery_queue,
        },
    },
)

# Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    "report-pending-usage": {
        "task": "billing.tasks.usage_tasks.report_pending_usage",
        "schedule": settings.usage_report_interval,
        "kwargs": {"batch_size": settings.usage_report_batch_size},
    },
    "cleanup-old-usage-events": {
        "task": "billing.tasks.usage_tasks.cleanup_old_usage_events",
        "schedule": settings.usage_cleanup_interval,
        "kwargs": {"days_old": settings.usage_retention_days},
    },
    "sync-products-to-stripe": {
        "task": "billing.tasks.stripe_sync_tasks.sync_all_products_to_stripe",
        "schedule": settings.stripe_sync_interval,
    },
}
