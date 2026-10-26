# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Webhook handler routes.

Receives Stripe webhooks, directly from Stripe or through the webhooks proxy
service, and processes the events.

Stripe cannot send an OAuth token: the only authentication of the endpoint is
the signature of the payload, checked with ``STRIPE_WEBHOOK_SECRET``. A
deployment that wants a bearer token on top of it (for example because the
proxy always sends one) sets ``STRIPE_WEBHOOK_REQUIRED_SCOPE``.
"""

import logging
from datetime import UTC, datetime
from typing import Annotated

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from billing.auth.dependencies import AuthContext, oauth2_scheme, require_scopes
from billing.config import settings
from billing.database import async_session_factory
from billing.models import BillingPrice, Customer, SaasApp, Subscription, SubscriptionStatus
from billing.services.saas_webhook import (
    notify_subscription_created,
    notify_subscription_deleted,
    notify_subscription_updated,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


async def get_subscription_by_stripe_id(
    db: AsyncSession, stripe_subscription_id: str
) -> Subscription | None:
    """Get subscription by Stripe subscription ID."""
    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == stripe_subscription_id)
    )
    return result.scalar_one_or_none()


async def get_customer_by_stripe_id(db: AsyncSession, stripe_customer_id: str) -> Customer | None:
    """Get customer by Stripe customer ID."""
    result = await db.execute(
        select(Customer).where(Customer.stripe_customer_id == stripe_customer_id)
    )
    return result.scalar_one_or_none()


async def handle_customer_created(event: dict, db: AsyncSession) -> None:
    """Handle customer.created event.

    Creates a customer record if it doesn't exist.
    Useful for customers created directly in Stripe dashboard.
    """
    stripe_customer = event["data"]["object"]
    stripe_customer_id = stripe_customer["id"]
    email = stripe_customer.get("email")
    name = stripe_customer.get("name")
    metadata = stripe_customer.get("metadata", {})

    # Check if customer already exists
    existing = await get_customer_by_stripe_id(db, stripe_customer_id)
    if existing:
        # If customer was soft-deleted, restore it
        if existing.deleted_at:
            existing.deleted_at = None
            existing.email = email or existing.email
            existing.name = name or existing.name
            logger.info(f"Restored soft-deleted customer: {stripe_customer_id}")
        else:
            logger.debug(f"Customer already exists: {stripe_customer_id}")
        return

    # Get saas_id from metadata
    saas_id = metadata.get("saas_id")
    external_id = metadata.get("external_id")

    if not saas_id or not external_id:
        logger.debug(
            f"Customer {stripe_customer_id} missing saas_id or external_id in metadata, skipping"
        )
        return

    known_saas = await db.execute(select(SaasApp.id).where(SaasApp.id == saas_id))
    if known_saas.first() is None:
        logger.warning(f"Customer {stripe_customer_id} refers to an unknown saas_id, skipping")
        return

    # Create customer record
    customer = Customer(
        saas_app_id=saas_id,
        external_id=external_id,
        stripe_customer_id=stripe_customer_id,
        email=email or "",
        name=name,
    )
    db.add(customer)
    logger.info(f"Created customer from webhook: {stripe_customer_id}")


async def handle_customer_deleted(event: dict, db: AsyncSession) -> None:
    """Handle customer.deleted event.

    Soft-deletes the customer to preserve history.
    """
    stripe_customer = event["data"]["object"]
    stripe_customer_id = stripe_customer["id"]

    customer = await get_customer_by_stripe_id(db, stripe_customer_id)
    if not customer:
        logger.debug(f"Customer not found for deletion: {stripe_customer_id}")
        return

    if customer.deleted_at:
        logger.debug(f"Customer already deleted: {stripe_customer_id}")
        return

    customer.deleted_at = datetime.now(UTC)
    logger.info(f"Soft-deleted customer: {stripe_customer_id} (email: {customer.email})")


async def handle_customer_updated(event: dict, db: AsyncSession) -> None:
    """Handle customer.updated event.

    Syncs customer changes from Stripe.
    """
    stripe_customer = event["data"]["object"]
    stripe_customer_id = stripe_customer["id"]

    customer = await get_customer_by_stripe_id(db, stripe_customer_id)
    if not customer:
        logger.debug(f"Customer not found for update: {stripe_customer_id}")
        return

    # Update customer fields
    if stripe_customer.get("email"):
        customer.email = stripe_customer["email"]
    if stripe_customer.get("name"):
        customer.name = stripe_customer["name"]

    logger.info(f"Updated customer: {stripe_customer_id}")


async def handle_checkout_session_completed(event: dict, db: AsyncSession) -> None:
    """Handle checkout.session.completed event.

    Creates or updates subscription when checkout is completed.
    """
    session = event["data"]["object"]
    saas_id = session.get("metadata", {}).get("saas_id")

    if not saas_id:
        logger.warning("Checkout session missing saas_id in metadata")
        return

    stripe_customer_id = session.get("customer")
    stripe_subscription_id = session.get("subscription")

    if not stripe_subscription_id:
        # One-time payment, not a subscription
        logger.info(f"Checkout completed (one-time payment): {session['id']}")
        return

    customer = await get_customer_by_stripe_id(db, stripe_customer_id)
    if not customer:
        logger.warning(f"Customer not found: {stripe_customer_id}")
        return

    # The session must belong to the tenant of the customer it was paid for
    if str(customer.saas_app_id) != str(saas_id):
        logger.warning(
            f"Checkout session {session['id']} has saas_id {saas_id} but customer "
            f"{stripe_customer_id} belongs to another SaaS app, ignoring"
        )
        return

    # Check if subscription already exists
    subscription = await get_subscription_by_stripe_id(db, stripe_subscription_id)
    if subscription:
        logger.info(f"Subscription already exists: {stripe_subscription_id}")
        return

    # Try to get price from Stripe subscription
    price_id = None
    try:
        stripe_sub = stripe.Subscription.retrieve(stripe_subscription_id)
        if stripe_sub.get("items") and stripe_sub["items"].get("data"):
            stripe_price_id = stripe_sub["items"]["data"][0]["price"]["id"]
            # Look up our price
            result = await db.execute(
                select(BillingPrice).where(BillingPrice.stripe_price_id == stripe_price_id)
            )
            price = result.scalar_one_or_none()
            if price:
                price_id = price.id
    except Exception as e:
        logger.warning(f"Could not fetch subscription details: {e}")

    # Create subscription record
    subscription = Subscription(
        customer_id=customer.id,
        stripe_subscription_id=stripe_subscription_id,
        price_id=price_id,
        status=SubscriptionStatus.ACTIVE,
        extra_data={"checkout_session_id": session["id"]},
    )
    db.add(subscription)
    await db.flush()  # Get the ID

    logger.info(f"Created subscription from checkout: {stripe_subscription_id}")

    # Notify SaaS app
    await notify_subscription_created(db, subscription, event["id"])


async def handle_invoice_paid(event: dict, db: AsyncSession) -> None:
    """Handle invoice.paid event.

    Updates subscription status when invoice is paid.
    """
    invoice = event["data"]["object"]
    stripe_subscription_id = invoice.get("subscription")

    if not stripe_subscription_id:
        return

    subscription = await get_subscription_by_stripe_id(db, stripe_subscription_id)
    if not subscription:
        logger.warning(f"Subscription not found: {stripe_subscription_id}")
        return

    # Update status to active if it was past_due
    if subscription.status in [SubscriptionStatus.PAST_DUE, SubscriptionStatus.UNPAID]:
        subscription.status = SubscriptionStatus.ACTIVE
        logger.info(f"Subscription reactivated: {stripe_subscription_id}")
        # Notify SaaS app of reactivation
        await notify_subscription_updated(db, subscription, event["id"])


async def handle_invoice_payment_failed(event: dict, db: AsyncSession) -> None:
    """Handle invoice.payment_failed event.

    Updates subscription status when payment fails.
    """
    invoice = event["data"]["object"]
    stripe_subscription_id = invoice.get("subscription")

    if not stripe_subscription_id:
        return

    subscription = await get_subscription_by_stripe_id(db, stripe_subscription_id)
    if not subscription:
        logger.warning(f"Subscription not found: {stripe_subscription_id}")
        return

    subscription.status = SubscriptionStatus.PAST_DUE
    logger.warning(f"Subscription payment failed: {stripe_subscription_id}")

    # Notify SaaS app of payment failure
    await notify_subscription_updated(db, subscription, event["id"])


async def handle_subscription_updated(event: dict, db: AsyncSession) -> None:
    """Handle customer.subscription.updated event.

    Syncs subscription changes from Stripe.
    """
    stripe_subscription = event["data"]["object"]
    stripe_subscription_id = stripe_subscription["id"]

    subscription = await get_subscription_by_stripe_id(db, stripe_subscription_id)
    if not subscription:
        logger.warning(f"Subscription not found: {stripe_subscription_id}")
        return

    # Update subscription fields
    subscription.status = SubscriptionStatus(stripe_subscription["status"])
    subscription.cancel_at_period_end = stripe_subscription.get("cancel_at_period_end", False)

    period_source = stripe_subscription
    first_item = None
    if stripe_subscription.get("items") and stripe_subscription["items"].get("data"):
        first_item = stripe_subscription["items"]["data"][0]
    # Recent Stripe API versions carry the billing period on the subscription item
    if not stripe_subscription.get("current_period_start") and first_item:
        period_source = first_item
    if period_source.get("current_period_start"):
        subscription.current_period_start = datetime.fromtimestamp(
            period_source["current_period_start"], tz=UTC
        )
    if period_source.get("current_period_end"):
        subscription.current_period_end = datetime.fromtimestamp(
            period_source["current_period_end"], tz=UTC
        )
    if stripe_subscription.get("canceled_at"):
        subscription.canceled_at = datetime.fromtimestamp(
            stripe_subscription["canceled_at"], tz=UTC
        )

    # Get subscription item ID and price (for metered billing and plan tracking)
    if stripe_subscription.get("items") and stripe_subscription["items"].get("data"):
        item = stripe_subscription["items"]["data"][0]
        subscription.stripe_subscription_item_id = item["id"]

        # Update price if changed
        stripe_price_id = item.get("price", {}).get("id")
        if stripe_price_id:
            result = await db.execute(
                select(BillingPrice).where(BillingPrice.stripe_price_id == stripe_price_id)
            )
            price = result.scalar_one_or_none()
            if price:
                subscription.price_id = price.id

    logger.info(f"Updated subscription: {stripe_subscription_id} -> {subscription.status}")

    # Notify SaaS app
    await notify_subscription_updated(db, subscription, event["id"])


async def handle_subscription_deleted(event: dict, db: AsyncSession) -> None:
    """Handle customer.subscription.deleted event.

    Marks subscription as canceled.
    """
    stripe_subscription = event["data"]["object"]
    stripe_subscription_id = stripe_subscription["id"]

    subscription = await get_subscription_by_stripe_id(db, stripe_subscription_id)
    if not subscription:
        logger.warning(f"Subscription not found: {stripe_subscription_id}")
        return

    subscription.status = SubscriptionStatus.CANCELED
    subscription.canceled_at = datetime.now(UTC)

    logger.info(f"Subscription deleted: {stripe_subscription_id}")

    # Notify SaaS app
    await notify_subscription_deleted(db, subscription, event["id"])


async def stripe_webhook_auth(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
) -> AuthContext | None:
    """Require a bearer token only when ``STRIPE_WEBHOOK_REQUIRED_SCOPE`` is set.

    By default the Stripe signature, checked by the route, is the only
    authentication: Stripe itself cannot send a token. A token that is sent
    anyway (by the webhooks proxy) is not looked at.
    """
    scope = settings.stripe_webhook_required_scope
    if not scope:
        return None
    return await require_scopes(scope)(request=request, token=token)


@router.post("/stripe")
async def handle_stripe_webhook(
    request: Request,
    _auth: Annotated[AuthContext | None, Depends(stripe_webhook_auth)],
) -> dict:
    """Receive and process Stripe webhook events.

    Authenticated by the signature of the payload (``Stripe-Signature`` header,
    ``STRIPE_WEBHOOK_SECRET``); no OAuth token is needed unless
    ``STRIPE_WEBHOOK_REQUIRED_SCOPE`` is set. Processes valid events.
    """
    payload = await request.body()
    signature = request.headers.get("Stripe-Signature", "")

    # Verify webhook signature
    if not settings.stripe_webhook_secret:
        logger.error("STRIPE_WEBHOOK_SECRET not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook secret not configured",
        )

    try:
        event = stripe.Webhook.construct_event(
            payload,
            signature,
            settings.stripe_webhook_secret,
        )
    except stripe.SignatureVerificationError as e:
        logger.warning(f"Invalid Stripe signature: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature",
        )
    except ValueError as e:
        logger.error(f"Invalid payload: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payload",
        )

    event_type = event.get("type")
    event_id = event.get("id")

    logger.info(f"Received Stripe webhook: {event_type} ({event_id})")

    async with async_session_factory() as db:
        try:
            match event_type:
                case "checkout.session.completed":
                    await handle_checkout_session_completed(event, db)
                case "invoice.paid":
                    await handle_invoice_paid(event, db)
                case "invoice.payment_failed":
                    await handle_invoice_payment_failed(event, db)
                case "customer.subscription.updated":
                    await handle_subscription_updated(event, db)
                case "customer.subscription.deleted":
                    await handle_subscription_deleted(event, db)
                case "customer.created":
                    await handle_customer_created(event, db)
                case "customer.updated":
                    await handle_customer_updated(event, db)
                case "customer.deleted":
                    await handle_customer_deleted(event, db)
                case _:
                    logger.debug(f"Unhandled event type: {event_type}")

            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to process webhook: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to process webhook",
            )

    return {"status": "ok"}
