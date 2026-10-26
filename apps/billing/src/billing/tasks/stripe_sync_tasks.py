# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Celery tasks for Stripe synchronization."""

import logging
import re

import stripe
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from billing.celery import celery_app
from billing.database import async_session_factory
from billing.models import BillingProduct, SaasApp
from billing.services import get_stripe_service
from billing.services.stripe_service import build_stripe_description

logger = logging.getLogger(__name__)

# Real Stripe IDs pattern: prod_XXXXX or price_XXXXX (alphanumeric after prefix)
STRIPE_PRODUCT_ID_PATTERN = re.compile(r"^prod_[A-Za-z0-9]{14,}$")
STRIPE_PRICE_ID_PATTERN = re.compile(r"^price_[A-Za-z0-9]{14,}$")


def is_placeholder_stripe_id(stripe_id: str, pattern: re.Pattern) -> bool:
    """Check if a Stripe ID is a placeholder (not a real Stripe ID)."""
    return not pattern.match(stripe_id)


@celery_app.task(bind=True, name="billing.tasks.stripe_sync_tasks.sync_all_products_to_stripe")
def sync_all_products_to_stripe(self) -> dict:
    """Sync all products and prices with placeholder IDs to Stripe.

    This task runs periodically to ensure all seeded products/prices
    are created on Stripe with real IDs.

    Returns:
        Dict with sync statistics.
    """
    import asyncio

    async def _sync():
        stripe_service = get_stripe_service()
        total_products_synced = 0
        total_prices_synced = 0
        total_products_skipped = 0
        total_prices_skipped = 0
        errors = []

        async with async_session_factory() as db:
            # Get all SaaS apps with products and prices
            result = await db.execute(
                select(SaasApp)
                .where(SaasApp.is_active == True)  # noqa: E712
                .options(selectinload(SaasApp.products).selectinload(BillingProduct.prices))
            )
            saas_apps = list(result.scalars().all())

            if not saas_apps:
                logger.debug("No SaaS apps to sync")
                return {
                    "products_synced": 0,
                    "prices_synced": 0,
                    "products_skipped": 0,
                    "prices_skipped": 0,
                    "errors": [],
                }

            for saas_app in saas_apps:
                logger.info(f"Syncing products for SaaS app: {saas_app.slug}")

                for product in saas_app.products:
                    if not is_placeholder_stripe_id(
                        product.stripe_product_id, STRIPE_PRODUCT_ID_PATTERN
                    ):
                        total_products_skipped += 1
                        continue

                    try:
                        # Build description with features for Stripe
                        stripe_description = build_stripe_description(
                            product.description, product.extra_data
                        )
                        stripe_product = stripe_service.create_product(
                            saas_id=saas_app.id,
                            name=product.name,
                            description=stripe_description,
                        )

                        old_stripe_id = product.stripe_product_id
                        product.stripe_product_id = stripe_product.id
                        total_products_synced += 1
                        logger.info(
                            f"Synced product {product.name}: {old_stripe_id} -> {stripe_product.id}"
                        )

                        # Sync prices for this product
                        for price in product.prices:
                            if not is_placeholder_stripe_id(
                                price.stripe_price_id, STRIPE_PRICE_ID_PATTERN
                            ):
                                total_prices_skipped += 1
                                continue

                            # Skip prices without unit_amount (custom/contact-us pricing)
                            if price.unit_amount is None:
                                logger.info(
                                    f"Skipping price {price.nickname}: no unit_amount (custom pricing)"
                                )
                                total_prices_skipped += 1
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
                                total_prices_synced += 1
                                logger.info(
                                    f"Synced price {price.nickname}: {old_price_id} -> {stripe_price.id}"
                                )

                            except stripe.StripeError as e:
                                error_msg = f"Failed to sync price {price.nickname}: {e}"
                                logger.error(error_msg)
                                errors.append(error_msg)

                    except stripe.StripeError as e:
                        error_msg = f"Failed to sync product {product.name}: {e}"
                        logger.error(error_msg)
                        errors.append(error_msg)

            await db.commit()

        logger.info(
            f"Stripe sync complete: {total_products_synced} products, "
            f"{total_prices_synced} prices synced"
        )

        return {
            "products_synced": total_products_synced,
            "prices_synced": total_prices_synced,
            "products_skipped": total_products_skipped,
            "prices_skipped": total_prices_skipped,
            "errors": errors,
        }

    return asyncio.run(_sync())
