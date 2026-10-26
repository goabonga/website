# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Billing webhook receiver.

Receives subscription events from the billing service and updates tenant plans.
The signature (``X-Billing-Signature``) is mandatory: without ``BILLING_WEBHOOK_SECRET``
nothing is accepted. The plan is identified by its slug, and the event ``id`` makes the
processing idempotent.
"""

import hashlib
import hmac
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.config import get_settings
from knowledge.database import async_session_factory
from knowledge.models import Organization, PlanType
from knowledge.services import event_dedupe

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

EVENT_NAMESPACE = "billing"


class SubscriptionEventData(BaseModel):
    """Subscription event data from billing."""

    subscription_id: str
    customer_external_id: str  # This is the tenant/organization ID
    status: str
    plan_name: str | None = None
    plan_slug: str | None = None
    price_id: str | None = None
    limits: dict[str, int] | None = None
    current_period_start: str | None = None
    current_period_end: str | None = None
    cancel_at_period_end: bool | None = None
    canceled_at: str | None = None


class BillingWebhookEvent(BaseModel):
    """Billing webhook event."""

    id: str
    type: str
    created: str
    saas_id: str | None = None
    saas_slug: str | None = None
    data: dict[str, Any]


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify webhook signature.

    Args:
        payload: Raw request body.
        signature: Signature from X-Billing-Signature header.
        secret: Webhook secret.

    Returns:
        True if signature is valid.
    """
    expected = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def plan_slug_to_plan_type(plan_slug: str | None) -> PlanType | None:
    """Convert the plan slug of billing to a PlanType.

    Args:
        plan_slug: Plan slug from billing (e.g., "starter", "pro"). The slug identifies
            the plan inside the SaaS application; the display name is not used.

    Returns:
        Corresponding PlanType or None if the slug is not a known plan.
    """
    if not plan_slug:
        return None
    try:
        return PlanType(plan_slug)
    except ValueError:
        return None


async def update_tenant_plan(db: AsyncSession, tenant_id: str, plan: PlanType) -> bool:
    """Update tenant's plan.

    Args:
        db: Database session.
        tenant_id: Tenant/Organization ID.
        plan: New plan type.

    Returns:
        True if tenant was found and updated.
    """
    result = await db.execute(select(Organization).where(Organization.id == tenant_id))
    tenant = result.scalar_one_or_none()

    if not tenant:
        logger.warning(f"Tenant not found: {tenant_id}")
        return False

    old_plan = tenant.plan
    tenant.plan = plan
    logger.info(f"Updated tenant {tenant_id} plan: {old_plan.value} -> {plan.value}")
    return True


@router.post("/billing")
async def handle_billing_webhook(request: Request) -> dict:
    """Receive billing webhook events.

    Updates tenant plans based on subscription status changes.
    """
    settings = get_settings()

    # Neither the secret nor the SaaS application may be left unset: there is no default
    if not settings.billing_webhook_secret or not settings.billing_saas_id:
        logger.error("Billing webhook refused: BILLING_WEBHOOK_SECRET or BILLING_SAAS_ID not set")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing webhooks are not configured",
        )

    # Get raw payload for signature verification
    payload = await request.body()

    signature = request.headers.get("X-Billing-Signature", "")
    if not signature:
        logger.warning("Missing X-Billing-Signature header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing signature",
        )

    if not verify_signature(payload, signature, settings.billing_webhook_secret):
        logger.warning("Invalid billing webhook signature")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature",
        )

    # Parse event
    try:
        event = BillingWebhookEvent.model_validate_json(payload)
    except Exception as e:
        logger.error(f"Failed to parse billing webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payload",
        )

    logger.info(f"Received billing webhook: {event.type} ({event.id})")

    # The billing service is shared: only the events of this SaaS application count
    if event.saas_id and event.saas_id != settings.billing_saas_id:
        logger.warning("Billing webhook for another SaaS application: %s", event.saas_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Event is not for this application",
        )

    # Billing resends an event with the same id: process it once
    if await event_dedupe.already_processed(EVENT_NAMESPACE, event.id):
        logger.info("Billing event %s already processed", event.id)
        return {"status": "duplicate"}

    async with async_session_factory() as db:
        try:
            if event.type in ["subscription.created", "subscription.updated"]:
                data = SubscriptionEventData.model_validate(event.data)

                # Determine plan from subscription status and plan slug
                if data.status in ["active", "trialing"]:
                    plan = plan_slug_to_plan_type(data.plan_slug)
                    if plan:
                        await update_tenant_plan(db, data.customer_external_id, plan)
                    else:
                        logger.warning(f"Unknown plan slug: {data.plan_slug}")

                elif data.status in ["canceled", "unpaid", "incomplete_expired"]:
                    # Downgrade to free on cancellation
                    await update_tenant_plan(db, data.customer_external_id, PlanType.FREE)

                elif data.status == "past_due":
                    # Keep current plan but log warning
                    logger.warning(f"Subscription past_due for tenant {data.customer_external_id}")

            elif event.type == "subscription.deleted":
                data = SubscriptionEventData.model_validate(event.data)
                # Downgrade to free when subscription is deleted
                await update_tenant_plan(db, data.customer_external_id, PlanType.FREE)

            else:
                logger.debug(f"Unhandled billing event type: {event.type}")

            await db.commit()

        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to process billing webhook: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to process webhook",
            )

    await event_dedupe.mark_processed(EVENT_NAMESPACE, event.id, settings.billing_event_ttl)
    return {"status": "ok"}
