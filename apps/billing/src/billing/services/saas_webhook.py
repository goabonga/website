# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""SaaS webhook dispatch service.

Sends billing events to registered SaaS applications.

Each event carries a stable identifier (``id``): it is derived from the
Stripe event that caused it, so the same Stripe event always produces the
same identifier, even when Stripe delivers it again or when the delivery is
retried. Receivers can use it to ignore events they already processed.

The body is signed with the webhook secret of the SaaS application
(HMAC-SHA256, hex) and the signature is sent in ``X-Billing-Signature``.
"""

import hashlib
import hmac
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from billing.config import settings
from billing.models import BillingPrice, Customer, SaasApp, Subscription
from billing.schemas.plan import parse_limits

logger = logging.getLogger(__name__)

# Name of the header that carries the signature of the body
SIGNATURE_HEADER = "X-Billing-Signature"

# HTTP statuses worth a new attempt: the receiver is busy or failing, not refusing
RETRYABLE_STATUSES = frozenset({408, 425, 429})

# HTTP client for sending webhooks
_http_client: httpx.AsyncClient | None = None


class WebhookDeliveryError(Exception):
    """A webhook could not be delivered.

    ``retryable`` tells whether a later attempt can succeed (network error,
    timeout, 5xx, 408/425/429) or not (any other refusal of the receiver).
    """

    def __init__(self, message: str, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


def get_http_client() -> httpx.AsyncClient:
    """Get or create HTTP client for webhook dispatch."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=settings.saas_webhook_timeout)
    return _http_client


def sign_payload(payload: str, secret: str) -> str:
    """Sign webhook payload using HMAC-SHA256.

    Args:
        payload: JSON string to sign.
        secret: Webhook secret.

    Returns:
        Hex-encoded signature.
    """
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


async def get_saas_app_by_id(db: AsyncSession, saas_app_id: str) -> SaasApp | None:
    """Get SaaS app by ID."""
    result = await db.execute(select(SaasApp).where(SaasApp.id == saas_app_id))
    return result.scalar_one_or_none()


def build_event_id(
    saas_app_id: str, source_event_id: str, event_type: str, subscription_id: str
) -> str:
    """Derive the identifier of an outgoing event.

    The identifier only depends on the SaaS application, the Stripe event, the
    type of the notification and the subscription, so it is the same every
    time the same Stripe event is processed.
    """
    name = f"urn:billing:event:{saas_app_id}:{source_event_id}:{event_type}:{subscription_id}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, name))


def build_event(
    saas_app: SaasApp,
    event_type: str,
    data: dict[str, Any],
    event_id: str,
) -> dict[str, Any]:
    """Build the envelope of an outgoing event."""
    return {
        "id": event_id,
        "type": event_type,
        "created": datetime.now(UTC).isoformat(),
        "saas_id": saas_app.id,
        "saas_slug": saas_app.slug,
        "data": data,
    }


async def deliver_event(saas_app: SaasApp, event: dict[str, Any]) -> None:
    """Send an event to the webhook URL of a SaaS application, once.

    Raises:
        WebhookDeliveryError: If the receiver cannot be reached or refuses the event.
    """
    if not saas_app.webhook_url:
        raise WebhookDeliveryError("no webhook URL configured", retryable=False)

    payload = json.dumps(event, default=str)

    # Sign payload if secret is configured
    headers = {"Content-Type": "application/json"}
    if saas_app.webhook_secret:
        headers[SIGNATURE_HEADER] = sign_payload(payload, saas_app.webhook_secret)

    try:
        client = get_http_client()
        response = await client.post(
            saas_app.webhook_url,
            content=payload,
            headers=headers,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        raise WebhookDeliveryError(
            f"receiver answered {status_code}",
            retryable=status_code >= 500 or status_code in RETRYABLE_STATUSES,
        ) from e
    except Exception as e:
        raise WebhookDeliveryError(f"{type(e).__name__}: {e}", retryable=True) from e

    logger.info(
        f"Webhook dispatched to {saas_app.slug}: {event['type']} "
        f"(id: {event['id']}, status: {response.status_code})"
    )


async def dispatch_webhook(
    saas_app: SaasApp,
    event_type: str,
    data: dict[str, Any],
    source_event_id: str,
    subscription_id: str,
) -> bool:
    """Dispatch a webhook event to a SaaS application.

    Args:
        saas_app: The SaaS application to notify.
        event_type: Type of event (e.g., "subscription.created").
        data: Event data payload.
        source_event_id: Identifier of the Stripe event that caused the notification.
        subscription_id: Internal identifier of the subscription concerned.

    Returns:
        True if webhook was sent successfully.
    """
    if not saas_app.webhook_url:
        logger.debug(f"SaaS app {saas_app.slug} has no webhook URL configured")
        return False

    event_id = build_event_id(saas_app.id, source_event_id, event_type, subscription_id)
    event = build_event(saas_app, event_type, data, event_id)
    try:
        await deliver_event(saas_app, event)
        return True
    except WebhookDeliveryError as e:
        logger.error(f"Webhook failed for {saas_app.slug}: {event_type} ({event_id}) - {e}")
        return False


async def _load_subscription(db: AsyncSession, subscription_id: str) -> Subscription | None:
    """Load a subscription with its customer, SaaS application, price and product."""
    result = await db.execute(
        select(Subscription)
        .options(
            selectinload(Subscription.customer).selectinload(Customer.saas_app),
            selectinload(Subscription.price).selectinload(BillingPrice.product),
        )
        .where(Subscription.id == subscription_id)
    )
    sub = result.scalar_one_or_none()
    if not sub or not sub.customer:
        return None
    return sub


def build_subscription_data(sub: Subscription) -> dict[str, Any]:
    """Build the ``data`` of a subscription event.

    ``plan_slug`` is the stable identifier of the plan inside the SaaS
    application (``plan_name`` is the display name and can be renamed);
    ``limits`` are the quota limits of the plan, free-form integers defined by
    the SaaS application; ``price_id`` is the internal identifier of the price.
    """
    price = sub.price
    product = price.product if price else None
    return {
        "subscription_id": sub.id,
        "customer_external_id": sub.customer.external_id,
        "status": sub.status.value,
        "plan_name": product.name if product else None,
        "plan_slug": product.slug if product else None,
        "price_id": price.id if price else None,
        "limits": parse_limits((product.extra_data or {}).get("limits")) if product else None,
        "current_period_start": sub.current_period_start,
        "current_period_end": sub.current_period_end,
        "cancel_at_period_end": sub.cancel_at_period_end,
        "canceled_at": sub.canceled_at,
    }


async def _notify(
    db: AsyncSession,
    subscription: Subscription,
    event_type: str,
    source_event_id: str,
) -> bool:
    sub = await _load_subscription(db, subscription.id)
    if sub is None:
        return False
    return await dispatch_webhook(
        sub.customer.saas_app,
        event_type,
        build_subscription_data(sub),
        source_event_id,
        sub.id,
    )


async def notify_subscription_created(
    db: AsyncSession,
    subscription: Subscription,
    source_event_id: str,
) -> bool:
    """Notify SaaS app when a subscription is created.

    Args:
        db: Database session.
        subscription: The created subscription.
        source_event_id: Identifier of the Stripe event that caused the notification.

    Returns:
        True if notification was sent.
    """
    return await _notify(db, subscription, "subscription.created", source_event_id)


async def notify_subscription_updated(
    db: AsyncSession,
    subscription: Subscription,
    source_event_id: str,
) -> bool:
    """Notify SaaS app when a subscription is updated.

    Args:
        db: Database session.
        subscription: The updated subscription.
        source_event_id: Identifier of the Stripe event that caused the notification.

    Returns:
        True if notification was sent.
    """
    return await _notify(db, subscription, "subscription.updated", source_event_id)


async def notify_subscription_deleted(
    db: AsyncSession,
    subscription: Subscription,
    source_event_id: str,
) -> bool:
    """Notify SaaS app when a subscription is deleted/canceled.

    Args:
        db: Database session.
        subscription: The deleted subscription.
        source_event_id: Identifier of the Stripe event that caused the notification.

    Returns:
        True if notification was sent.
    """
    return await _notify(db, subscription, "subscription.deleted", source_event_id)
