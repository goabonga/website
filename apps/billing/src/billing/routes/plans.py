# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Public plans routes for pricing pages."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from billing.auth import AuthContext, require_scopes
from billing.auth.dependencies import oauth2_scheme
from billing.config import settings
from billing.database import get_db
from billing.models import BillingProduct, SaasApp
from billing.partition import Guard
from billing.schemas.plan import (
    PlanFeature,
    PlanPrice,
    PlanResponse,
    PlansResponse,
    parse_limits,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/plans", tags=["Plans (Public)"])


async def plans_auth(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
) -> AuthContext | None:
    """Authenticate the caller of the plans, unless ``PLANS_PUBLIC`` is enabled.

    The scope is ``billing:platform:read``; the binding to the SaaS app is
    checked by the route once the application is known.
    """
    if settings.plans_public:
        return None
    return await require_scopes("billing:platform:read")(request=request, token=token)


@router.get("/{app_slug}", response_model=PlansResponse)
async def list_plans(
    app_slug: str,
    auth: Annotated[AuthContext | None, Depends(plans_auth)],
    guard: Guard,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlansResponse:
    """List all plans for a SaaS application.

    Returns active products with their prices and metadata (features, limits).
    The endpoint is served without a token only when ``PLANS_PUBLIC`` is
    enabled (public pricing page); otherwise the caller needs
    ``billing:platform:read`` and a binding to the application.
    """
    # Find the SaaS app by slug
    result = await db.execute(
        select(SaasApp).where(SaasApp.slug == app_slug, SaasApp.is_active == True)  # noqa: E712
    )
    saas_app = result.scalar_one_or_none()

    if auth is not None:
        # Same answer for an unknown application and one the client may not see
        allowed = await guard.authorized_saas_ids(auth, db)
        if not saas_app or (allowed is not None and saas_app.id not in allowed):
            saas_app = None

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
