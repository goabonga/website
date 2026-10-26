# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Scheduled tasks for Mailler."""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, func, select

from mailler.celery import celery_app
from mailler.config import settings
from mailler.database import get_sync_db
from mailler.logging import get_logger
from mailler.models.email import Email, EmailStatus, ProviderStats
from mailler.tasks.send import send_email_task

logger = get_logger(__name__)


@celery_app.task(name="mailler.tasks.scheduler.requeue_stuck_emails")
def requeue_stuck_emails(stuck_minutes: int | None = None) -> dict:
    """Requeue emails stuck in pending status.

    Finds emails that have been in "pending" status for too long
    (task was never picked up or failed silently) and requeues them.

    Runs every 2 minutes via Celery Beat.

    Args:
        stuck_minutes: Consider emails stuck after this many minutes
            (defaults to ``STUCK_EMAIL_MINUTES``)

    Returns:
        Dict with count of requeued emails
    """
    with get_sync_db() as db:
        if stuck_minutes is None:
            stuck_minutes = settings.stuck_email_minutes
        cutoff = datetime.now(UTC) - timedelta(minutes=stuck_minutes)

        # Find stuck pending emails (no scheduled_at = immediate send that got stuck)
        stmt = (
            select(Email)
            .where(
                Email.status == EmailStatus.PENDING.value,
                Email.scheduled_at.is_(None),  # Immediate sends only
                Email.created_at < cutoff,  # Older than X minutes
            )
            .limit(settings.stuck_email_batch)  # Process in batches
        )

        stuck_emails = db.execute(stmt).scalars().all()

        requeued_count = 0
        for email in stuck_emails:
            try:
                send_email_task.delay(str(email.id))
                requeued_count += 1
                logger.info(
                    "Requeued stuck email",
                    extra={
                        "email_id": str(email.id),
                        "created_at": str(email.created_at),
                    },
                )
            except Exception as e:
                logger.error(
                    "Failed to requeue stuck email",
                    extra={"email_id": str(email.id), "error": str(e)},
                )

        if requeued_count > 0:
            logger.info(
                "Requeued stuck emails",
                extra={"requeued_count": requeued_count},
            )

        return {"requeued": requeued_count}


@celery_app.task(name="mailler.tasks.scheduler.process_scheduled_emails")
def process_scheduled_emails() -> dict:
    """Process scheduled emails that are due for sending.

    Runs every minute via Celery Beat.

    Returns:
        Dict with count of queued emails
    """
    with get_sync_db() as db:
        now = datetime.now(UTC)

        # Find scheduled emails that are due
        stmt = (
            select(Email)
            .where(
                Email.status == EmailStatus.PENDING.value,
                Email.scheduled_at.isnot(None),
                Email.scheduled_at <= now,
            )
            .limit(settings.scheduled_email_batch)  # Process in batches
        )

        scheduled_emails = db.execute(stmt).scalars().all()

        queued_count = 0
        for email in scheduled_emails:
            try:
                send_email_task.delay(str(email.id))
                queued_count += 1
                logger.debug(
                    "Queued scheduled email",
                    extra={
                        "email_id": str(email.id),
                        "scheduled_at": str(email.scheduled_at),
                    },
                )
            except Exception as e:
                logger.error(
                    "Failed to queue scheduled email",
                    extra={"email_id": str(email.id), "error": str(e)},
                )

        if queued_count > 0:
            logger.info(
                "Processed scheduled emails",
                extra={"queued_count": queued_count},
            )

        return {"queued": queued_count}


@celery_app.task(name="mailler.tasks.scheduler.cleanup_old_emails")
def cleanup_old_emails(days: int | None = None) -> dict:
    """Clean up old email records.

    Runs daily via Celery Beat.

    Args:
        days: Delete emails older than this many days (defaults to ``EMAIL_RETENTION_DAYS``)

    Returns:
        Dict with count of deleted emails
    """
    with get_sync_db() as db:
        if days is None:
            days = settings.email_retention_days
        cutoff = datetime.now(UTC) - timedelta(days=days)

        # Delete old emails
        stmt = delete(Email).where(Email.created_at < cutoff)
        result = db.execute(stmt)
        deleted_count: int = getattr(result, "rowcount", 0) or 0
        db.commit()

        if deleted_count > 0:
            logger.info(
                "Cleaned up old emails",
                extra={"deleted_count": deleted_count, "older_than_days": days},
            )

        return {"deleted": deleted_count}


@celery_app.task(name="mailler.tasks.scheduler.aggregate_daily_stats")
def aggregate_daily_stats() -> dict:
    """Aggregate email statistics for the previous day.

    Runs daily at 00:05 via Celery Beat.

    Returns:
        Dict with aggregated stats
    """
    with get_sync_db() as db:
        yesterday = date.today() - timedelta(days=1)
        start_of_day = datetime.combine(yesterday, datetime.min.time()).replace(tzinfo=UTC)
        end_of_day = datetime.combine(yesterday, datetime.max.time()).replace(tzinfo=UTC)

        # Get counts by provider and status
        stmt = (
            select(
                Email.provider,
                Email.status,
                func.count(Email.id).label("count"),
            )
            .where(
                Email.created_at >= start_of_day,
                Email.created_at <= end_of_day,
            )
            .group_by(Email.provider, Email.status)
        )

        results = db.execute(stmt).all()

        # Update or create stats records
        stats_by_provider: dict = {}
        for provider, status, count in results:
            if provider not in stats_by_provider:
                stats_by_provider[provider] = {
                    "sent": 0,
                    "delivered": 0,
                    "bounced": 0,
                    "failed": 0,
                }

            if status == EmailStatus.SENT.value:
                stats_by_provider[provider]["sent"] += count
            elif status == EmailStatus.DELIVERED.value:
                stats_by_provider[provider]["delivered"] += count
            elif status == EmailStatus.BOUNCED.value:
                stats_by_provider[provider]["bounced"] += count
            elif status == EmailStatus.FAILED.value:
                stats_by_provider[provider]["failed"] += count

        # Upsert stats records
        for provider, counts in stats_by_provider.items():
            stats_stmt = select(ProviderStats).where(
                ProviderStats.date == yesterday,
                ProviderStats.provider == provider,
            )
            stats = db.execute(stats_stmt).scalar_one_or_none()

            if stats is None:
                stats = ProviderStats(date=yesterday, provider=provider)
                db.add(stats)

            stats.sent_count = counts["sent"]
            stats.delivered_count = counts["delivered"]
            stats.bounced_count = counts["bounced"]
            stats.failed_count = counts["failed"]

        db.commit()

        logger.info(
            "Aggregated daily stats",
            extra={"date": str(yesterday), "providers": list(stats_by_provider.keys())},
        )

        return {"date": str(yesterday), "stats": stats_by_provider}
