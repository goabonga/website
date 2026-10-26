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
        "cleanup-expired-tokens": {
            "task": "cleanup_expired_tokens",
            "schedule": crontab(minute=0),  # Every hour at :00
        },
        "cleanup-expired-authorization-codes": {
            "task": "cleanup_expired_authorization_codes",
            "schedule": crontab(minute="*/15"),  # Every 15 minutes
        },
        "cleanup-expired-device-codes": {
            "task": "cleanup_expired_device_codes",
            "schedule": crontab(minute="*/30"),  # Every 30 minutes
        },
        "cleanup-expired-par-requests": {
            "task": "cleanup_expired_par_requests",
            "schedule": crontab(minute="*/15"),  # Every 15 minutes
        },
        "cleanup-expired-verification-codes": {
            "task": "cleanup_expired_verification_codes",
            "schedule": crontab(minute=0),  # Every hour at :00
        },
        "cleanup-expired-password-reset-tokens": {
            "task": "cleanup_expired_password_reset_tokens",
            "schedule": crontab(minute=0),  # Every hour at :00
        },
        "cleanup-expired-mfa-email-codes": {
            "task": "cleanup_expired_mfa_email_codes",
            "schedule": crontab(minute="*/30"),  # Every 30 minutes
        },
        "cleanup-expired-sessions": {
            "task": "cleanup_expired_sessions",
            "schedule": crontab(minute=0, hour=0),  # Every day at midnight
        },
        "cleanup-expired-pats": {
            "task": "cleanup_expired_pats",
            "schedule": crontab(minute=0, hour=3),  # Every day at 3 AM
        },
        "cleanup-orphaned-avatars": {
            "task": "cleanup_orphaned_avatars",
            "schedule": crontab(minute=0, hour="*/12"),  # Every 12 hours (0:00, 12:00)
        },
        "cleanup-unverified-users": {
            "task": "cleanup_unverified_users",
            "schedule": crontab(minute=30, hour="*/12"),  # Every 12 hours (0:30, 12:30)
        },
        "check-pending-custom-domains": {
            "task": "check_pending_custom_domains",
            "schedule": crontab(minute="*/5"),  # Every 5 minutes
        },
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
