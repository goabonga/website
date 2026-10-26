# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Celery task that delivers a notification to a SaaS application, with retries."""

import asyncio
import logging
from typing import Any

from billing.celery import celery_app
from billing.config import settings
from billing.database import async_session_factory
from billing.services.saas_webhook import (
    WebhookDeliveryError,
    deliver_event,
    get_saas_app_by_id,
    new_http_client,
)

logger = logging.getLogger(__name__)


def retry_delay(retries: int) -> float:
    """Delay before the next attempt, after ``retries`` retries already made.

    ``SAAS_WEBHOOK_BACKOFF_SECONDS`` before the second attempt, multiplied by
    ``SAAS_WEBHOOK_BACKOFF_FACTOR`` after each failure, never more than
    ``SAAS_WEBHOOK_BACKOFF_MAX_SECONDS``.
    """
    delay = settings.saas_webhook_backoff_seconds * settings.saas_webhook_backoff_factor**retries
    return min(delay, settings.saas_webhook_backoff_max_seconds)


def should_retry(error: WebhookDeliveryError, retries: int) -> bool:
    """Tell whether a failed attempt is retried.

    Only retryable failures are, and at most ``SAAS_WEBHOOK_MAX_ATTEMPTS``
    attempts are made in total (``retries`` retries follow the first attempt).
    """
    return error.retryable and retries + 1 < settings.saas_webhook_max_attempts


async def _deliver(saas_app_id: str, event: dict[str, Any]) -> None:
    """Load the SaaS application, so that a changed URL or secret is honored, and send."""
    async with async_session_factory() as db:
        saas_app = await get_saas_app_by_id(db, saas_app_id)
    if saas_app is None:
        raise WebhookDeliveryError("SaaS app no longer exists", retryable=False)
    # The shared client belongs to the event loop of the API: this task has its own loop
    async with new_http_client() as client:
        await deliver_event(saas_app, event, client=client)


@celery_app.task(bind=True, name="billing.tasks.webhook_tasks.deliver_saas_webhook")
def deliver_saas_webhook(self, saas_app_id: str, event: dict[str, Any]) -> dict:
    """Deliver an event to the webhook URL of a SaaS application.

    The event (with its stable ``id``) is built by the API; every attempt
    sends the same body, signed with the current secret of the application. A
    retryable failure is tried again after ``retry_delay``, up to
    ``SAAS_WEBHOOK_MAX_ATTEMPTS`` attempts; other failures are final.

    Args:
        saas_app_id: Identifier of the SaaS application to notify.
        event: The event, JSON-serializable.

    Returns:
        Dict with the event id, whether it was delivered and the number of attempts.
    """
    retries = self.request.retries
    try:
        asyncio.run(_deliver(saas_app_id, event))
    except WebhookDeliveryError as error:
        if should_retry(error, retries):
            delay = retry_delay(retries)
            logger.warning(
                f"Webhook {event['id']} failed ({error}), attempt {retries + 1} of "
                f"{settings.saas_webhook_max_attempts}, retrying in {delay:.0f}s"
            )
            raise self.retry(exc=error, countdown=delay)
        logger.error(f"Webhook {event['id']} given up after {retries + 1} attempt(s): {error}")
        return {"event_id": event["id"], "delivered": False, "attempts": retries + 1}
    return {"event_id": event["id"], "delivered": True, "attempts": retries + 1}
