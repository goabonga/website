# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Celery application configuration."""

from celery import Celery

from internal.config import settings

celery_app = Celery(
    "internal",
    broker=settings.celery_broker_url or settings.redis_url,
    backend=settings.celery_result_backend or settings.redis_url,
    include=[
        "internal.tasks.knowledge_validation",
        "internal.tasks.knowledge_generation",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_default_queue="internal",
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
