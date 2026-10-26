# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Checkout session routes."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from billing.auth import AuthContext, require_scopes
from billing.database import get_db
from billing.models import BillingPrice, BillingProduct, Customer, SaasApp
from billing.partition import Guard
from billing.schemas import CheckoutSessionCreate, CheckoutSessionResponse
from billing.services import get_stripe_service
from billing.services.redirects import RedirectNotAllowed, ensure_allowed_redirect

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/checkout", tags=["Checkout"])


@router.post("/session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    data: CheckoutSessionCreate,
    auth: Annotated[AuthContext, Depends(require_scopes("billing:checkout:write"))],
    guard: Guard,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CheckoutSessionResponse:
    """Create a Stripe Checkout Session.

    This endpoint creates a checkout session for a customer to complete payment.
    The customer can be identified by either customer_id (internal) or external_id.
    The client must be bound to ``saas_id`` (or hold the admin scope).
    The customer and the price must both belong to ``saas_id``; the success and
    cancel URLs must be covered by the SaaS app's ``checkout_url_allowlist``.
    The ``saas_id`` metadata of the session is set by the server and cannot be
    overridden through ``metadata``.
    """
    # The client must be bound to the SaaS app it creates a session for
    await guard.authorize(auth, data.saas_id, db)

    # Verify SaaS app exists
    result = await db.execute(select(SaasApp).where(SaasApp.id == data.saas_id))
    saas_app = result.scalar_one_or_none()
    if not saas_app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SaaS app not found",
        )

    # Redirect targets are chosen by the caller: they must be allowed for this SaaS app
    for field, url in (("success_url", data.success_url), ("cancel_url", data.cancel_url)):
        try:
            ensure_allowed_redirect(saas_app, str(url), field)
        except RedirectNotAllowed as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Get customer by ID or external_id
    customer: Customer | None = None
    stripe_service = get_stripe_service()

    if data.customer_id:
        cust_result = await db.execute(
            select(Customer).where(
                Customer.id == data.customer_id,
                Customer.saas_app_id == data.saas_id,
                Customer.deleted_at.is_(None),  # Exclude soft-deleted
            )
        )
        customer = cust_result.scalar_one_or_none()
    elif data.external_id:
        cust_result = await db.execute(
            select(Customer).where(
                Customer.external_id == data.external_id,
                Customer.saas_app_id == data.saas_id,
                Customer.deleted_at.is_(None),  # Exclude soft-deleted
            )
        )
        customer = cust_result.scalar_one_or_none()

        # Auto-create customer if not found and email is provided
        if not customer and data.customer_email:
            logger.info(
                f"Auto-creating customer: external_id={data.external_id}, "
                f"email={data.customer_email}"
            )
            # Create in Stripe first
            stripe_customer = stripe_service.create_customer(
                saas_id=str(data.saas_id),
                email=data.customer_email,
                name=data.customer_name,
                external_id=data.external_id,
            )
            # Create in local database
            customer = Customer(
                saas_app_id=data.saas_id,
                external_id=data.external_id,
                stripe_customer_id=stripe_customer.id,
                email=data.customer_email,
                name=data.customer_name,
            )
            db.add(customer)
            await db.flush()
            logger.info(f"Created customer: id={customer.id}, stripe_id={stripe_customer.id}")

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found. Provide customer_id, external_id, or external_id with customer_email.",
        )

    # Get price: it must be an active price of a product of the same SaaS app, a price of
    # another tenant is reported as unknown
    price_result = await db.execute(
        select(BillingPrice)
        .join(BillingProduct, BillingPrice.product_id == BillingProduct.id)
        .where(
            BillingPrice.id == data.price_id,
            BillingPrice.is_active == True,  # noqa: E712
            BillingProduct.saas_app_id == data.saas_id,
        )
    )
    price = price_result.scalar_one_or_none()
    if not price:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Price not found",
        )

    # The branding of the SaaS app customizes the hosted page
    branding = saas_app.branding if isinstance(saas_app.branding, dict) else {}
    locale = branding.get("locale")
    custom_text = branding.get("custom_text")

    # Create checkout session in Stripe
    session = stripe_service.create_checkout_session(
        saas_id=data.saas_id,
        stripe_customer_id=customer.stripe_customer_id,
        stripe_price_id=price.stripe_price_id,
        success_url=str(data.success_url),
        cancel_url=str(data.cancel_url),
        mode=data.mode,
        quantity=data.quantity,
        trial_period_days=data.trial_period_days,
        metadata=data.metadata,
        locale=locale if isinstance(locale, str) else None,
        custom_text=custom_text if isinstance(custom_text, dict) else None,
    )

    logger.info(
        f"Created checkout session: {session.id} for customer {customer.email} "
        f"(SaaS: {saas_app.slug})"
    )

    return CheckoutSessionResponse(
        session_id=session.id,
        url=session.url or "",
    )
