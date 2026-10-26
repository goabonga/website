# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""HTTP client for billing API (billing.internal)."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import quote

import httpx
from pydantic import BaseModel

from internal.config import settings

logger = logging.getLogger(__name__)


# =============================================================================
# Response Models
# =============================================================================


class SaasApp(BaseModel):
    """SaaS application in the billing system."""

    id: str
    name: str
    slug: str
    description: str | None = None
    webhook_url: str | None = None
    branding: dict | None = None
    checkout_url_allowlist: list[str] | None = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class BillingProduct(BaseModel):
    """Billing product."""

    id: str
    saas_app_id: str
    stripe_product_id: str
    name: str
    description: str | None = None
    extra_data: dict | None = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class BillingPrice(BaseModel):
    """Billing price."""

    id: str
    product_id: str
    stripe_price_id: str
    nickname: str | None = None
    currency: str = "usd"
    unit_amount: int | None = None
    billing_type: str = "recurring"
    recurring_interval: str | None = None
    recurring_interval_count: int = 1
    usage_type: str = "licensed"
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class Customer(BaseModel):
    """Billing customer."""

    id: str
    saas_app_id: str
    external_id: str
    stripe_customer_id: str
    email: str
    name: str | None = None
    created_at: datetime
    updated_at: datetime


class Subscription(BaseModel):
    """Customer subscription."""

    id: str
    customer_id: str
    price_id: str | None = None
    stripe_subscription_id: str
    stripe_subscription_item_id: str | None = None
    status: str
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    cancel_at_period_end: bool = False
    canceled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ClientBinding(BaseModel):
    """An OAuth client allowed to act on a SaaS application."""

    id: str
    saas_app_id: str
    client_id: str
    created_at: datetime


class CustomerPortal(BaseModel):
    """Stripe Customer Portal session."""

    url: str


# =============================================================================
# Billing Client
# =============================================================================

# What a call needs from the access token: the scope of the operation (read or write), always
# together with the admin scope, or the admin scope alone (SaaS creation, client bindings).
Access = Literal["read", "write", "admin"]


class BillingClient:
    """HTTP client to interact with billing API."""

    def __init__(self) -> None:
        self._socket_path = getattr(settings, "billing_socket_path", "") or ""
        # For socket connections, use http://localhost as base URL (routing via socket)
        if self._socket_path:
            self._base_url = "http://localhost"
        else:
            self._base_url = settings.billing_api_url.rstrip("/")
        self._client_id = settings.oauth2_client_id
        self._client_secret = settings.oauth2_client_secret
        self._issuer = settings.oauth2_issuer.rstrip("/") if settings.oauth2_issuer else ""
        self._tokens: dict[str, tuple[str, datetime]] = {}

    @staticmethod
    def _scope(access: Access) -> str:
        """Return the scopes to request for an ``access`` level, from the settings.

        The billing service partitions its API between SaaS apps: only a token carrying its
        admin scope (``PARTITION_ADMIN_SCOPE``) may list every app, create one or manage the
        OAuth client bindings. Scopes that are not configured are left out.
        """
        operation = {
            "read": settings.billing_read_scope,
            "write": settings.billing_write_scope,
            "admin": "",
        }[access]
        return " ".join(
            dict.fromkeys(name for name in (operation, settings.billing_admin_scope) if name)
        )

    async def _get_access_token(self, scope: str) -> str:
        """Get access token using client credentials flow."""
        if scope in self._tokens:
            token, expires_at = self._tokens[scope]
            if datetime.now(UTC) < expires_at - timedelta(seconds=30):
                return token

        if not self._issuer:
            raise ValueError("oauth2_issuer not configured")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._issuer}/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "scope": scope,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            data = response.json()

        access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        self._tokens[scope] = (access_token, expires_at)
        return access_token

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        access: Access = "read",
    ) -> Any:
        """Make an authenticated request to the billing API."""
        if not self._base_url:
            raise ValueError("billing_api_url not configured")

        try:
            token = await self._get_access_token(scope=self._scope(access))
        except Exception as e:
            logger.error("Failed to get access token for billing API: %s", e)
            raise

        # Use Unix socket transport if configured
        transport = None
        if self._socket_path:
            transport = httpx.AsyncHTTPTransport(uds=self._socket_path)

        async with httpx.AsyncClient(
            timeout=settings.billing_timeout, transport=transport
        ) as client:
            response = await client.request(
                method,
                f"{self._base_url}{endpoint}",
                params=params,
                json=json_data,
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()

    # =========================================================================
    # SaaS Apps
    # =========================================================================

    async def list_saas_apps(self, include_inactive: bool = False) -> list[SaasApp]:
        """List the SaaS applications (the inactive ones too when asked)."""
        try:
            params = {"include_inactive": "true"} if include_inactive else None
            data = await self._request("GET", "/platform/saas", params=params)
            return [SaasApp(**item) for item in data]
        except Exception as e:
            logger.exception("Failed to fetch SaaS apps: %s", e)
            return []

    async def get_saas_app(self, saas_id: str) -> SaasApp | None:
        """Get a specific SaaS application."""
        try:
            data = await self._request("GET", f"/platform/saas/{saas_id}")
            return SaasApp(**data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.exception("Failed to fetch SaaS app: %s", e)
            return None
        except Exception as e:
            logger.exception("Failed to fetch SaaS app: %s", e)
            return None

    async def create_saas_app(
        self,
        name: str,
        slug: str,
        description: str | None = None,
        webhook_url: str | None = None,
        webhook_secret: str | None = None,
    ) -> SaasApp | None:
        """Create a new SaaS application."""
        try:
            json_data = {
                "name": name,
                "slug": slug,
                "description": description,
                "webhook_url": webhook_url,
            }
            if webhook_secret:
                json_data["webhook_secret"] = webhook_secret

            data = await self._request(
                "POST",
                "/platform/saas",
                json_data=json_data,
                access="admin",
            )
            return SaasApp(**data)
        except Exception as e:
            logger.exception("Failed to create SaaS app: %s", e)
            return None

    async def update_saas_app(
        self,
        saas_id: str,
        name: str | None = None,
        description: str | None = None,
        webhook_url: str | None = None,
        webhook_secret: str | None = None,
        is_active: bool | None = None,
    ) -> SaasApp | None:
        """Update a SaaS application."""
        try:
            update_data: dict[str, Any] = {}
            if name is not None:
                update_data["name"] = name
            if description is not None:
                update_data["description"] = description
            if webhook_url is not None:
                update_data["webhook_url"] = webhook_url
            if webhook_secret:
                update_data["webhook_secret"] = webhook_secret
            if is_active is not None:
                update_data["is_active"] = is_active

            data = await self._request(
                "PATCH",
                f"/platform/saas/{saas_id}",
                json_data=update_data,
                access="write",
            )
            return SaasApp(**data)
        except Exception as e:
            logger.exception("Failed to update SaaS app: %s", e)
            return None

    # =========================================================================
    # OAuth client bindings (admin scope)
    # =========================================================================

    async def list_saas_clients(self, saas_id: str) -> list[ClientBinding]:
        """List the OAuth clients bound to a SaaS application."""
        try:
            data = await self._request("GET", f"/platform/saas/{saas_id}/clients", access="admin")
            return [ClientBinding(**item) for item in data]
        except Exception as e:
            logger.exception("Failed to fetch client bindings: %s", e)
            return []

    async def bind_client(self, saas_id: str, client_id: str) -> ClientBinding | None:
        """Bind an OAuth client to a SaaS application (idempotent)."""
        try:
            data = await self._request(
                "PUT",
                f"/platform/saas/{saas_id}/clients/{quote(client_id, safe='')}",
                access="admin",
            )
            return ClientBinding(**data)
        except Exception as e:
            logger.exception("Failed to bind client: %s", e)
            return None

    async def unbind_client(self, saas_id: str, client_id: str) -> bool:
        """Remove the binding of an OAuth client to a SaaS application."""
        try:
            await self._request(
                "DELETE",
                f"/platform/saas/{saas_id}/clients/{quote(client_id, safe='')}",
                access="admin",
            )
            return True
        except Exception as e:
            logger.exception("Failed to unbind client: %s", e)
            return False

    # =========================================================================
    # Products
    # =========================================================================

    async def list_products(
        self, saas_id: str, include_inactive: bool = False
    ) -> list[BillingProduct]:
        """List products for a SaaS application (the inactive ones too when asked)."""
        try:
            params = {"include_inactive": "true"} if include_inactive else None
            data = await self._request("GET", f"/platform/{saas_id}/products", params=params)
            return [BillingProduct(**item) for item in data]
        except Exception as e:
            logger.exception("Failed to fetch products: %s", e)
            return []

    async def get_product(self, saas_id: str, product_id: str) -> BillingProduct | None:
        """Get a specific product."""
        try:
            data = await self._request("GET", f"/platform/{saas_id}/products/{product_id}")
            return BillingProduct(**data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.exception("Failed to fetch product: %s", e)
            return None
        except Exception as e:
            logger.exception("Failed to fetch product: %s", e)
            return None

    async def create_product(
        self,
        saas_id: str,
        name: str,
        description: str | None = None,
        metadata: dict | None = None,
    ) -> BillingProduct | None:
        """Create a new product in Stripe."""
        try:
            json_data: dict[str, Any] = {
                "name": name,
                "description": description,
            }
            if metadata is not None:
                json_data["metadata"] = metadata

            data = await self._request(
                "POST",
                f"/platform/{saas_id}/products",
                json_data=json_data,
                access="write",
            )
            return BillingProduct(**data)
        except Exception as e:
            logger.exception("Failed to create product: %s", e)
            return None

    async def update_product(
        self,
        saas_id: str,
        product_id: str,
        name: str | None = None,
        description: str | None = None,
        metadata: dict | None = None,
        is_active: bool | None = None,
    ) -> BillingProduct | None:
        """Update a product with name, description, metadata (features/limits), or status."""
        try:
            update_data: dict[str, Any] = {}
            if name is not None:
                update_data["name"] = name
            if description is not None:
                update_data["description"] = description
            if metadata is not None:
                update_data["metadata"] = metadata
            if is_active is not None:
                update_data["is_active"] = is_active

            data = await self._request(
                "PATCH",
                f"/platform/{saas_id}/products/{product_id}",
                json_data=update_data,
                access="write",
            )
            return BillingProduct(**data)
        except Exception as e:
            logger.exception("Failed to update product: %s", e)
            return None

    # =========================================================================
    # Prices
    # =========================================================================

    async def list_prices(
        self, saas_id: str, product_id: str, include_inactive: bool = False
    ) -> list[BillingPrice]:
        """List prices for a product."""
        try:
            params = {"include_inactive": include_inactive} if include_inactive else None
            data = await self._request(
                "GET",
                f"/platform/{saas_id}/products/{product_id}/prices",
                params=params,
            )
            return [BillingPrice(**item) for item in data]
        except Exception as e:
            logger.exception("Failed to fetch prices: %s", e)
            return []

    async def create_price(
        self,
        saas_id: str,
        product_id: str,
        unit_amount: int,
        currency: str | None = None,
        billing_type: str | None = None,
        recurring_interval: str | None = None,
        usage_type: str | None = None,
        nickname: str | None = None,
    ) -> BillingPrice | None:
        """Create a new price in Stripe.

        Fields left to ``None`` are not sent: the billing service applies its own defaults
        (``DEFAULT_CURRENCY``, ``DEFAULT_RECURRING_INTERVAL``, recurring and licensed).
        """
        try:
            optional = {
                "currency": currency,
                "billing_type": billing_type,
                "recurring_interval": recurring_interval,
                "usage_type": usage_type,
                "nickname": nickname,
            }
            data = await self._request(
                "POST",
                f"/platform/{saas_id}/products/{product_id}/prices",
                json_data={
                    "unit_amount": unit_amount,
                    **{key: value for key, value in optional.items() if value is not None},
                },
                access="write",
            )
            return BillingPrice(**data)
        except Exception as e:
            logger.exception("Failed to create price: %s", e)
            return None

    async def update_price(
        self,
        saas_id: str,
        product_id: str,
        price_id: str,
        nickname: str | None = None,
        is_active: bool | None = None,
    ) -> BillingPrice | None:
        """Update a price (limited fields - Stripe prices are mostly immutable)."""
        try:
            update_data: dict[str, Any] = {}
            if nickname is not None:
                update_data["nickname"] = nickname
            if is_active is not None:
                update_data["is_active"] = is_active

            data = await self._request(
                "PATCH",
                f"/platform/{saas_id}/products/{product_id}/prices/{price_id}",
                json_data=update_data,
                access="write",
            )
            return BillingPrice(**data)
        except Exception as e:
            logger.exception("Failed to update price: %s", e)
            return None

    # =========================================================================
    # Customers
    # =========================================================================

    async def list_customers(
        self, saas_id: str, limit: int = 50, offset: int = 0
    ) -> list[Customer]:
        """List customers for a SaaS application."""
        try:
            data = await self._request(
                "GET",
                f"/platform/{saas_id}/customers",
                params={"limit": limit, "offset": offset},
            )
            return [Customer(**item) for item in data]
        except Exception as e:
            logger.exception("Failed to fetch customers: %s", e)
            return []

    async def get_customer(self, saas_id: str, customer_id: str) -> Customer | None:
        """Get a specific customer."""
        try:
            data = await self._request("GET", f"/platform/{saas_id}/customers/{customer_id}")
            return Customer(**data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.exception("Failed to fetch customer: %s", e)
            return None
        except Exception as e:
            logger.exception("Failed to fetch customer: %s", e)
            return None

    async def get_customer_portal(
        self, saas_id: str, customer_id: str, return_url: str
    ) -> CustomerPortal | None:
        """Get Stripe Customer Portal URL for a customer.

        ``return_url`` must be covered by the checkout URL allow-list of the SaaS app.
        """
        try:
            data = await self._request(
                "GET",
                f"/platform/{saas_id}/customers/{customer_id}/portal",
                params={"return_url": return_url},
            )
            return CustomerPortal(**data)
        except Exception as e:
            logger.exception("Failed to get customer portal: %s", e)
            return None

    # =========================================================================
    # Subscriptions
    # =========================================================================

    async def list_subscriptions(
        self,
        saas_id: str,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Subscription]:
        """List subscriptions for a SaaS application."""
        try:
            params: dict[str, Any] = {"limit": limit, "offset": offset}
            if status:
                params["status"] = status
            data = await self._request("GET", f"/platform/{saas_id}/subscriptions", params=params)
            return [Subscription(**item) for item in data]
        except Exception as e:
            logger.exception("Failed to fetch subscriptions: %s", e)
            return []

    async def get_subscription(self, saas_id: str, subscription_id: str) -> Subscription | None:
        """Get a specific subscription."""
        try:
            data = await self._request(
                "GET", f"/platform/{saas_id}/subscriptions/{subscription_id}"
            )
            return Subscription(**data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.exception("Failed to fetch subscription: %s", e)
            return None
        except Exception as e:
            logger.exception("Failed to fetch subscription: %s", e)
            return None

    async def list_customer_subscriptions(
        self, saas_id: str, customer_id: str
    ) -> list[Subscription]:
        """List every subscription of a customer."""
        try:
            data = await self._request(
                "GET", f"/platform/{saas_id}/customers/{customer_id}/subscriptions"
            )
            return [Subscription(**item) for item in data]
        except Exception as e:
            logger.exception("Failed to fetch customer subscriptions: %s", e)
            return []

    async def cancel_subscription(
        self,
        saas_id: str,
        subscription_id: str,
        cancel_at_period_end: bool = True,
    ) -> Subscription | None:
        """Cancel a subscription, at the end of the paid period or immediately."""
        try:
            data = await self._request(
                "POST",
                f"/platform/{saas_id}/subscriptions/{subscription_id}/cancel",
                json_data={"cancel_at_period_end": cancel_at_period_end},
                access="write",
            )
            return Subscription(**data)
        except Exception as e:
            logger.exception("Failed to cancel subscription: %s", e)
            return None

    async def reactivate_subscription(
        self, saas_id: str, subscription_id: str
    ) -> Subscription | None:
        """Undo a cancellation scheduled for the end of the period."""
        try:
            data = await self._request(
                "POST",
                f"/platform/{saas_id}/subscriptions/{subscription_id}/reactivate",
                access="write",
            )
            return Subscription(**data)
        except Exception as e:
            logger.exception("Failed to reactivate subscription: %s", e)
            return None

    async def sync_subscription(
        self,
        saas_id: str,
        subscription_id: str,
    ) -> Subscription | None:
        """Sync a subscription from Stripe."""
        try:
            data = await self._request(
                "POST",
                f"/platform/{saas_id}/subscriptions/{subscription_id}/sync",
                access="write",
            )
            return Subscription(**data)
        except Exception as e:
            logger.exception("Failed to sync subscription: %s", e)
            return None


# Singleton instance
billing_client = BillingClient()
