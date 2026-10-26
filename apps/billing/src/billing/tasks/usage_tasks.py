# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Celery tasks for usage-based billing."""

import hashlib
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import CursorResult, delete, select

from billing.celery import celery_app
from billing.config import settings
from billing.database import async_session_factory
from billing.models import Subscription, UsageEvent, UsageEventStatus
from billing.services import get_stripe_service

logger = logging.getLogger(__name__)


def stripe_idempotency_key(saas_app_id: str, key: str | None) -> str | None:
    """Namespace the idempotency key of a usage event for Stripe.

    Idempotency keys are unique per SaaS application here, but Stripe applies
    them to the whole account: two applications using the same key would see
    the second report swallowed. The key sent to Stripe is a digest of the
    application and of the key given by the application.
    """
    if not key:
        return None
    return hashlib.sha256(f"{saas_app_id}:{key}".encode()).hexdigest()


@celery_app.task(bind=True, name="billing.tasks.usage_tasks.report_pending_usage")
def report_pending_usage(self, batch_size: int | None = None) -> dict:
    """Process pending usage events and report to Stripe.

    This task runs periodically to batch-report usage events to Stripe.
    It processes events in order of creation and marks them as reported.

    Args:
        batch_size: Maximum number of events to process in one run
            (``USAGE_REPORT_BATCH_SIZE`` when omitted).

    Returns:
        Dict with processing statistics.
    """
    import asyncio

    batch_size = batch_size or settings.usage_report_batch_size

    async def _process():
        stripe_service = get_stripe_service()
        processed = 0
        success = 0
        failed = 0

        async with async_session_factory() as db:
            # Get pending events
            result = await db.execute(
                select(UsageEvent)
                .where(UsageEvent.status == UsageEventStatus.PENDING)
                .order_by(UsageEvent.created_at)
                .limit(batch_size)
            )
            pending_events = list(result.scalars().all())

            if not pending_events:
                logger.debug("No pending usage events to process")
                return {"processed": 0, "success": 0, "failed": 0}

            logger.info(f"Processing {len(pending_events)} pending usage events")

            for event in pending_events:
                processed += 1

                # Get subscription to get Stripe subscription item ID
                sub_result = await db.execute(
                    select(Subscription).where(Subscription.id == event.subscription_id)
                )
                subscription = sub_result.scalar_one_or_none()

                if not subscription:
                    event.status = UsageEventStatus.FAILED
                    event.error_message = "Subscription not found"
                    failed += 1
                    continue

                if not subscription.stripe_subscription_item_id:
                    event.status = UsageEventStatus.FAILED
                    event.error_message = "No subscription item ID (not metered)"
                    failed += 1
                    continue

                try:
                    # Report usage to Stripe
                    usage_record = stripe_service.report_usage(
                        stripe_subscription_item_id=subscription.stripe_subscription_item_id,
                        quantity=event.quantity,
                        timestamp=int(event.timestamp.timestamp()),
                        idempotency_key=stripe_idempotency_key(
                            event.saas_app_id, event.idempotency_key
                        ),
                    )

                    # Mark as reported
                    event.status = UsageEventStatus.REPORTED
                    record_id = usage_record["id"]
                    event.stripe_usage_record_id = record_id
                    event.reported_at = datetime.now(UTC)
                    success += 1

                    logger.debug(
                        f"Reported usage: {event.id} -> {record_id} (quantity={event.quantity})"
                    )

                except Exception as e:
                    event.status = UsageEventStatus.FAILED
                    event.error_message = str(e)[:500]
                    failed += 1
                    logger.error(f"Failed to report usage {event.id}: {e}")

            await db.commit()

        logger.info(
            f"Usage reporting complete: processed={processed}, success={success}, failed={failed}"
        )
        return {"processed": processed, "success": success, "failed": failed}

    return asyncio.run(_process())


@celery_app.task(bind=True, name="billing.tasks.usage_tasks.cleanup_old_usage_events")
def cleanup_old_usage_events(self, days_old: int | None = None) -> dict:
    """Delete old reported usage events.

    Cleans up usage events that have been successfully reported
    and are older than the specified number of days.

    Args:
        days_old: Delete events older than this many days
            (``USAGE_RETENTION_DAYS`` when omitted).

    Returns:
        Dict with deletion statistics.
    """
    import asyncio

    days_old = days_old if days_old is not None else settings.usage_retention_days

    async def _cleanup():
        cutoff_date = datetime.now(UTC) - timedelta(days=days_old)

        async with async_session_factory() as db:
            # Delete old reported events
            delete_result: CursorResult[tuple[()]] = await db.execute(  # type: ignore[assignment]
                delete(UsageEvent).where(
                    UsageEvent.status == UsageEventStatus.REPORTED,
                    UsageEvent.reported_at < cutoff_date,
                )
            )
            deleted_count = delete_result.rowcount
            await db.commit()

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old usage events (older than {days_old} days)")
        else:
            logger.debug("No old usage events to clean up")

        return {"deleted": deleted_count}

    return asyncio.run(_cleanup())
