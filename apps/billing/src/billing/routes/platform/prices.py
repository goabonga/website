# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Price management routes."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from billing.auth import AuthContext, require_scopes
from billing.config import settings
from billing.database import get_db
from billing.models import BillingPrice, BillingProduct, BillingType, SaasApp
from billing.schemas import PriceCreate, PriceResponse, PriceUpdate
from billing.services import get_stripe_service

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/platform/{saas_id}/products/{product_id}/prices",
    tags=["Platform - Prices"],
)


async def get_product_or_404(saas_id: str, product_id: str, db: AsyncSession) -> BillingProduct:
    """Get product or raise 404."""
    # Verify SaaS app exists
    saas_result = await db.execute(select(SaasApp).where(SaasApp.id == saas_id))
    if not saas_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SaaS app not found",
        )

    # Get product
    product_result = await db.execute(
        select(BillingProduct).where(
            BillingProduct.id == product_id,
            BillingProduct.saas_app_id == saas_id,
        )
    )
    product = product_result.scalar_one_or_none()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )
    return product


@router.post("", response_model=PriceResponse, status_code=status.HTTP_201_CREATED)
async def create_price(
    saas_id: str,
    product_id: str,
    data: PriceCreate,
    _auth: Annotated[AuthContext, Depends(require_scopes("billing:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BillingPrice:
    """Create a new price for a product (syncs to Stripe)."""
    product = await get_product_or_404(saas_id, product_id, db)
    stripe_service = get_stripe_service()

    # A recurring price always has an interval: the configured default fills the gap,
    # and the same value is sent to Stripe and stored locally.
    recurring_interval = data.recurring_interval
    if data.billing_type == BillingType.RECURRING and recurring_interval is None:
        recurring_interval = settings.default_recurring_interval

    # Create price in Stripe
    stripe_price = stripe_service.create_price(
        saas_id=saas_id,
        stripe_product_id=product.stripe_product_id,
        unit_amount=data.unit_amount,
        currency=data.currency,
        billing_type=data.billing_type.value,
        recurring_interval=recurring_interval,
        recurring_interval_count=data.recurring_interval_count,
        usage_type=data.usage_type.value,
        nickname=data.nickname,
    )

    # Create local price record
    price = BillingPrice(
        product_id=product.id,
        stripe_price_id=stripe_price.id,
        nickname=data.nickname,
        currency=data.currency,
        unit_amount=data.unit_amount,
        billing_type=data.billing_type,
        recurring_interval=recurring_interval,
        recurring_interval_count=data.recurring_interval_count,
        usage_type=data.usage_type,
    )
    db.add(price)
    await db.flush()
    await db.refresh(price)

    logger.info(f"Created price: {price.nickname or price.id} for product {product.name}")
    return price


@router.get("", response_model=list[PriceResponse])
async def list_prices(
    saas_id: str,
    product_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("billing:platform:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    include_inactive: bool = False,
) -> list[BillingPrice]:
    """List all prices for a product."""
    await get_product_or_404(saas_id, product_id, db)

    query = select(BillingPrice).where(BillingPrice.product_id == product_id)
    if not include_inactive:
        query = query.where(BillingPrice.is_active == True)  # noqa: E712
    query = query.order_by(BillingPrice.created_at.desc())

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{price_id}", response_model=PriceResponse)
async def get_price(
    saas_id: str,
    product_id: str,
    price_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("billing:platform:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BillingPrice:
    """Get a price by ID."""
    await get_product_or_404(saas_id, product_id, db)

    result = await db.execute(
        select(BillingPrice).where(
            BillingPrice.id == price_id,
            BillingPrice.product_id == product_id,
        )
    )
    price = result.scalar_one_or_none()
    if not price:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Price not found",
        )
    return price


@router.patch("/{price_id}", response_model=PriceResponse)
async def update_price(
    saas_id: str,
    product_id: str,
    price_id: str,
    data: PriceUpdate,
    _auth: Annotated[AuthContext, Depends(require_scopes("billing:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BillingPrice:
    """Update a price (limited fields - Stripe prices are mostly immutable)."""
    await get_product_or_404(saas_id, product_id, db)

    result = await db.execute(
        select(BillingPrice).where(
            BillingPrice.id == price_id,
            BillingPrice.product_id == product_id,
        )
    )
    price = result.scalar_one_or_none()
    if not price:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Price not found",
        )

    stripe_service = get_stripe_service()

    # Update in Stripe (best effort - price may not exist in Stripe)
    try:
        stripe_service.update_price(
            stripe_price_id=price.stripe_price_id,
            nickname=data.nickname,
            active=data.is_active,
        )
    except Exception as e:
        logger.warning(f"Failed to update price in Stripe: {e}. Updating local record only.")

    # Update local record
    if data.nickname is not None:
        price.nickname = data.nickname
    if data.is_active is not None:
        price.is_active = data.is_active

    await db.flush()
    await db.refresh(price)

    logger.info(f"Updated price: {price.id} (is_active={price.is_active})")
    return price
