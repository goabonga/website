# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Billing API client for fetching plans and pricing."""

import json
from dataclasses import dataclass
from datetime import datetime

import httpx
import redis.asyncio as redis

from knowledge.config import get_settings
from knowledge.logging import get_logger
from knowledge.services.service_auth import (
    ServiceAuthError,
    TokenCache,
    credentials_for,
)

logger = get_logger(__name__)


class BillingAPIError(Exception):
    """Billing API request failed."""

    pass


@dataclass
class PlanFeature:
    """A feature included in a plan."""

    label: str
    highlight: bool = False
    disabled: bool = False


@dataclass
class PlanPrice:
    """Price information for a plan."""

    id: str
    currency: str
    unit_amount: int | None  # In cents
    interval: str | None  # month, year
    interval_count: int = 1

    @property
    def display_amount(self) -> str:
        """Get display-friendly amount (with cents if applicable)."""
        if self.unit_amount is None or self.unit_amount == 0:
            return "0"
        dollars = self.unit_amount // 100
        cents = self.unit_amount % 100
        if cents == 0:
            return str(dollars)
        return f"{dollars}.{cents:02d}"

    @property
    def is_custom(self) -> bool:
        """Check if this is custom pricing."""
        return self.unit_amount is None


@dataclass
class Plan:
    """A billing plan with pricing and features."""

    id: str
    slug: str
    name: str
    description: str | None
    features: list[PlanFeature]
    limits: dict[str, int] | None  # quota limits, named by this application
    prices: list[PlanPrice]
    is_recommended: bool
    sort_order: int

    @property
    def monthly_price(self) -> PlanPrice | None:
        """Get the monthly price for this plan."""
        for price in self.prices:
            if price.interval == "month" and price.interval_count == 1:
                return price
        return self.prices[0] if self.prices else None

    @property
    def yearly_price(self) -> PlanPrice | None:
        """Get the yearly price for this plan."""
        for price in self.prices:
            if price.interval == "year" and price.interval_count == 1:
                return price
        return None

    @property
    def yearly_savings_percent(self) -> int:
        """Calculate savings percentage for yearly vs monthly billing."""
        monthly = self.monthly_price
        yearly = self.yearly_price
        if not monthly or not yearly:
            return 0
        if not monthly.unit_amount or not yearly.unit_amount:
            return 0
        monthly_annual_cost = monthly.unit_amount * 12
        savings = monthly_annual_cost - yearly.unit_amount
        return round((savings / monthly_annual_cost) * 100)

    @property
    def yearly_monthly_equivalent(self) -> str:
        """Get the monthly equivalent of the yearly price (for display)."""
        yearly = self.yearly_price
        if not yearly or not yearly.unit_amount:
            return "0"
        monthly_amount = yearly.unit_amount // 12
        dollars = monthly_amount // 100
        cents = monthly_amount % 100
        if cents == 0:
            return str(dollars)
        return f"{dollars}.{cents:02d}"

    @property
    def is_free(self) -> bool:
        """Check if this is a free plan."""
        price = self.monthly_price
        return price is not None and price.unit_amount == 0


@dataclass
class CheckoutSession:
    """A Stripe checkout session."""

    session_id: str
    url: str


@dataclass
class ProrationLineItem:
    """A single line item in the proration preview."""

    description: str
    amount: int  # In cents (negative = credit, positive = charge)
    currency: str = "usd"

    @property
    def display_amount(self) -> str:
        """Get display-friendly amount."""
        dollars = abs(self.amount) // 100
        cents = abs(self.amount) % 100
        sign = "-" if self.amount < 0 else ""
        if cents == 0:
            return f"{sign}${dollars}"
        return f"{sign}${dollars}.{cents:02d}"


@dataclass
class UpgradePreview:
    """Preview of what a subscription upgrade will cost."""

    current_plan_name: str
    new_plan_name: str
    current_price_amount: int  # Monthly price in cents
    new_price_amount: int  # Monthly price in cents
    line_items: list[ProrationLineItem]
    subtotal: int  # In cents
    total: int  # Amount due now (in cents)
    credit_applied: int  # Credit from current plan (in cents)
    currency: str = "usd"

    @property
    def display_total(self) -> str:
        """Get display-friendly total amount."""
        dollars = abs(self.total) // 100
        cents = abs(self.total) % 100
        sign = "-" if self.total < 0 else ""
        if cents == 0:
            return f"{sign}${dollars}"
        return f"{sign}${dollars}.{cents:02d}"

    @property
    def display_credit(self) -> str:
        """Get display-friendly credit amount."""
        dollars = self.credit_applied // 100
        cents = self.credit_applied % 100
        if cents == 0:
            return f"${dollars}"
        return f"${dollars}.{cents:02d}"


@dataclass
class UpgradeResult:
    """Result of a subscription upgrade."""

    success: bool
    proration_applied: bool
    amount_due: int  # In cents
    invoice_id: str | None = None


@dataclass
class CancelResult:
    """Result of a subscription cancellation."""

    success: bool
    cancel_at_period_end: bool
    current_period_end: datetime | None = None
    error: str | None = None


@dataclass
class ReactivateResult:
    """Result of a subscription reactivation."""

    success: bool
    status: str | None = None
    error: str | None = None


@dataclass
class TenantSubscription:
    """Subscription information for a tenant."""

    id: str
    status: str
    price_id: str | None
    current_period_start: datetime | None
    current_period_end: datetime | None
    cancel_at_period_end: bool = False


def parse_limits(raw: object) -> dict[str, int] | None:
    """Return the integer limits of a plan, ``None`` when the plan declares none."""
    if not isinstance(raw, dict):
        return None
    return {
        str(name): value
        for name, value in raw.items()
        if isinstance(value, int) and not isinstance(value, bool)
    }


def checkout_redirect_urls() -> tuple[str, str]:
    """Return the success and cancel URLs of a checkout session.

    They come from ``BILLING_CHECKOUT_SUCCESS_URL`` and ``BILLING_CHECKOUT_CANCEL_URL``.
    Billing only accepts URLs covered by the checkout URL allow-list of the SaaS
    application, so the two must be registered there.

    Raises:
        BillingAPIError: If one of the URLs is not configured.
    """
    settings = get_settings()
    success = settings.billing_checkout_success_url
    cancel = settings.billing_checkout_cancel_url
    if not success or not cancel:
        raise BillingAPIError(
            "BILLING_CHECKOUT_SUCCESS_URL and BILLING_CHECKOUT_CANCEL_URL are not configured"
        )
    return success, cancel


class BillingClient:
    """Client for the Billing API.

    Fetches plans and pricing information from the centralized billing service.
    Caches results in Redis to reduce API calls.

    Supports two connection modes:
    - HTTP URL: Direct HTTP connection (e.g., http://127.0.0.1:8082)
    - Unix socket: Local socket connection (e.g., /run/billing/billing.sock)
    """

    def __init__(self) -> None:
        # Get fresh settings instance to ensure env vars are loaded
        current_settings = get_settings()
        self.socket_path = current_settings.billing_socket_path
        self.api_url = (
            current_settings.billing_api_url.rstrip("/") if current_settings.billing_api_url else ""
        )
        self.app_slug = current_settings.billing_app_slug
        self.cache_ttl = current_settings.billing_cache_ttl
        self.timeout = current_settings.service_timeout
        self._redis_url = current_settings.redis_url
        self._billing_saas_id = current_settings.billing_saas_id
        self._http_client: httpx.AsyncClient | None = None
        self._redis_client: redis.Redis | None = None
        self._tokens = TokenCache()

    @property
    def is_configured(self) -> bool:
        """Check if the billing service is reachable by configuration (URL or socket)."""
        return bool(self.api_url) or bool(self.socket_path)

    @property
    def saas_id(self) -> str:
        """Return the id of this SaaS application in billing.

        Raises:
            BillingAPIError: If BILLING_SAAS_ID is not configured (there is no default).
        """
        if not self._billing_saas_id:
            raise BillingAPIError("BILLING_SAAS_ID is not configured")
        return self._billing_saas_id

    @property
    def base_url(self) -> str:
        """Get the base URL for API requests.

        For Unix sockets, we use http://localhost as a placeholder
        (the actual routing happens via the socket transport).
        """
        if self.socket_path:
            return "http://localhost"
        return self.api_url

    async def get_http_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            if self.socket_path:
                transport = httpx.AsyncHTTPTransport(uds=self.socket_path)
                self._http_client = httpx.AsyncClient(
                    transport=transport,
                    timeout=self.timeout,
                )
            else:
                self._http_client = httpx.AsyncClient(timeout=self.timeout)
        return self._http_client

    async def _get_access_token(self, scope: str) -> str:
        """Get an access token for ``scope`` with the client credentials grant.

        Raises:
            BillingAPIError: If the token cannot be obtained.
        """
        try:
            return await self._tokens.aget(credentials_for("billing"), scope)
        except ServiceAuthError as e:
            logger.error("Failed to get OAuth2 access token: %s", e)
            raise BillingAPIError(str(e)) from e

    async def get_redis_client(self) -> redis.Redis:
        """Get or create Redis client."""
        if self._redis_client is None:
            self._redis_client = redis.from_url(
                self._redis_url,
                decode_responses=True,
            )
        return self._redis_client

    def _cache_key(self) -> str:
        """Generate cache key for plans."""
        return f"knowledge:billing:plans:{self.app_slug}"

    async def get_plans(self) -> list[Plan]:
        """Fetch plans from the billing API.

        Returns:
            List of Plan objects with pricing and features.

        Raises:
            BillingAPIError: If the API request fails.
        """
        if not self.is_configured or not self.app_slug:
            logger.warning("Billing API not configured, returning empty plans")
            return []

        # Check cache first
        cache_key = self._cache_key()
        try:
            redis_client = await self.get_redis_client()
            cached = await redis_client.get(cache_key)
            if cached:
                logger.debug("Billing plans cache hit")
                return self._parse_plans(json.loads(cached))
        except Exception as e:
            logger.warning(f"Redis cache error: {e}")

        # Fetch from API
        try:
            # The plans are not public (PLANS_PUBLIC=false): billing wants a token
            access_token = await self._get_access_token("billing:platform:read")
            client = await self.get_http_client()
            response = await client.get(
                f"{self.base_url}/plans/{self.app_slug}",
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if response.status_code == 404:
                logger.warning(f"Billing app '{self.app_slug}' not found")
                return []

            if response.status_code != 200:
                raise BillingAPIError(
                    f"Billing API returned {response.status_code}: {response.text}"
                )

            data = response.json()

            # Cache the result
            try:
                await redis_client.setex(
                    cache_key,
                    self.cache_ttl,
                    json.dumps(data),
                )
            except Exception as e:
                logger.warning(f"Redis cache set error: {e}")

            return self._parse_plans(data)

        except httpx.RequestError as e:
            logger.error(f"Billing API request failed: {e}")
            raise BillingAPIError(f"Billing API request failed: {e}")

    def _parse_plans(self, data: dict) -> list[Plan]:
        """Parse API response into Plan objects."""
        plans = []
        for plan_data in data.get("plans", []):
            # Parse features
            features = []
            for feat in plan_data.get("features", []):
                features.append(
                    PlanFeature(
                        label=feat.get("label", ""),
                        highlight=feat.get("highlight", False),
                        disabled=feat.get("disabled", False),
                    )
                )

            # Parse limits: integers named by this application, nothing is built in
            limits = parse_limits(plan_data.get("limits"))

            # Parse prices
            prices = []
            for price_data in plan_data.get("prices", []):
                prices.append(
                    PlanPrice(
                        id=price_data.get("id", ""),
                        currency=price_data.get("currency", "usd"),
                        unit_amount=price_data.get("unit_amount"),
                        interval=price_data.get("interval"),
                        interval_count=price_data.get("interval_count", 1),
                    )
                )

            plan = Plan(
                id=plan_data.get("id", ""),
                slug=plan_data.get("slug", ""),
                name=plan_data.get("name", ""),
                description=plan_data.get("description"),
                features=features,
                limits=limits,
                prices=prices,
                is_recommended=plan_data.get("is_recommended", False),
                sort_order=plan_data.get("sort_order", 0),
            )
            plans.append(plan)

        # Sort by sort_order
        plans.sort(key=lambda p: p.sort_order)
        return plans

    async def get_plan_by_slug(self, slug: str) -> Plan | None:
        """Get a specific plan by slug.

        Args:
            slug: The plan slug (e.g., 'free', 'starter', 'pro').

        Returns:
            The Plan if found, None otherwise.
        """
        plans = await self.get_plans()
        for plan in plans:
            if plan.slug == slug:
                return plan
        return None

    async def create_checkout_session(
        self,
        tenant_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
        trial_period_days: int | None = None,
        customer_email: str | None = None,
        customer_name: str | None = None,
    ) -> CheckoutSession:
        """Create a Stripe Checkout session for subscription.

        Args:
            tenant_id: The tenant ID (used as external_id in billing).
            price_id: The price ID to subscribe to.
            success_url: URL to redirect after successful payment.
            cancel_url: URL to redirect if checkout is cancelled.
            trial_period_days: Optional trial period in days.
            customer_email: Customer email (for auto-creating customer if not exists).
            customer_name: Customer name (for auto-creating customer if not exists).

        Returns:
            CheckoutSession with session_id and redirect URL.

        Raises:
            BillingAPIError: If the API request fails.
        """
        if not self.is_configured:
            raise BillingAPIError("Billing API not configured")

        payload: dict[str, str | int | None] = {
            "saas_id": self.saas_id,
            "external_id": tenant_id,
            "price_id": price_id,
            "success_url": success_url,
            "cancel_url": cancel_url,
            "mode": "subscription",
        }

        if trial_period_days:
            payload["trial_period_days"] = trial_period_days

        # Include customer info for auto-creation if not exists
        if customer_email:
            payload["customer_email"] = customer_email
        if customer_name:
            payload["customer_name"] = customer_name

        try:
            # Get OAuth2 access token with billing checkout scope
            access_token = await self._get_access_token("billing:checkout:write")

            client = await self.get_http_client()
            response = await client.post(
                f"{self.base_url}/checkout/session",
                json=payload,
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if response.status_code == 404:
                raise BillingAPIError("Customer or price not found in billing system")

            if response.status_code == 422:
                raise BillingAPIError(
                    "Billing refused the checkout URLs: they must be covered by the "
                    "checkout URL allow-list of the SaaS application"
                )

            if response.status_code != 200:
                raise BillingAPIError(
                    f"Billing API returned {response.status_code}: {response.text}"
                )

            data = response.json()
            return CheckoutSession(
                session_id=data["session_id"],
                url=data["url"],
            )

        except httpx.RequestError as e:
            logger.error(f"Billing API checkout request failed: {e}")
            raise BillingAPIError(f"Billing API request failed: {e}")

    async def get_tenant_subscription(self, tenant_id: str) -> TenantSubscription | None:
        """Get the active subscription for a tenant.

        Args:
            tenant_id: The tenant/organization ID.

        Returns:
            TenantSubscription if found, None otherwise.
        """
        if not self.is_configured:
            return None

        try:
            access_token = await self._get_access_token("billing:platform:read")

            client = await self.get_http_client()
            response = await client.get(
                f"{self.base_url}/platform/{self.saas_id}/external/{tenant_id}/subscription",
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if response.status_code == 404:
                return None

            if response.status_code != 200:
                logger.warning(
                    f"Failed to get subscription: {response.status_code} {response.text}"
                )
                return None

            data = response.json()
            if not data:
                return None

            return TenantSubscription(
                id=data["id"],
                status=data["status"],
                price_id=data.get("price_id"),
                current_period_start=datetime.fromisoformat(
                    data["current_period_start"].replace("Z", "+00:00")
                )
                if data.get("current_period_start")
                else None,
                current_period_end=datetime.fromisoformat(
                    data["current_period_end"].replace("Z", "+00:00")
                )
                if data.get("current_period_end")
                else None,
                cancel_at_period_end=data.get("cancel_at_period_end", False),
            )

        except httpx.RequestError as e:
            logger.error(f"Failed to get tenant subscription: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting tenant subscription: {e}")
            return None

    async def preview_upgrade(
        self,
        subscription_id: str,
        new_price_id: str,
    ) -> UpgradePreview:
        """Preview what an upgrade will cost before committing.

        Args:
            subscription_id: The subscription ID to upgrade.
            new_price_id: The new price ID to upgrade to.

        Returns:
            UpgradePreview with proration details.

        Raises:
            BillingAPIError: If the API request fails.
        """
        if not self.is_configured:
            raise BillingAPIError("Billing API not configured")

        try:
            access_token = await self._get_access_token("billing:platform:read")

            client = await self.get_http_client()
            response = await client.post(
                f"{self.base_url}/platform/{self.saas_id}/subscriptions/{subscription_id}/upgrade/preview",
                json={"new_price_id": new_price_id},
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if response.status_code == 404:
                raise BillingAPIError("Subscription or price not found")

            if response.status_code == 400:
                error_data = response.json()
                raise BillingAPIError(error_data.get("detail", "Invalid upgrade request"))

            if response.status_code != 200:
                raise BillingAPIError(
                    f"Billing API returned {response.status_code}: {response.text}"
                )

            data = response.json()

            # Parse line items
            line_items = [
                ProrationLineItem(
                    description=item["description"],
                    amount=item["amount"],
                    currency=item.get("currency", "usd"),
                )
                for item in data.get("line_items", [])
            ]

            return UpgradePreview(
                current_plan_name=data["current_plan_name"],
                new_plan_name=data["new_plan_name"],
                current_price_amount=data["current_price_amount"],
                new_price_amount=data["new_price_amount"],
                line_items=line_items,
                subtotal=data["subtotal"],
                total=data["total"],
                credit_applied=data["credit_applied"],
                currency=data.get("currency", "usd"),
            )

        except httpx.RequestError as e:
            logger.error(f"Billing API preview request failed: {e}")
            raise BillingAPIError(f"Billing API request failed: {e}")

    async def upgrade_subscription(
        self,
        subscription_id: str,
        new_price_id: str,
        proration_behavior: str = "create_prorations",
    ) -> UpgradeResult:
        """Upgrade a subscription to a new plan with proration.

        Args:
            subscription_id: The subscription ID to upgrade.
            new_price_id: The new price ID to upgrade to.
            proration_behavior: How to handle proration:
                - 'create_prorations': Credit applied to next invoice (default)
                - 'always_invoice': Invoice immediately with proration
                - 'none': No proration

        Returns:
            UpgradeResult with success status and invoice details.

        Raises:
            BillingAPIError: If the API request fails.
        """
        if not self.is_configured:
            raise BillingAPIError("Billing API not configured")

        try:
            access_token = await self._get_access_token("billing:platform:write")

            client = await self.get_http_client()
            response = await client.post(
                f"{self.base_url}/platform/{self.saas_id}/subscriptions/{subscription_id}/upgrade",
                json={
                    "new_price_id": new_price_id,
                    "proration_behavior": proration_behavior,
                },
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if response.status_code == 404:
                raise BillingAPIError("Subscription or price not found")

            if response.status_code == 400:
                error_data = response.json()
                raise BillingAPIError(error_data.get("detail", "Invalid upgrade request"))

            if response.status_code != 200:
                raise BillingAPIError(
                    f"Billing API returned {response.status_code}: {response.text}"
                )

            data = response.json()

            return UpgradeResult(
                success=True,
                proration_applied=data.get("proration_applied", True),
                amount_due=data.get("amount_due", 0),
                invoice_id=data.get("invoice_id"),
            )

        except httpx.RequestError as e:
            logger.error(f"Billing API upgrade request failed: {e}")
            raise BillingAPIError(f"Billing API request failed: {e}")

    async def cancel_subscription(
        self,
        subscription_id: str,
        cancel_at_period_end: bool = True,
    ) -> CancelResult:
        """Cancel a subscription.

        Args:
            subscription_id: The subscription ID to cancel.
            cancel_at_period_end: If True, cancel at end of billing period.
                                  If False, cancel immediately.

        Returns:
            CancelResult with cancellation details.
        """
        if not self.is_configured:
            return CancelResult(
                success=False,
                cancel_at_period_end=False,
                error="Billing API not configured",
            )

        try:
            access_token = await self._get_access_token("billing:platform:write")

            client = await self.get_http_client()
            response = await client.post(
                f"{self.base_url}/platform/{self.saas_id}/subscriptions/{subscription_id}/cancel",
                json={"cancel_at_period_end": cancel_at_period_end},
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if response.status_code == 404:
                return CancelResult(
                    success=False,
                    cancel_at_period_end=False,
                    error="Subscription not found",
                )

            if response.status_code == 409:
                return CancelResult(
                    success=False,
                    cancel_at_period_end=False,
                    error="Subscription is already canceled",
                )

            if response.status_code not in (200, 201):
                logger.error(
                    f"Failed to cancel subscription: {response.status_code} {response.text}"
                )
                return CancelResult(
                    success=False,
                    cancel_at_period_end=False,
                    error=f"Billing API error: {response.status_code}",
                )

            data = response.json()

            current_period_end = None
            if data.get("current_period_end"):
                current_period_end = datetime.fromisoformat(
                    data["current_period_end"].replace("Z", "+00:00")
                )

            return CancelResult(
                success=True,
                cancel_at_period_end=data.get("cancel_at_period_end", cancel_at_period_end),
                current_period_end=current_period_end,
            )

        except httpx.RequestError as e:
            logger.error(f"Billing API cancel request failed: {e}")
            return CancelResult(
                success=False,
                cancel_at_period_end=False,
                error=f"Request failed: {e}",
            )
        except Exception as e:
            logger.error(f"Unexpected error cancelling subscription: {e}")
            return CancelResult(
                success=False,
                cancel_at_period_end=False,
                error=f"Unexpected error: {e}",
            )

    async def reactivate_subscription(
        self,
        subscription_id: str,
    ) -> ReactivateResult:
        """Reactivate a subscription that was scheduled for cancellation.

        This removes the cancel_at_period_end flag and resumes normal billing.

        Args:
            subscription_id: The subscription ID to reactivate.

        Returns:
            ReactivateResult with reactivation details.
        """
        if not self.is_configured:
            return ReactivateResult(
                success=False,
                error="Billing API not configured",
            )

        try:
            access_token = await self._get_access_token("billing:platform:write")

            client = await self.get_http_client()
            response = await client.post(
                f"{self.base_url}/platform/{self.saas_id}/subscriptions/{subscription_id}/reactivate",
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if response.status_code == 404:
                return ReactivateResult(
                    success=False,
                    error="Subscription not found",
                )

            if response.status_code == 409:
                return ReactivateResult(
                    success=False,
                    error="Subscription cannot be reactivated",
                )

            if response.status_code not in (200, 201):
                logger.error(
                    f"Failed to reactivate subscription: {response.status_code} {response.text}"
                )
                return ReactivateResult(
                    success=False,
                    error=f"Billing API error: {response.status_code}",
                )

            data = response.json()

            return ReactivateResult(
                success=True,
                status=data.get("status", "active"),
            )

        except httpx.RequestError as e:
            logger.error(f"Billing API reactivate request failed: {e}")
            return ReactivateResult(
                success=False,
                error=f"Request failed: {e}",
            )
        except Exception as e:
            logger.error(f"Unexpected error reactivating subscription: {e}")
            return ReactivateResult(
                success=False,
                error=f"Unexpected error: {e}",
            )

    async def close(self) -> None:
        """Close HTTP and Redis clients."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
        if self._redis_client:
            await self._redis_client.aclose()


# Singleton instance
_billing_client: BillingClient | None = None


def get_billing_client() -> BillingClient:
    """Get or create the billing client singleton."""
    global _billing_client
    if _billing_client is None:
        _billing_client = BillingClient()
    return _billing_client
