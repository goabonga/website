# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Delivery of the status webhooks of the clients."""

import json

import httpx
from sqlalchemy import select

from custom_domain.celery import celery_app
from custom_domain.config import settings
from custom_domain.database import get_sync_db
from custom_domain.logging import get_logger
from custom_domain.models import AuthorizedClient, CustomDomain
from custom_domain.webhook_signature import (
    DELIVERY_HEADER,
    EVENT_HEADER,
    SIGNATURE_HEADER,
    signature_header,
)

logger = get_logger(__name__)


def build_body(
    domain: CustomDomain, event: str, data: dict, delivery_id: str, created_at: str
) -> bytes:
    """Serialize a webhook delivery.

    The body is ``{id, event, created_at, domain, data}``: ``domain`` is a snapshot of
    the domain when the delivery is made, ``data`` the details of the event. The same
    ``id`` and ``created_at`` are kept across retries so that a receiver can
    deduplicate.
    """
    document = {
        "id": delivery_id,
        "event": event,
        "created_at": created_at,
        "domain": {
            "id": str(domain.id),
            "domain": domain.domain,
            "status": domain.status.value,
            "client_id": domain.client_id,
            "owner_id": domain.owner_id,
            "owner_type": domain.owner_type,
            "metadata": domain.metadata_ or {},
            "error": domain.error_message,
        },
        "data": data,
    }
    return json.dumps(document, sort_keys=True, separators=(",", ":"), default=str).encode()


@celery_app.task(
    bind=True,
    max_retries=settings.webhook_max_retries,
    default_retry_delay=settings.webhook_retry_delay_seconds,
)
def deliver_webhook(
    self,
    domain_id: str,
    event: str,
    data: dict,
    delivery_id: str,
    created_at: str,
) -> str:
    """POST a signed notification to the webhook of the domain's client.

    Nothing is sent when the domain is unknown or its client is unknown, inactive or
    has no webhook. A network error or a non-2xx answer is retried with an
    exponential back-off (``WEBHOOK_RETRY_DELAY_SECONDS`` doubling, up to
    ``WEBHOOK_MAX_RETRIES``); redirects are not followed.

    Returns:
        ``"skipped"``, ``"delivered"`` or ``"failed"`` (retries exhausted)
    """
    with get_sync_db() as db:
        domain = db.execute(
            select(CustomDomain).where(CustomDomain.id == domain_id)
        ).scalar_one_or_none()
        if not domain:
            return "skipped"

        client = db.execute(
            select(AuthorizedClient).where(AuthorizedClient.client_id == domain.client_id)
        ).scalar_one_or_none()
        if (
            not client
            or not client.is_active
            or not client.webhook_url
            or not client.webhook_secret
        ):
            return "skipped"

        url, secret = client.webhook_url, client.webhook_secret
        body = build_body(domain, event, data, delivery_id, created_at)

    headers = {
        "Content-Type": "application/json",
        SIGNATURE_HEADER: signature_header(secret, body),
        EVENT_HEADER: event,
        DELIVERY_HEADER: delivery_id,
    }

    try:
        response = httpx.post(
            url,
            content=body,
            headers=headers,
            timeout=settings.webhook_timeout_seconds,
            follow_redirects=False,
        )
        if response.is_success:
            logger.info("Webhook %s delivered to %s (%s)", event, url, response.status_code)
            return "delivered"
        failure = f"HTTP {response.status_code}"
    except httpx.HTTPError as e:
        failure = f"{type(e).__name__}: {e}"

    logger.warning("Webhook %s to %s failed: %s", event, url, failure)
    if self.request.retries < self.max_retries:
        delay = settings.webhook_retry_delay_seconds * (2**self.request.retries)
        raise self.retry(countdown=delay)

    logger.error("Webhook %s to %s given up after %d retries", event, url, self.max_retries)
    return "failed"
