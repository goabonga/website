# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Subscription management routes."""

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from billing.auth import AuthContext, require_scopes
from billing.config import settings
from billing.database import get_db
from billing.models import (
    BillingPrice,
    Customer,
    SaasApp,
    Subscription,
    SubscriptionStatus,
)
from billing.schemas import SubscriptionCreate, SubscriptionResponse, SubscriptionUpdate
from billing.schemas.subscription import (
    ProrationBehavior,
    ProrationLineItem,
    SubscriptionCancelRequest,
    SubscriptionUpgradePreview,
    SubscriptionUpgradeRequest,
    SubscriptionUpgradeResponse,
)
from billing.services import get_stripe_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/platform/{saas_id}", tags=["Platform - Subscriptions"])


async def get_saas_app_or_404(saas_id: str, db: AsyncSession) -> SaasApp:
    """Get SaaS app or raise 404."""
    result = await db.execute(select(SaasApp).where(SaasApp.id == saas_id))
    saas_app = result.scalar_one_or_none()
    if not saas_app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SaaS app not found",
        )
    return saas_app


@router.get("/subscriptions", response_model=list[SubscriptionResponse])
async def list_subscriptions(
    saas_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("billing:platform:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: SubscriptionStatus | None = None,
    limit: int = Query(settings.list_default_limit, ge=1, le=settings.list_max_limit),
    offset: int = Query(0, ge=0),
) -> list[Subscription]:
    """List all subscriptions for a SaaS app."""
    await get_saas_app_or_404(saas_id, db)

    # Join with customers to filter by saas_app_id
    query = select(Subscription).join(Customer).where(Customer.saas_app_id == saas_id)

    if status_filter:
        query = query.where(Subscription.status == status_filter)

    query = query.order_by(Subscription.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/customers/{customer_id}/subscriptions", response_model=list[SubscriptionResponse])
async def list_customer_subscriptions(
    saas_id: str,
    customer_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("billing:platform:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Subscription]:
    """List all subscriptions for a customer."""
    await get_saas_app_or_404(saas_id, db)

    # Verify customer belongs to SaaS app
    cust_result = await db.execute(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.saas_app_id == saas_id,
        )
    )
    if not cust_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    query = (
        select(Subscription)
        .where(Subscription.customer_id == customer_id)
        .order_by(Subscription.created_at.desc())
    )

    subs_result = await db.execute(query)
    return list(subs_result.scalars().all())


@router.get("/external/{external_id}/subscription", response_model=SubscriptionResponse | None)
async def get_subscription_by_external_id(
    saas_id: str,
    external_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("billing:platform:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Subscription | None:
    """Get the active subscription for a customer by external_id.

    Returns the most recent active subscription for the customer identified
    by their external_id (e.g., tenant/organization ID).
    """
    await get_saas_app_or_404(saas_id, db)

    # Find customer by external_id
    cust_result = await db.execute(
        select(Customer).where(
            Customer.saas_app_id == saas_id,
            Customer.external_id == external_id,
        )
    )
    customer = cust_result.scalar_one_or_none()
    if not customer:
        return None

    # Get active subscription
    sub_result = await db.execute(
        select(Subscription)
        .where(
            Subscription.customer_id == customer.id,
            Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]),
        )
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    return sub_result.scalar_one_or_none()


@router.get("/subscriptions/{subscription_id}", response_model=SubscriptionResponse)
async def get_subscription(
    saas_id: str,
    subscription_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("billing:platform:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Subscription:
    """Get a subscription by ID."""
    await get_saas_app_or_404(saas_id, db)

    # Get subscription with customer to verify saas_app_id
    result = await db.execute(
        select(Subscription)
        .join(Customer)
        .where(
            Subscription.id == subscription_id,
            Customer.saas_app_id == saas_id,
        )
    )
    subscription = result.scalar_one_or_none()
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )
    return subscription


@router.post(
    "/customers/{customer_id}/subscriptions",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_subscription(
    saas_id: str,
    customer_id: str,
    data: SubscriptionCreate,
    _auth: Annotated[AuthContext, Depends(require_scopes("billing:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Subscription:
    """Create a new subscription for a customer (syncs to Stripe)."""
    await get_saas_app_or_404(saas_id, db)

    # Get customer
    cust_result = await db.execute(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.saas_app_id == saas_id,
        )
    )
    customer = cust_result.scalar_one_or_none()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    # Get price
    price_result = await db.execute(select(BillingPrice).where(BillingPrice.id == data.price_id))
    price = price_result.scalar_one_or_none()
    if not price:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Price not found",
        )

    stripe_service = get_stripe_service()

    # Create subscription in Stripe
    stripe_subscription = stripe_service.create_subscription(
        saas_id=saas_id,
        stripe_customer_id=customer.stripe_customer_id,
        stripe_price_id=price.stripe_price_id,
        trial_period_days=data.trial_period_days,
        metadata=data.extra_data,
    )

    # Get subscription item ID (for metered billing)
    stripe_item_id = None
    if stripe_subscription.items and stripe_subscription.items.data:
        stripe_item_id = stripe_subscription.items.data[0].id

    # Create local subscription record
    # Use bracket notation for current_period_* (Stripe SDK types may not expose them)
    period_start = stripe_subscription.get("current_period_start")
    period_end = stripe_subscription.get("current_period_end")

    subscription = Subscription(
        customer_id=customer.id,
        price_id=price.id,
        stripe_subscription_id=stripe_subscription.id,
        stripe_subscription_item_id=stripe_item_id,
        status=SubscriptionStatus(stripe_subscription.status),
        current_period_start=(
            datetime.fromtimestamp(period_start, tz=UTC) if period_start else None
        ),
        current_period_end=(datetime.fromtimestamp(period_end, tz=UTC) if period_end else None),
        extra_data=data.extra_data,
    )
    db.add(subscription)
    await db.flush()
    await db.refresh(subscription)

    logger.info(f"Created subscription: {subscription.id} for customer {customer.email}")
    return subscription


@router.patch("/subscriptions/{subscription_id}", response_model=SubscriptionResponse)
async def update_subscription(
    saas_id: str,
    subscription_id: str,
    data: SubscriptionUpdate,
    _auth: Annotated[AuthContext, Depends(require_scopes("billing:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Subscription:
    """Update a subscription (syncs to Stripe)."""
    await get_saas_app_or_404(saas_id, db)

    # Get subscription with customer to verify saas_app_id
    result = await db.execute(
        select(Subscription)
        .join(Customer)
        .where(
            Subscription.id == subscription_id,
            Customer.saas_app_id == saas_id,
        )
    )
    subscription = result.scalar_one_or_none()
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )

    stripe_service = get_stripe_service()
    update_data = data.model_dump(exclude_unset=True)

    # Update in Stripe
    stripe_service.update_subscription(
        stripe_subscription_id=subscription.stripe_subscription_id,
        cancel_at_period_end=update_data.get("cancel_at_period_end"),
        metadata=update_data.get("extra_data"),
    )

    # Update local record
    for field, value in update_data.items():
        setattr(subscription, field, value)

    await db.flush()
    await db.refresh(subscription)

    logger.info(f"Updated subscription: {subscription.id}")
    return subscription


@router.delete("/subscriptions/{subscription_id}", response_model=SubscriptionResponse)
async def cancel_subscription(
    saas_id: str,
    subscription_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("billing:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    immediately: bool = False,
) -> Subscription:
    """Cancel a subscription (syncs to Stripe)."""
    await get_saas_app_or_404(saas_id, db)

    # Get subscription with customer to verify saas_app_id
    result = await db.execute(
        select(Subscription)
        .join(Customer)
        .where(
            Subscription.id == subscription_id,
            Customer.saas_app_id == saas_id,
        )
    )
    subscription = result.scalar_one_or_none()
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )

    stripe_service = get_stripe_service()

    # Cancel in Stripe
    stripe_subscription = stripe_service.cancel_subscription(
        stripe_subscription_id=subscription.stripe_subscription_id,
        immediately=immediately,
    )

    # Update local record
    subscription.status = SubscriptionStatus(stripe_subscription.status)
    subscription.cancel_at_period_end = stripe_subscription.cancel_at_period_end
    if immediately:
        subscription.canceled_at = datetime.now(UTC)

    await db.flush()
    await db.refresh(subscription)

    logger.info(f"Canceled subscription: {subscription.id} (immediately={immediately})")
    return subscription


@router.post("/subscriptions/{subscription_id}/sync", response_model=SubscriptionResponse)
async def sync_subscription(
    saas_id: str,
    subscription_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("billing:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Subscription:
    """Sync subscription data from Stripe."""
    await get_saas_app_or_404(saas_id, db)

    # Get subscription with customer to verify saas_app_id
    result = await db.execute(
        select(Subscription)
        .join(Customer)
        .where(
            Subscription.id == subscription_id,
            Customer.saas_app_id == saas_id,
        )
    )
    subscription = result.scalar_one_or_none()
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )

    stripe_service = get_stripe_service()

    # Fetch from Stripe
    try:
        stripe_subscription = stripe_service.get_subscription(subscription.stripe_subscription_id)
    except Exception as e:
        logger.warning(f"Failed to fetch subscription from Stripe: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch subscription from Stripe: {e}",
        )

    # Update local record with Stripe data
    subscription.status = SubscriptionStatus(stripe_subscription.status)
    subscription.cancel_at_period_end = stripe_subscription.cancel_at_period_end or False

    # Get period info from subscription items (Stripe API 2026+ structure)
    # Period info is in items.data[0], not at subscription root level
    # Note: Must use bracket notation for "items" to avoid conflict with dict .items() method
    current_period_start = None
    current_period_end = None

    try:
        items_obj = stripe_subscription["items"]
        if items_obj and items_obj.data:
            item = items_obj.data[0]
            current_period_start = item["current_period_start"]
            current_period_end = item["current_period_end"]
            subscription.stripe_subscription_item_id = item["id"]
            logger.debug(
                f"Got period from item: start={current_period_start}, end={current_period_end}"
            )
    except (AttributeError, TypeError, KeyError) as e:
        logger.warning(f"Could not get period from subscription items: {e}")

    if current_period_start:
        subscription.current_period_start = datetime.fromtimestamp(current_period_start, tz=UTC)

    if current_period_end:
        subscription.current_period_end = datetime.fromtimestamp(current_period_end, tz=UTC)

    if stripe_subscription.canceled_at:
        subscription.canceled_at = datetime.fromtimestamp(stripe_subscription.canceled_at, tz=UTC)

    await db.flush()
    await db.refresh(subscription)

    logger.info(f"Synced subscription from Stripe: {subscription.id}")
    return subscription


async def _get_subscription_with_price(
    saas_id: str,
    subscription_id: str,
    db: AsyncSession,
) -> Subscription:
    """Get subscription with price and product loaded, verifying saas_id ownership."""
    result = await db.execute(
        select(Subscription)
        .join(Customer)
        .options(selectinload(Subscription.price).selectinload(BillingPrice.product))
        .where(
            Subscription.id == subscription_id,
            Customer.saas_app_id == saas_id,
        )
    )
    subscription = result.scalar_one_or_none()
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )
    return subscription


@router.post(
    "/subscriptions/{subscription_id}/upgrade/preview",
    response_model=SubscriptionUpgradePreview,
)
async def preview_subscription_upgrade(
    saas_id: str,
    subscription_id: str,
    data: SubscriptionUpgradeRequest,
    _auth: Annotated[AuthContext, Depends(require_scopes("billing:platform:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SubscriptionUpgradePreview:
    """Preview proration costs for upgrading a subscription.

    Returns a detailed breakdown of:
    - Credit from unused time on current plan
    - Charge for remaining time on new plan
    - Total amount due

    This is a preview only - no changes are made.
    """
    await get_saas_app_or_404(saas_id, db)

    # Get subscription with current price and product
    subscription = await _get_subscription_with_price(saas_id, subscription_id, db)

    # Verify subscription is active
    if subscription.status not in [
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.TRIALING,
    ]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot upgrade subscription with status: {subscription.status.value}",
        )

    # Get new price with product
    result = await db.execute(
        select(BillingPrice)
        .options(selectinload(BillingPrice.product))
        .where(BillingPrice.id == data.new_price_id)
    )
    new_price = result.scalar_one_or_none()
    if not new_price:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="New price not found",
        )

    # Verify new price belongs to same saas_app
    if new_price.product.saas_app_id != saas_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Price does not belong to this SaaS app",
        )

    # Check if upgrading to same price
    if subscription.price_id == data.new_price_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already subscribed to this plan",
        )

    stripe_service = get_stripe_service()

    try:
        # Get proration preview from Stripe
        upcoming_invoice = stripe_service.preview_subscription_upgrade(
            stripe_subscription_id=subscription.stripe_subscription_id,
            new_stripe_price_id=new_price.stripe_price_id,
        )
    except Exception as e:
        logger.error(f"Failed to preview upgrade: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to preview upgrade from Stripe: {e}",
        )

    # Parse line items - only include proration items, not the next billing cycle
    line_items = []
    credit_applied = 0
    proration_total = 0

    for item in upcoming_invoice.lines.data:
        # Only include proration line items (not the regular subscription charge)
        # In Stripe SDK v7+, use bracket notation to access proration attribute
        # Also check description for proration patterns as fallback
        is_proration = item.get("proration", False)
        description = item.get("description", "") or ""

        # Fallback: detect proration by description patterns
        # Proration items have descriptions like "Unused time on X" or "Remaining time on X"
        if not is_proration:
            is_proration = (
                "Unused time" in description
                or "Remaining time" in description
                or "unused portion" in description.lower()
            )

        if is_proration:
            line_items.append(
                ProrationLineItem(
                    description=description or "Proration adjustment",
                    amount=item.amount,
                    currency=item.currency,
                )
            )
            proration_total += item.amount
            # Track credits (negative amounts)
            if item.amount < 0:
                credit_applied += abs(item.amount)

    # Build response
    current_price = subscription.price
    current_plan_name = (
        current_price.product.name if current_price and current_price.product else "Unknown"
    )
    new_plan_name = new_price.product.name if new_price.product else "Unknown"

    return SubscriptionUpgradePreview(
        current_plan_name=current_plan_name,
        new_plan_name=new_plan_name,
        current_price_amount=current_price.unit_amount or 0 if current_price else 0,
        new_price_amount=new_price.unit_amount or 0,
        proration_date=datetime.now(UTC),
        period_end=subscription.current_period_end or datetime.now(UTC),
        line_items=line_items,
        # Use proration_total instead of full invoice total to show only the upgrade cost
        subtotal=proration_total,
        total=proration_total,
        credit_applied=credit_applied,
        currency=upcoming_invoice.currency,
    )


@router.post(
    "/subscriptions/{subscription_id}/upgrade",
    response_model=SubscriptionUpgradeResponse,
)
async def upgrade_subscription(
    saas_id: str,
    subscription_id: str,
    data: SubscriptionUpgradeRequest,
    _auth: Annotated[AuthContext, Depends(require_scopes("billing:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SubscriptionUpgradeResponse:
    """Upgrade a subscription to a new plan with proration.

    Proration behavior options:
    - create_prorations: Credit applied to next invoice (default, recommended)
    - always_invoice: Create and pay an invoice immediately
    - none: No proration (not recommended for upgrades)
    """
    await get_saas_app_or_404(saas_id, db)

    # Get subscription with current price
    subscription = await _get_subscription_with_price(saas_id, subscription_id, db)

    # Verify subscription is active
    if subscription.status not in [
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.TRIALING,
    ]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot upgrade subscription with status: {subscription.status.value}",
        )

    # Get new price
    result = await db.execute(
        select(BillingPrice)
        .options(selectinload(BillingPrice.product))
        .where(BillingPrice.id == data.new_price_id)
    )
    new_price = result.scalar_one_or_none()
    if not new_price:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="New price not found",
        )

    # Verify new price belongs to same saas_app
    if new_price.product.saas_app_id != saas_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Price does not belong to this SaaS app",
        )

    # Check if upgrading to same price
    if subscription.price_id == data.new_price_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already subscribed to this plan",
        )

    stripe_service = get_stripe_service()

    try:
        # Perform the upgrade
        stripe_sub, invoice = stripe_service.upgrade_subscription(
            stripe_subscription_id=subscription.stripe_subscription_id,
            new_stripe_price_id=new_price.stripe_price_id,
            proration_behavior=data.proration_behavior.value,
        )
    except Exception as e:
        logger.error(f"Failed to upgrade subscription: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to upgrade subscription in Stripe: {e}",
        )

    # Update local subscription record
    subscription.price_id = new_price.id
    subscription.status = SubscriptionStatus(stripe_sub.status)

    # Update subscription item ID if changed
    if stripe_sub.items and stripe_sub.items.data:
        subscription.stripe_subscription_item_id = stripe_sub.items.data[0].id

    await db.flush()
    await db.refresh(subscription)

    # Determine amount due
    amount_due = 0
    invoice_id = None
    if invoice:
        amount_due = invoice.amount_due
        invoice_id = invoice.id

    logger.info(
        f"Upgraded subscription {subscription.id} to price {new_price.id} "
        f"(proration: {data.proration_behavior.value})"
    )

    return SubscriptionUpgradeResponse(
        subscription=SubscriptionResponse.model_validate(subscription),
        proration_applied=data.proration_behavior != ProrationBehavior.NONE,
        amount_due=amount_due,
        invoice_id=invoice_id,
    )


# =============================================================================
# Cancel / reactivate actions
# =============================================================================

# Statuses from which a subscription can never come back: a new one must be created.
_FINAL_STATUSES = (SubscriptionStatus.CANCELED, SubscriptionStatus.INCOMPLETE_EXPIRED)


async def _get_tenant_subscription(
    saas_id: str, subscription_id: str, db: AsyncSession
) -> Subscription:
    """Load a subscription through its customer so that another tenant's one is a 404."""
    await get_saas_app_or_404(saas_id, db)
    result = await db.execute(
        select(Subscription)
        .join(Customer)
        .where(
            Subscription.id == subscription_id,
            Customer.saas_app_id == saas_id,
        )
    )
    subscription = result.scalar_one_or_none()
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )
    return subscription


@router.post("/subscriptions/{subscription_id}/cancel", response_model=SubscriptionResponse)
async def cancel_subscription_action(
    saas_id: str,
    subscription_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("billing:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    data: SubscriptionCancelRequest | None = None,
) -> Subscription:
    """Cancel a subscription, at the end of the paid period by default.

    With ``cancel_at_period_end`` true (the default) Stripe stops renewing the
    subscription but keeps it ``active`` until the period ends; the local
    record only gets ``cancel_at_period_end=true`` and the final ``canceled``
    status arrives later through the Stripe webhook. With ``false`` the
    subscription is canceled immediately. Repeating the call is harmless.
    A subscription that is already canceled gives ``409``.
    """
    subscription = await _get_tenant_subscription(saas_id, subscription_id, db)
    if subscription.status in _FINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Subscription is already {subscription.status.value}",
        )

    at_period_end = data.cancel_at_period_end if data else True
    stripe_service = get_stripe_service()
    try:
        stripe_subscription = stripe_service.cancel_subscription(
            stripe_subscription_id=subscription.stripe_subscription_id,
            immediately=not at_period_end,
        )
    except Exception as e:
        logger.warning(f"Failed to cancel subscription in Stripe: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to cancel subscription in Stripe: {e}",
        )

    subscription.status = SubscriptionStatus(stripe_subscription.status)
    subscription.cancel_at_period_end = bool(stripe_subscription.cancel_at_period_end)
    if not at_period_end:
        subscription.canceled_at = datetime.now(UTC)

    await db.flush()
    await db.refresh(subscription)

    logger.info(f"Canceled subscription: {subscription.id} (at_period_end={at_period_end})")
    return subscription


@router.post("/subscriptions/{subscription_id}/reactivate", response_model=SubscriptionResponse)
async def reactivate_subscription_action(
    saas_id: str,
    subscription_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("billing:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Subscription:
    """Undo a cancellation scheduled for the end of the period.

    Only a subscription that is still running can be reactivated: it stops
    being scheduled for cancellation and keeps renewing. A subscription that
    is already ``canceled`` (or ``incomplete_expired``) cannot come back, a
    new checkout is needed: ``409``. Reactivating a subscription that is not
    scheduled for cancellation changes nothing and answers ``200``.
    """
    subscription = await _get_tenant_subscription(saas_id, subscription_id, db)
    if subscription.status in _FINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Subscription is {subscription.status.value} and cannot be reactivated, "
            "create a new subscription",
        )

    if subscription.cancel_at_period_end:
        stripe_service = get_stripe_service()
        try:
            stripe_subscription = stripe_service.update_subscription(
                stripe_subscription_id=subscription.stripe_subscription_id,
                cancel_at_period_end=False,
            )
        except Exception as e:
            logger.warning(f"Failed to reactivate subscription in Stripe: {e}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to reactivate subscription in Stripe: {e}",
            )
        subscription.cancel_at_period_end = bool(stripe_subscription.cancel_at_period_end)
        subscription.status = SubscriptionStatus(stripe_subscription.status)

        await db.flush()
        await db.refresh(subscription)
        logger.info(f"Reactivated subscription: {subscription.id}")

    return subscription
