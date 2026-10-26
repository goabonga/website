# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""SaaS application management routes."""

import logging
import re
from typing import Annotated

import stripe
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from billing.auth import AuthContext, require_scopes
from billing.database import get_db
from billing.models import BillingProduct, SaasApp
from billing.schemas import SaasAppCreate, SaasAppResponse, SaasAppUpdate
from billing.services import get_stripe_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/platform/saas", tags=["Platform - SaaS Apps"])


@router.post("", response_model=SaasAppResponse, status_code=status.HTTP_201_CREATED)
async def create_saas_app(
    data: SaasAppCreate,
    _auth: Annotated[AuthContext, Depends(require_scopes("billing:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SaasApp:
    """Create a new SaaS application."""
    # Check if slug already exists
    result = await db.execute(select(SaasApp).where(SaasApp.slug == data.slug))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"SaaS app with slug '{data.slug}' already exists",
        )

    saas_app = SaasApp(
        name=data.name,
        slug=data.slug,
        description=data.description,
        webhook_url=data.webhook_url,
        webhook_secret=data.webhook_secret,
        branding=data.branding,
        checkout_url_allowlist=data.checkout_url_allowlist,
    )
    db.add(saas_app)
    await db.flush()
    await db.refresh(saas_app)

    logger.info(f"Created SaaS app: {saas_app.slug} ({saas_app.id})")
    return saas_app


@router.get("", response_model=list[SaasAppResponse])
async def list_saas_apps(
    _auth: Annotated[AuthContext, Depends(require_scopes("billing:platform:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    include_inactive: bool = False,
) -> list[SaasApp]:
    """List all SaaS applications."""
    query = select(SaasApp).order_by(SaasApp.created_at.desc())
    if not include_inactive:
        query = query.where(SaasApp.is_active == True)  # noqa: E712

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{saas_id}", response_model=SaasAppResponse)
async def get_saas_app(
    saas_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("billing:platform:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SaasApp:
    """Get a SaaS application by ID."""
    result = await db.execute(select(SaasApp).where(SaasApp.id == saas_id))
    saas_app = result.scalar_one_or_none()
    if not saas_app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SaaS app not found",
        )
    return saas_app


@router.patch("/{saas_id}", response_model=SaasAppResponse)
async def update_saas_app(
    saas_id: str,
    data: SaasAppUpdate,
    _auth: Annotated[AuthContext, Depends(require_scopes("billing:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SaasApp:
    """Update a SaaS application."""
    result = await db.execute(select(SaasApp).where(SaasApp.id == saas_id))
    saas_app = result.scalar_one_or_none()
    if not saas_app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SaaS app not found",
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(saas_app, field, value)

    await db.flush()
    await db.refresh(saas_app)

    logger.info(f"Updated SaaS app: {saas_app.slug} ({saas_app.id})")
    return saas_app


# =============================================================================
# Stripe Sync
# =============================================================================

# Real Stripe IDs pattern: prod_XXXXX or price_XXXXX (alphanumeric after prefix)
STRIPE_PRODUCT_ID_PATTERN = re.compile(r"^prod_[A-Za-z0-9]{14,}$")
STRIPE_PRICE_ID_PATTERN = re.compile(r"^price_[A-Za-z0-9]{14,}$")


class StripeSyncResult(BaseModel):
    """Result of a Stripe sync operation."""

    products_synced: int = 0
    prices_synced: int = 0
    products_skipped: int = 0
    prices_skipped: int = 0
    errors: list[str] = []


def is_placeholder_stripe_id(stripe_id: str, pattern: re.Pattern) -> bool:
    """Check if a Stripe ID is a placeholder (not a real Stripe ID)."""
    return not pattern.match(stripe_id)


@router.post("/{saas_id}/sync-stripe", response_model=StripeSyncResult)
async def sync_saas_to_stripe(
    saas_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("billing:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StripeSyncResult:
    """Sync products and prices to Stripe.

    Creates products and prices on Stripe for records that have placeholder IDs.
    Updates local records with real Stripe IDs.
    """
    # Get SaaS app with products and prices
    result = await db.execute(
        select(SaasApp)
        .where(SaasApp.id == saas_id)
        .options(selectinload(SaasApp.products).selectinload(BillingProduct.prices))
    )
    saas_app = result.scalar_one_or_none()
    if not saas_app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SaaS app not found",
        )

    stripe_service = get_stripe_service()
    sync_result = StripeSyncResult()

    # Sync products
    for product in saas_app.products:
        if not is_placeholder_stripe_id(product.stripe_product_id, STRIPE_PRODUCT_ID_PATTERN):
            sync_result.products_skipped += 1
            continue

        try:
            # Create product on Stripe
            # Note: extra_data contains complex nested objects (features, limits)
            # that can't be sent as Stripe metadata (strings only)
            stripe_product = stripe_service.create_product(
                saas_id=saas_app.id,
                name=product.name,
                description=product.description,
            )

            old_stripe_id = product.stripe_product_id
            product.stripe_product_id = stripe_product.id
            sync_result.products_synced += 1
            logger.info(f"Synced product {product.name}: {old_stripe_id} -> {stripe_product.id}")

            # Sync prices for this product
            for price in product.prices:
                if not is_placeholder_stripe_id(price.stripe_price_id, STRIPE_PRICE_ID_PATTERN):
                    sync_result.prices_skipped += 1
                    continue

                # Skip prices without unit_amount (custom/contact-us pricing)
                if price.unit_amount is None:
                    logger.info(f"Skipping price {price.nickname}: no unit_amount (custom pricing)")
                    sync_result.prices_skipped += 1
                    continue

                try:
                    # Create price on Stripe
                    stripe_price = stripe_service.create_price(
                        saas_id=saas_app.id,
                        stripe_product_id=stripe_product.id,
                        unit_amount=price.unit_amount,
                        currency=price.currency,
                        billing_type=price.billing_type.value,
                        recurring_interval=price.recurring_interval,
                        recurring_interval_count=price.recurring_interval_count,
                        usage_type=price.usage_type.value,
                        nickname=price.nickname,
                    )

                    old_price_id = price.stripe_price_id
                    price.stripe_price_id = stripe_price.id
                    sync_result.prices_synced += 1
                    logger.info(
                        f"Synced price {price.nickname}: {old_price_id} -> {stripe_price.id}"
                    )

                except stripe.StripeError as e:
                    error_msg = f"Failed to sync price {price.nickname}: {e}"
                    logger.error(error_msg)
                    sync_result.errors.append(error_msg)

        except stripe.StripeError as e:
            error_msg = f"Failed to sync product {product.name}: {e}"
            logger.error(error_msg)
            sync_result.errors.append(error_msg)

    await db.flush()

    logger.info(
        f"Stripe sync for {saas_app.slug}: "
        f"{sync_result.products_synced} products, {sync_result.prices_synced} prices synced"
    )

    return sync_result
