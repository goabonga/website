# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Celery application configuration."""

import logging
import os

from celery import Celery

from knowledge.config import get_settings

settings = get_settings()

# Configure logging for Celery
logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO")),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

celery_app = Celery(
    "knowledge",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["knowledge.tasks"],
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
    "process-scheduled-deletions": {
        "task": "knowledge.tasks.process_scheduled_deletions",
        "schedule": settings.deletion_check_interval,
    },
    "send-deletion-reminders": {
        "task": "knowledge.tasks.send_deletion_reminders",
        "schedule": settings.deletion_check_interval,
    },
}
