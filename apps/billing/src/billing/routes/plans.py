# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Public plans routes for pricing pages."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from billing.database import get_db
from billing.models import BillingProduct, SaasApp
from billing.schemas.plan import (
    PlanFeature,
    PlanLimits,
    PlanPrice,
    PlanResponse,
    PlansResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/plans", tags=["Plans (Public)"])


def parse_limits(raw: object) -> PlanLimits | None:
    """Read the ``limits`` document of a plan.

    The document is a mapping of limit names to integers, whatever the names
    are. Entries that are not integers (``null``, text, booleans) are left
    out: a limit that is absent or ``null`` means the plan declares no limit.

    Returns:
        The limits, or None if the plan has no limits document.
    """
    if not isinstance(raw, dict):
        return None
    limits: PlanLimits = {}
    for name, value in raw.items():
        if isinstance(value, bool) or not isinstance(value, int | float):
            continue
        if isinstance(value, float) and not value.is_integer():
            continue
        limits[str(name)] = int(value)
    return limits


@router.get("/{app_slug}", response_model=PlansResponse)
async def list_plans(
    app_slug: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlansResponse:
    """List all plans for a SaaS application.

    This is a public endpoint for pricing pages. Returns active products
    with their prices and metadata (features, limits).

    No authentication required.
    """
    # Find the SaaS app by slug
    result = await db.execute(
        select(SaasApp).where(SaasApp.slug == app_slug, SaasApp.is_active == True)  # noqa: E712
    )
    saas_app = result.scalar_one_or_none()

    if not saas_app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"App '{app_slug}' not found",
        )

    # Get all active products with their prices
    products_result = await db.execute(
        select(BillingProduct)
        .where(
            BillingProduct.saas_app_id == saas_app.id,
            BillingProduct.is_active == True,  # noqa: E712
        )
        .options(selectinload(BillingProduct.prices))
        .order_by(BillingProduct.created_at)
    )
    products = products_result.scalars().all()

    plans = []
    for product in products:
        # Extract metadata from extra_data
        metadata = product.extra_data or {}

        # Parse features from metadata
        features = []
        for feat in metadata.get("features", []):
            if isinstance(feat, dict):
                features.append(
                    PlanFeature(
                        label=feat.get("label", ""),
                        highlight=feat.get("highlight", False),
                        disabled=feat.get("disabled", False),
                    )
                )
            elif isinstance(feat, str):
                features.append(PlanFeature(label=feat))

        # Limits are free-form integers defined by the SaaS application
        limits = parse_limits(metadata.get("limits"))

        # Get active prices
        prices = []
        for price in product.prices:
            if price.is_active:
                prices.append(
                    PlanPrice(
                        id=price.id,
                        currency=price.currency,
                        unit_amount=price.unit_amount,
                        billing_type=price.billing_type,
                        interval=price.recurring_interval,
                        interval_count=price.recurring_interval_count,
                    )
                )

        # Sort prices by unit_amount (cheaper first, free/None first)
        prices.sort(key=lambda p: p.unit_amount or 0)

        plan = PlanResponse(
            id=product.id,
            slug=product.slug,
            name=product.name,
            description=product.description,
            features=features,
            limits=limits,
            prices=prices,
            is_recommended=metadata.get("is_recommended", False),
            sort_order=metadata.get("sort_order", 0),
            created_at=product.created_at,
        )
        plans.append(plan)

    # Sort by sort_order
    plans.sort(key=lambda p: p.sort_order)

    return PlansResponse(app_slug=app_slug, plans=plans)
