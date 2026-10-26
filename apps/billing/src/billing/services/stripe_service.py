# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Stripe service layer.

Wraps Stripe SDK operations with saas_id metadata injection.
All Stripe objects are tagged with metadata.saas_id for routing.
"""

import json
import logging
from datetime import datetime
from functools import lru_cache
from typing import Any

import stripe

from billing.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# Metadata keys owned by the server: callers can never set or override them.
RESERVED_METADATA_KEYS = frozenset({"saas_id", "external_id"})

# Limits of the Stripe API on metadata: 50 keys, 40 characters per key and
# 500 characters per value, and string values only.
STRIPE_METADATA_MAX_KEYS = 50
STRIPE_METADATA_MAX_KEY_LENGTH = 40
STRIPE_METADATA_MAX_VALUE_LENGTH = 500


def to_stripe_metadata(metadata: dict | None, reserved: set[str] | None = None) -> dict[str, str]:
    """Turn caller metadata into a flat string mapping accepted by Stripe.

    Stripe only stores string values. Non-string values (numbers, booleans,
    lists, nested objects such as ``features`` or ``limits``) are serialized
    to compact JSON, ``None`` values are dropped, and entries that Stripe
    would refuse (key or value too long, too many keys) are skipped with a
    warning: the full document stays in the local database. Server-owned
    keys (``RESERVED_METADATA_KEYS`` plus ``reserved``) are always dropped
    so that a caller cannot override ``saas_id``.

    Args:
        metadata: Caller supplied metadata.
        reserved: Additional keys to drop for this call.

    Returns:
        Metadata where every value is a string.
    """
    blocked = RESERVED_METADATA_KEYS | (reserved or set())
    result: dict[str, str] = {}
    for raw_key, value in (metadata or {}).items():
        key = str(raw_key)
        if key in blocked or value is None:
            continue
        text = (
            value
            if isinstance(value, str)
            else json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)
        )
        if (
            len(key) > STRIPE_METADATA_MAX_KEY_LENGTH
            or len(text) > STRIPE_METADATA_MAX_VALUE_LENGTH
        ):
            logger.warning("Stripe metadata key %r skipped: key or value too long", key)
            continue
        # Keep one slot for the server-owned saas_id
        if len(result) >= STRIPE_METADATA_MAX_KEYS - 1:
            logger.warning("Stripe metadata key %r skipped: too many keys", key)
            continue
        result[key] = text
    return result


def tag_metadata(saas_id: str, metadata: dict | None = None, **owned: str) -> dict[str, str]:
    """Build the metadata of a new Stripe object.

    The caller metadata is sanitized first and the server-owned values
    (``saas_id`` and the keyword arguments) are written last, so they always
    win.

    Args:
        saas_id: The SaaS application ID.
        metadata: Caller supplied metadata.
        **owned: Other server-owned values (e.g. ``external_id``).

    Returns:
        Metadata for the Stripe call.
    """
    tagged = to_stripe_metadata(metadata, reserved=set(owned))
    tagged.update({key: value for key, value in owned.items() if value})
    tagged["saas_id"] = str(saas_id)
    return tagged


def build_stripe_description(
    description: str | None,
    extra_data: dict | None,
) -> str | None:
    """Build a Stripe product description including features from extra_data.

    Appends enabled features as a bullet list after the base description.
    Disabled features are excluded (they represent "not included" on pricing pages).

    Args:
        description: Base product description.
        extra_data: Product extra_data containing optional features list.

    Returns:
        Combined description string, or None if no content.
    """
    features = []
    if extra_data:
        for feat in extra_data.get("features", []):
            if isinstance(feat, dict) and not feat.get("disabled", False):
                label = feat.get("label", "").strip()
                if label:
                    features.append(label)

    if not description and not features:
        return None

    parts = []
    if description:
        parts.append(description)
    if features:
        parts.append("Features:\n" + "\n".join(f"- {f}" for f in features))

    return "\n\n".join(parts)


class StripeService:
    """Wrapper for Stripe SDK operations with saas_id metadata injection."""

    def __init__(self) -> None:
        stripe.api_key = settings.stripe_secret_key

    # =========================================================================
    # Products
    # =========================================================================

    def create_product(
        self,
        saas_id: str,
        name: str,
        description: str | None = None,
        metadata: dict | None = None,
    ) -> stripe.Product:
        """Create a Stripe product with saas_id in metadata.

        Args:
            saas_id: The SaaS application ID.
            name: Product name.
            description: Product description.
            metadata: Additional metadata.

        Returns:
            Stripe Product object.
        """
        params: dict[str, Any] = {
            "name": name,
            "metadata": tag_metadata(saas_id, metadata),
        }
        if description is not None:
            params["description"] = description

        return stripe.Product.create(**params)

    def update_product(
        self,
        stripe_product_id: str,
        name: str | None = None,
        description: str | None = None,
        active: bool | None = None,
        metadata: dict | None = None,
    ) -> stripe.Product:
        """Update a Stripe product.

        Args:
            stripe_product_id: Stripe product ID.
            name: New product name.
            description: New product description.
            active: Whether product is active.
            metadata: Additional metadata (merged, not replaced). Values are
                stringified and ``saas_id`` cannot be changed.

        Returns:
            Updated Stripe Product object.
        """
        params: dict[str, Any] = {}
        if name is not None:
            params["name"] = name
        if description is not None:
            params["description"] = description
        if active is not None:
            params["active"] = active
        if metadata is not None:
            params["metadata"] = to_stripe_metadata(metadata)

        return stripe.Product.modify(stripe_product_id, **params)

    def get_product(self, stripe_product_id: str) -> stripe.Product:
        """Get a Stripe product by ID.

        Args:
            stripe_product_id: Stripe product ID.

        Returns:
            Stripe Product object.
        """
        return stripe.Product.retrieve(stripe_product_id)

    # =========================================================================
    # Prices
    # =========================================================================

    def create_price(
        self,
        saas_id: str,
        stripe_product_id: str,
        unit_amount: int | None,
        currency: str | None = None,
        billing_type: str = "recurring",
        recurring_interval: str | None = None,
        recurring_interval_count: int = 1,
        usage_type: str = "licensed",
        nickname: str | None = None,
        metadata: dict | None = None,
    ) -> stripe.Price:
        """Create a Stripe price with saas_id in metadata.

        Args:
            saas_id: The SaaS application ID.
            stripe_product_id: Stripe product ID.
            unit_amount: Price in cents (None for metered).
            currency: Currency code (``DEFAULT_CURRENCY`` when omitted).
            billing_type: 'recurring' or 'one_time'.
            recurring_interval: 'day', 'week', 'month', or 'year'.
            recurring_interval_count: Number of intervals.
            usage_type: 'licensed' or 'metered'.
            nickname: Price nickname.
            metadata: Additional metadata.

        Returns:
            Stripe Price object.
        """
        params: dict[str, Any] = {
            "product": stripe_product_id,
            "currency": currency or settings.default_currency,
            "metadata": tag_metadata(saas_id, metadata),
        }

        if nickname:
            params["nickname"] = nickname

        if billing_type == "recurring":
            params["recurring"] = {
                "interval": recurring_interval or settings.default_recurring_interval,
                "interval_count": recurring_interval_count,
                "usage_type": usage_type,
            }
            if usage_type == "metered":
                params["recurring"]["aggregate_usage"] = "sum"
            else:
                params["unit_amount"] = unit_amount
        else:
            # One-time payment
            params["unit_amount"] = unit_amount

        return stripe.Price.create(**params)

    def get_price(self, stripe_price_id: str) -> stripe.Price:
        """Get a Stripe price by ID.

        Args:
            stripe_price_id: Stripe price ID.

        Returns:
            Stripe Price object.
        """
        return stripe.Price.retrieve(stripe_price_id)

    def update_price(
        self,
        stripe_price_id: str,
        nickname: str | None = None,
        active: bool | None = None,
        metadata: dict | None = None,
    ) -> stripe.Price:
        """Update a Stripe price (limited fields - prices are mostly immutable).

        Args:
            stripe_price_id: Stripe price ID.
            nickname: Price nickname.
            active: Whether price is active.
            metadata: Additional metadata (merged, not replaced).

        Returns:
            Updated Stripe Price object.
        """
        params: dict[str, Any] = {}
        if nickname is not None:
            params["nickname"] = nickname
        if active is not None:
            params["active"] = active
        if metadata is not None:
            params["metadata"] = to_stripe_metadata(metadata)

        return stripe.Price.modify(stripe_price_id, **params)

    # =========================================================================
    # Customers
    # =========================================================================

    def create_customer(
        self,
        saas_id: str,
        email: str,
        name: str | None = None,
        external_id: str | None = None,
        metadata: dict | None = None,
    ) -> stripe.Customer:
        """Create a Stripe customer with saas_id in metadata.

        Args:
            saas_id: The SaaS application ID.
            email: Customer email.
            name: Customer name.
            external_id: External reference ID from SaaS app.
            metadata: Additional metadata.

        Returns:
            Stripe Customer object.
        """
        params: dict[str, Any] = {
            "email": email,
            "metadata": tag_metadata(saas_id, metadata, external_id=external_id or ""),
        }
        if name is not None:
            params["name"] = name

        return stripe.Customer.create(**params)

    def update_customer(
        self,
        stripe_customer_id: str,
        email: str | None = None,
        name: str | None = None,
        metadata: dict | None = None,
    ) -> stripe.Customer:
        """Update a Stripe customer.

        Args:
            stripe_customer_id: Stripe customer ID.
            email: New email.
            name: New name.
            metadata: Additional metadata (merged, not replaced).

        Returns:
            Updated Stripe Customer object.
        """
        params: dict[str, Any] = {}
        if email is not None:
            params["email"] = email
        if name is not None:
            params["name"] = name
        if metadata is not None:
            params["metadata"] = to_stripe_metadata(metadata)

        return stripe.Customer.modify(stripe_customer_id, **params)

    def get_customer(self, stripe_customer_id: str) -> stripe.Customer:
        """Get a Stripe customer by ID.

        Args:
            stripe_customer_id: Stripe customer ID.

        Returns:
            Stripe Customer object.
        """
        return stripe.Customer.retrieve(stripe_customer_id)

    def create_customer_portal_session(
        self,
        stripe_customer_id: str,
        return_url: str,
    ) -> stripe.billing_portal.Session:
        """Create a customer portal session for managing billing.

        Args:
            stripe_customer_id: Stripe customer ID.
            return_url: URL to redirect after portal session.

        Returns:
            Stripe BillingPortal Session object.
        """
        return stripe.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url=return_url,
        )

    # =========================================================================
    # Subscriptions
    # =========================================================================

    def create_subscription(
        self,
        saas_id: str,
        stripe_customer_id: str,
        stripe_price_id: str,
        trial_period_days: int | None = None,
        metadata: dict | None = None,
    ) -> stripe.Subscription:
        """Create a Stripe subscription with saas_id in metadata.

        Args:
            saas_id: The SaaS application ID.
            stripe_customer_id: Stripe customer ID.
            stripe_price_id: Stripe price ID.
            trial_period_days: Trial period in days.
            metadata: Additional metadata.

        Returns:
            Stripe Subscription object.
        """
        params: dict[str, Any] = {
            "customer": stripe_customer_id,
            "items": [{"price": stripe_price_id}],
            "metadata": tag_metadata(saas_id, metadata),
        }

        if trial_period_days:
            params["trial_period_days"] = trial_period_days

        return stripe.Subscription.create(**params)

    def update_subscription(
        self,
        stripe_subscription_id: str,
        cancel_at_period_end: bool | None = None,
        metadata: dict | None = None,
    ) -> stripe.Subscription:
        """Update a Stripe subscription.

        Args:
            stripe_subscription_id: Stripe subscription ID.
            cancel_at_period_end: Whether to cancel at period end.
            metadata: Additional metadata (merged, not replaced).

        Returns:
            Updated Stripe Subscription object.
        """
        params: dict[str, Any] = {}
        if cancel_at_period_end is not None:
            params["cancel_at_period_end"] = cancel_at_period_end
        if metadata is not None:
            params["metadata"] = to_stripe_metadata(metadata)

        return stripe.Subscription.modify(stripe_subscription_id, **params)

    def cancel_subscription(
        self,
        stripe_subscription_id: str,
        immediately: bool = False,
    ) -> stripe.Subscription:
        """Cancel a Stripe subscription.

        Args:
            stripe_subscription_id: Stripe subscription ID.
            immediately: If True, cancel immediately. Otherwise, cancel at period end.

        Returns:
            Canceled Stripe Subscription object.
        """
        if immediately:
            return stripe.Subscription.cancel(stripe_subscription_id)
        else:
            return stripe.Subscription.modify(
                stripe_subscription_id,
                cancel_at_period_end=True,
            )

    def get_subscription(self, stripe_subscription_id: str) -> stripe.Subscription:
        """Get a Stripe subscription by ID.

        Args:
            stripe_subscription_id: Stripe subscription ID.

        Returns:
            Stripe Subscription object.
        """
        return stripe.Subscription.retrieve(stripe_subscription_id)

    def preview_subscription_upgrade(
        self,
        stripe_subscription_id: str,
        new_stripe_price_id: str,
    ) -> stripe.Invoice:
        """Preview what an upgrade will cost (proration).

        Uses Stripe's upcoming invoice API to calculate proration.

        Args:
            stripe_subscription_id: Stripe subscription ID.
            new_stripe_price_id: The new Stripe price ID to switch to.

        Returns:
            Stripe Invoice object with proration line items.
        """
        # Get current subscription to find the item ID
        subscription = stripe.Subscription.retrieve(stripe_subscription_id)

        # Use bracket notation to access 'items' to avoid conflict with dict.items() method
        subscription_items = subscription["items"]
        if not subscription_items or not subscription_items.data:
            raise ValueError("Subscription has no items")

        subscription_item_id = subscription_items.data[0].id

        # Preview upcoming invoice with the new price
        # In Stripe SDK v7+, Invoice.upcoming() was replaced by Invoice.create_preview()
        return stripe.Invoice.create_preview(
            customer=str(subscription.customer),
            subscription=stripe_subscription_id,
            subscription_details={
                "items": [
                    {
                        "id": subscription_item_id,
                        "price": new_stripe_price_id,
                    }
                ],
                "proration_behavior": "create_prorations",
            },
        )

    def upgrade_subscription(
        self,
        stripe_subscription_id: str,
        new_stripe_price_id: str,
        proration_behavior: str = "create_prorations",
    ) -> tuple[stripe.Subscription, stripe.Invoice | None]:
        """Upgrade a subscription to a new plan with proration.

        Args:
            stripe_subscription_id: Stripe subscription ID.
            new_stripe_price_id: The new Stripe price ID to switch to.
            proration_behavior: How to handle proration:
                - 'create_prorations': Credit applied to next invoice (default)
                - 'always_invoice': Invoice immediately with proration
                - 'none': No proration

        Returns:
            Tuple of (updated subscription, invoice if always_invoice else None).
        """
        # Get current subscription to find the item ID
        subscription = stripe.Subscription.retrieve(stripe_subscription_id)

        # Use bracket notation to access 'items' to avoid conflict with dict.items() method
        subscription_items = subscription["items"]
        if not subscription_items or not subscription_items.data:
            raise ValueError("Subscription has no items")

        subscription_item_id = subscription_items.data[0].id

        # Modify the subscription with the new price
        updated_subscription = stripe.Subscription.modify(
            stripe_subscription_id,
            items=[
                {
                    "id": subscription_item_id,
                    "price": new_stripe_price_id,
                }
            ],
            proration_behavior=proration_behavior,  # type: ignore[arg-type]
        )

        # If always_invoice, Stripe creates and pays an invoice immediately
        # Fetch it if available
        invoice = None
        if proration_behavior == "always_invoice":
            try:
                # Get the latest invoice for this subscription
                invoices = stripe.Invoice.list(
                    subscription=stripe_subscription_id,
                    limit=1,
                )
                if invoices.data:
                    invoice = invoices.data[0]
            except Exception as e:
                logger.warning(f"Could not fetch proration invoice: {e}")

        return updated_subscription, invoice

    # =========================================================================
    # Checkout Sessions
    # =========================================================================

    def create_checkout_session(
        self,
        saas_id: str,
        stripe_customer_id: str,
        stripe_price_id: str,
        success_url: str,
        cancel_url: str,
        mode: str = "subscription",
        quantity: int = 1,
        trial_period_days: int | None = None,
        metadata: dict | None = None,
        locale: str | None = None,
        custom_text: dict | None = None,
    ) -> stripe.checkout.Session:
        """Create a Stripe Checkout Session.

        Args:
            saas_id: The SaaS application ID.
            stripe_customer_id: Stripe customer ID.
            stripe_price_id: Stripe price ID.
            success_url: URL to redirect on success.
            cancel_url: URL to redirect on cancel.
            mode: 'subscription' or 'payment'.
            quantity: Quantity of items.
            trial_period_days: Trial period in days (subscription only).
            metadata: Additional metadata. ``saas_id`` is owned by the server
                and cannot be overridden by the caller.
            locale: Checkout page locale (e.g. from the SaaS branding).
            custom_text: Stripe ``custom_text`` block (e.g. from the SaaS branding).

        Returns:
            Stripe Checkout Session object.
        """
        session_metadata = tag_metadata(saas_id, metadata)

        params: dict[str, Any] = {
            "customer": stripe_customer_id,
            "line_items": [{"price": stripe_price_id, "quantity": quantity}],
            "mode": mode,
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": session_metadata,
        }

        if locale:
            params["locale"] = locale
        if custom_text:
            params["custom_text"] = custom_text

        if mode == "subscription":
            params["subscription_data"] = {"metadata": {"saas_id": str(saas_id)}}
            if trial_period_days:
                params["subscription_data"]["trial_period_days"] = trial_period_days

        return stripe.checkout.Session.create(**params)

    # =========================================================================
    # Usage Records (Metered Billing)
    # =========================================================================

    def report_usage(
        self,
        stripe_subscription_item_id: str,
        quantity: int,
        timestamp: int | None = None,
        idempotency_key: str | None = None,
    ) -> stripe.StripeObject:
        """Report usage for metered billing.

        Args:
            stripe_subscription_item_id: Stripe subscription item ID.
            quantity: Usage quantity.
            timestamp: Unix timestamp (defaults to now).
            idempotency_key: Idempotency key to prevent duplicates.

        Returns:
            Stripe usage record object.
        """
        params: dict[str, Any] = {
            "quantity": quantity,
            "action": "increment",
        }

        if timestamp:
            params["timestamp"] = timestamp
        else:
            params["timestamp"] = int(datetime.utcnow().timestamp())

        kwargs: dict[str, Any] = {}
        if idempotency_key:
            kwargs["idempotency_key"] = idempotency_key

        return stripe.SubscriptionItem.create_usage_record(  # type: ignore[attr-defined]
            stripe_subscription_item_id,
            **params,
            **kwargs,
        )

    # =========================================================================
    # Webhook Signature Verification
    # =========================================================================

    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
        webhook_secret: str | None = None,
    ) -> stripe.Event:
        """Verify webhook signature and construct event.

        Args:
            payload: Raw request body.
            signature: Stripe-Signature header value.
            webhook_secret: Webhook secret (uses default if not provided).

        Returns:
            Stripe Event object.

        Raises:
            stripe.error.SignatureVerificationError: If signature is invalid.
        """
        secret = webhook_secret or settings.stripe_webhook_secret
        return stripe.Webhook.construct_event(payload, signature, secret)


@lru_cache
def get_stripe_service() -> StripeService:
    """Get cached Stripe service instance."""
    return StripeService()
