# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Celery tasks for outbound tenant webhook delivery.

Three tasks:

- ``deliver_webhook``: perform a single HTTP attempt for a
  :class:`WebhookDelivery` row, capture the response, and either mark it
  success/failed or schedule a DB-backed retry.
- ``retry_pending_webhooks``: beat-driven scheduler that re-enqueues
  deliveries in ``RETRYING`` status whose ``next_retry_at`` has elapsed.
- ``cleanup_webhook_deliveries``: retention by age and by per-webhook cap.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from auth.celery import celery_app
from auth.config import settings
from auth.core.database import get_sync_db
from auth.db.models.tenant import WebhookDeliveryStatus
from auth.db.repositories.cleanup import cleanup_repository
from auth.services.webhook import (
    WebhookURLError,
    build_request_headers,
    serialize_body,
    validate_target_url,
)

logger = logging.getLogger(__name__)

# Exponential backoff schedule keyed by the attempt number that just failed.
# attempt 1 failed -> wait 60s, attempt 2 -> 5m, attempt 3 -> 30m, etc.
_BACKOFF_SECONDS: dict[int, int] = {
    1: 60,
    2: 5 * 60,
    3: 30 * 60,
    4: 2 * 60 * 60,
    5: 12 * 60 * 60,
}


def _next_retry_delay(attempt: int) -> int:
    return _BACKOFF_SECONDS.get(attempt, 12 * 60 * 60)


def _is_success(status_code: int) -> bool:
    return 200 <= status_code < 300


def _truncate_body(body: str) -> str:
    max_bytes = settings.webhook_response_body_max_bytes
    encoded = body.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return body
    return encoded[:max_bytes].decode("utf-8", errors="replace") + "... [truncated]"


@celery_app.task(name="deliver_webhook", ignore_result=True)
def deliver_webhook(delivery_id: str) -> dict[str, Any]:
    """Attempt a single delivery for ``delivery_id``.

    On 2xx the delivery is marked ``success``. On non-2xx or transport error
    the delivery is either scheduled for retry (``status=retrying``,
    ``next_retry_at`` populated) or marked ``failed`` if ``max_attempts`` is
    reached.
    """
    with get_sync_db() as db:
        delivery = cleanup_repository.get_delivery_sync(db, delivery_id)
        if delivery is None:
            logger.warning("deliver_webhook: delivery %s not found", delivery_id)
            return {"status": "not_found", "delivery_id": delivery_id}

        if delivery.status not in (
            WebhookDeliveryStatus.PENDING,
            WebhookDeliveryStatus.RETRYING,
        ):
            logger.info(
                "deliver_webhook: delivery %s already finalized (status=%s), skipping",
                delivery_id,
                delivery.status,
            )
            return {"status": "skipped", "delivery_id": delivery_id}

        webhook = cleanup_repository.get_webhook_sync(db, delivery.webhook_id)
        if webhook is None:
            delivery.status = WebhookDeliveryStatus.FAILED
            delivery.error = "Webhook configuration was deleted"
            delivery.delivered_at = datetime.now(UTC)
            return {"status": "failed", "delivery_id": delivery_id, "reason": "missing_webhook"}

        # Re-validate target every attempt in case config changed since enqueue.
        try:
            validate_target_url(webhook.url)
        except WebhookURLError as e:
            delivery.status = WebhookDeliveryStatus.FAILED
            delivery.error = f"Target URL rejected: {e}"
            delivery.delivered_at = datetime.now(UTC)
            webhook.last_error = delivery.error
            webhook.failure_count += 1
            return {"status": "failed", "delivery_id": delivery_id, "reason": "unsafe_url"}

        attempt = delivery.attempt + 1
        body = serialize_body(delivery.request_body)
        timestamp = int(datetime.now(UTC).timestamp())
        headers = build_request_headers(
            webhook=webhook,
            delivery_id=delivery.id,
            event=delivery.event,
            attempt=attempt,
            body=body,
            timestamp=timestamp,
        )

        delivery.attempt = attempt
        delivery.request_url = webhook.url
        delivery.request_headers = headers

        started = datetime.now(UTC)
        response_status: int | None = None
        response_headers: dict[str, str] | None = None
        response_body: str | None = None
        error: str | None = None

        try:
            timeout = httpx.Timeout(settings.webhook_delivery_timeout_seconds)
            with httpx.Client(timeout=timeout, follow_redirects=False) as client:
                response = client.post(webhook.url, content=body, headers=headers)
            response_status = response.status_code
            response_headers = dict(response.headers)
            response_body = _truncate_body(response.text)
        except (httpx.HTTPError, OSError) as e:
            error = f"{type(e).__name__}: {e}"
            logger.warning(
                "Webhook delivery transport error (delivery=%s, attempt=%d): %s",
                delivery_id,
                attempt,
                error,
            )

        duration_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)

        delivery.response_status = response_status
        delivery.response_headers = response_headers
        delivery.response_body = response_body
        delivery.error = error
        delivery.duration_ms = duration_ms
        delivery.delivered_at = datetime.now(UTC)

        webhook.last_triggered_at = delivery.delivered_at
        webhook.last_status_code = response_status
        webhook.last_error = (
            error if not (response_status and _is_success(response_status)) else None
        )

        success = response_status is not None and _is_success(response_status)

        if success:
            delivery.status = WebhookDeliveryStatus.SUCCESS
            delivery.next_retry_at = None
            webhook.failure_count = 0
            return {
                "status": "success",
                "delivery_id": delivery_id,
                "response_status": response_status,
                "attempt": attempt,
            }

        webhook.failure_count += 1

        if attempt >= delivery.max_attempts:
            delivery.status = WebhookDeliveryStatus.FAILED
            delivery.next_retry_at = None
            return {
                "status": "failed",
                "delivery_id": delivery_id,
                "response_status": response_status,
                "attempt": attempt,
            }

        delay = _next_retry_delay(attempt)
        delivery.status = WebhookDeliveryStatus.RETRYING
        delivery.next_retry_at = datetime.now(UTC) + timedelta(seconds=delay)
        return {
            "status": "retrying",
            "delivery_id": delivery_id,
            "response_status": response_status,
            "attempt": attempt,
            "retry_in_seconds": delay,
        }


@celery_app.task(name="retry_pending_webhooks")
def retry_pending_webhooks() -> dict[str, int]:
    """Re-enqueue deliveries whose ``next_retry_at`` has elapsed.

    We atomically flip ``status`` from ``retrying`` back to ``pending`` in
    one UPDATE and return the affected ids, which guarantees that two beat
    ticks running concurrently never double-enqueue the same delivery.
    """
    now = datetime.now(UTC)

    with get_sync_db() as db:
        ids = cleanup_repository.reset_retrying_webhook_deliveries(db, now)

    for delivery_id in ids:
        deliver_webhook.delay(str(delivery_id))

    if ids:
        logger.info("retry_pending_webhooks: re-enqueued %d delivery/ies", len(ids))

    return {"rescheduled": len(ids)}


@celery_app.task(name="cleanup_webhook_deliveries")
def cleanup_webhook_deliveries() -> dict[str, int]:
    """Delete delivery rows older than the retention window.

    Combines age-based retention (``webhook_retention_days``) with a
    per-webhook cap (``webhook_retention_max_per_hook``) so that a very
    chatty hook does not blow past the cap between daily runs.
    """
    retention_days = settings.webhook_retention_days
    per_hook_cap = settings.webhook_retention_max_per_hook
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)

    deleted_age = 0
    deleted_cap = 0

    with get_sync_db() as db:
        deleted_age = cleanup_repository.delete_webhook_deliveries_older_than(db, cutoff)

        # Enforce per-webhook cap: find webhooks over the cap, then delete the
        # overflow in each one. Small N in practice (a handful of webhooks).
        for webhook_id in cleanup_repository.list_tenant_webhook_ids(db):
            deleted_cap += cleanup_repository.delete_webhook_deliveries_over_cap(
                db, webhook_id, per_hook_cap
            )

    if deleted_age or deleted_cap:
        logger.info(
            "cleanup_webhook_deliveries: deleted %d (age) + %d (cap)",
            deleted_age,
            deleted_cap,
        )

    return {"deleted_by_age": deleted_age, "deleted_by_cap": deleted_cap}
