# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for billing API client."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from internal.services.billing_client import (
    BillingClient,
    BillingPrice,
    BillingProduct,
    ClientBinding,
    Customer,
    CustomerPortal,
    SaasApp,
    Subscription,
)


@pytest.fixture
def client():
    """Create a BillingClient with mocked settings (no socket)."""
    with patch("internal.services.billing_client.settings") as s:
        s.billing_socket_path = ""
        s.billing_api_url = "https://billing.example.com"
        s.billing_read_scope = "billing:platform:read"
        s.billing_write_scope = "billing:platform:write"
        s.billing_admin_scope = "billing:admin"
        s.billing_timeout = 12.5
        s.oauth2_client_id = "test-client"
        s.oauth2_client_secret = "test-secret"
        s.oauth2_issuer = "https://auth.example.com"
        yield BillingClient()


@pytest.fixture
def socket_client():
    """Create a BillingClient with socket transport."""
    with patch("internal.services.billing_client.settings") as s:
        s.billing_socket_path = "/run/billing/billing.sock"
        s.billing_api_url = "https://billing.example.com"
        s.billing_read_scope = "billing:platform:read"
        s.billing_write_scope = "billing:platform:write"
        s.billing_admin_scope = "billing:admin"
        s.billing_timeout = 12.5
        s.oauth2_client_id = "test-client"
        s.oauth2_client_secret = "test-secret"
        s.oauth2_issuer = "https://auth.example.com"
        yield BillingClient()


def _token_response(token="test-token", expires_in=3600):
    return httpx.Response(
        200,
        json={"access_token": token, "expires_in": expires_in},
        request=httpx.Request("POST", "https://auth.example.com/oauth2/token"),
    )


def _json_response(data, status_code=200):
    return httpx.Response(
        status_code,
        json=data,
        request=httpx.Request("GET", "https://billing.example.com/platform/test"),
    )


NOW = "2024-01-01T00:00:00"
NOW2 = "2024-01-02T00:00:00"


def _saas_app_data(app_id="app1"):
    return {
        "id": app_id,
        "name": "Test App",
        "slug": "test-app",
        "description": "A test app",
        "webhook_url": None,
        "is_active": True,
        "created_at": NOW,
        "updated_at": NOW2,
    }


def _product_data(product_id="prod1", saas_id="app1"):
    return {
        "id": product_id,
        "saas_app_id": saas_id,
        "stripe_product_id": "stripe_prod_1",
        "slug": "test-product",
        "name": "Test Product",
        "description": "A product",
        "extra_data": None,
        "is_active": True,
        "created_at": NOW,
        "updated_at": NOW2,
    }


def _price_data(price_id="price1", product_id="prod1"):
    return {
        "id": price_id,
        "product_id": product_id,
        "stripe_price_id": "stripe_price_1",
        "nickname": "Monthly",
        "currency": "eur",
        "unit_amount": 1000,
        "billing_type": "recurring",
        "recurring_interval": "month",
        "recurring_interval_count": 1,
        "usage_type": "licensed",
        "is_active": True,
        "created_at": NOW,
        "updated_at": NOW2,
    }


def _binding_data(client_id="client-a", saas_id="app1"):
    return {
        "id": "bind1",
        "saas_app_id": saas_id,
        "client_id": client_id,
        "created_at": NOW,
    }


def _customer_data(customer_id="cust1", saas_id="app1"):
    return {
        "id": customer_id,
        "saas_app_id": saas_id,
        "external_id": "ext1",
        "stripe_customer_id": "stripe_cust_1",
        "email": "customer@example.com",
        "name": "Test Customer",
        "created_at": NOW,
        "updated_at": NOW2,
    }


def _subscription_data(sub_id="sub1", customer_id="cust1"):
    return {
        "id": sub_id,
        "customer_id": customer_id,
        "price_id": "price1",
        "stripe_subscription_id": "stripe_sub_1",
        "stripe_subscription_item_id": "stripe_si_1",
        "status": "active",
        "current_period_start": NOW,
        "current_period_end": NOW2,
        "cancel_at_period_end": False,
        "canceled_at": None,
        "created_at": NOW,
        "updated_at": NOW2,
    }


# =========================================================================
# __init__
# =========================================================================


class TestInit:
    def test_without_socket(self, client):
        assert client._base_url == "https://billing.example.com"
        assert client._socket_path == ""

    def test_with_socket(self, socket_client):
        assert socket_client._base_url == "http://localhost"
        assert socket_client._socket_path == "/run/billing/billing.sock"

    def test_no_billing_socket_path_attr(self):
        with patch("internal.services.billing_client.settings") as s:
            # Simulate settings without billing_socket_path attribute
            del s.billing_socket_path
            s.billing_api_url = "https://billing.example.com"
            s.oauth2_client_id = "test"
            s.oauth2_client_secret = "test"
            s.oauth2_issuer = "https://auth.example.com"
            c = BillingClient()
            assert c._base_url == "https://billing.example.com"
            assert c._socket_path == ""


# =========================================================================
# _get_access_token
# =========================================================================


class TestGetAccessToken:
    @pytest.mark.asyncio
    async def test_fetches_new_token(self, client):
        mock_http = AsyncMock()
        mock_http.post.return_value = _token_response("new-token")

        with patch("internal.services.billing_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            token = await client._get_access_token("billing:platform:read")
            assert token == "new-token"

    @pytest.mark.asyncio
    async def test_returns_cached_token(self, client):
        client._tokens["billing:platform:read"] = (
            "cached-token",
            datetime.now(UTC) + timedelta(hours=1),
        )
        token = await client._get_access_token("billing:platform:read")
        assert token == "cached-token"

    @pytest.mark.asyncio
    async def test_refreshes_expired_token(self, client):
        client._tokens["billing:platform:read"] = (
            "expired-token",
            datetime.now(UTC) - timedelta(hours=1),
        )
        mock_http = AsyncMock()
        mock_http.post.return_value = _token_response("fresh-token")

        with patch("internal.services.billing_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            token = await client._get_access_token("billing:platform:read")
            assert token == "fresh-token"

    @pytest.mark.asyncio
    async def test_refreshes_near_expiry_token(self, client):
        client._tokens["billing:platform:read"] = (
            "near-expiry",
            datetime.now(UTC) + timedelta(seconds=10),
        )
        mock_http = AsyncMock()
        mock_http.post.return_value = _token_response("new-token")

        with patch("internal.services.billing_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            token = await client._get_access_token("billing:platform:read")
            assert token == "new-token"

    @pytest.mark.asyncio
    async def test_raises_when_no_issuer(self):
        with patch("internal.services.billing_client.settings") as s:
            s.billing_socket_path = ""
            s.billing_api_url = "https://billing.example.com"
            s.oauth2_client_id = "test"
            s.oauth2_client_secret = "test"
            s.oauth2_issuer = ""
            c = BillingClient()
            with pytest.raises(ValueError, match="oauth2_issuer not configured"):
                await c._get_access_token("billing:platform:read")

    @pytest.mark.asyncio
    async def test_default_expires_in(self, client):
        mock_http = AsyncMock()
        mock_http.post.return_value = httpx.Response(
            200,
            json={"access_token": "tok"},
            request=httpx.Request("POST", "https://auth.example.com/oauth2/token"),
        )

        with patch("internal.services.billing_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            token = await client._get_access_token("billing:platform:read")
            assert token == "tok"


# =========================================================================
# Scopes
# =========================================================================


class TestScope:
    def test_read_carries_the_admin_scope(self, client):
        assert client._scope("read") == "billing:platform:read billing:admin"

    def test_write_carries_the_admin_scope(self, client):
        assert client._scope("write") == "billing:platform:write billing:admin"

    def test_admin_is_alone(self, client):
        assert client._scope("admin") == "billing:admin"

    def test_scope_names_come_from_the_settings(self, client):
        with patch("internal.services.billing_client.settings") as s:
            s.billing_read_scope = "billing:r"
            s.billing_write_scope = "billing:w"
            s.billing_admin_scope = "billing:root"
            assert client._scope("read") == "billing:r billing:root"
            assert client._scope("write") == "billing:w billing:root"
            assert client._scope("admin") == "billing:root"

    def test_an_empty_admin_scope_is_left_out(self, client):
        with patch("internal.services.billing_client.settings") as s:
            s.billing_read_scope = "billing:platform:read"
            s.billing_write_scope = "billing:platform:write"
            s.billing_admin_scope = ""
            assert client._scope("read") == "billing:platform:read"
            assert client._scope("admin") == ""

    @pytest.mark.asyncio
    async def test_token_is_requested_with_the_scopes(self, client):
        mock_http = AsyncMock()
        mock_http.post.return_value = _token_response("tok")
        with patch("internal.services.billing_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_http.request.return_value = _json_response([])
            await client._request("GET", "/platform/saas", access="write")
        assert (
            mock_http.post.call_args[1]["data"]["scope"] == "billing:platform:write billing:admin"
        )
        assert "billing:platform:write billing:admin" in client._tokens

    @pytest.mark.asyncio
    async def test_timeout_comes_from_the_settings(self, client):
        client._tokens["billing:platform:read billing:admin"] = (
            "token",
            datetime.now(UTC) + timedelta(hours=1),
        )
        mock_http = AsyncMock()
        mock_http.request.return_value = _json_response({})
        with patch("internal.services.billing_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            await client._request("GET", "/platform/saas")
            assert MockClient.call_args[1]["timeout"] == 12.5

    @pytest.mark.asyncio
    async def test_no_content_answer_is_an_empty_dict(self, client):
        client._tokens["billing:platform:read billing:admin"] = (
            "token",
            datetime.now(UTC) + timedelta(hours=1),
        )
        mock_http = AsyncMock()
        mock_http.request.return_value = httpx.Response(
            204, request=httpx.Request("DELETE", "https://billing.example.com/x")
        )
        with patch("internal.services.billing_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            assert await client._request("DELETE", "/x") == {}


# =========================================================================
# _request
# =========================================================================


class TestRequest:
    @pytest.mark.asyncio
    async def test_raises_when_no_base_url(self):
        with patch("internal.services.billing_client.settings") as s:
            s.billing_socket_path = ""
            s.billing_api_url = ""
            s.oauth2_client_id = "test"
            s.oauth2_client_secret = "test"
            s.oauth2_issuer = "https://auth.example.com"
            c = BillingClient()
            with pytest.raises(ValueError, match="billing_api_url not configured"):
                await c._request("GET", "/test")

    @pytest.mark.asyncio
    async def test_success(self, client):
        client._tokens["billing:platform:read billing:admin"] = (
            "token",
            datetime.now(UTC) + timedelta(hours=1),
        )
        mock_http = AsyncMock()
        mock_http.request.return_value = _json_response([_saas_app_data()])

        with patch("internal.services.billing_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client._request("GET", "/platform/saas")
            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_propagates_token_error(self, client):
        with (
            patch.object(client, "_get_access_token", side_effect=Exception("token fail")),
            pytest.raises(Exception, match="token fail"),
        ):
            await client._request("GET", "/test")

    @pytest.mark.asyncio
    async def test_uses_socket_transport(self, socket_client):
        socket_client._tokens["billing:platform:read billing:admin"] = (
            "token",
            datetime.now(UTC) + timedelta(hours=1),
        )
        mock_http = AsyncMock()
        mock_http.request.return_value = httpx.Response(
            200,
            json={"ok": True},
            request=httpx.Request("GET", "http://localhost/platform/test"),
        )

        with patch("internal.services.billing_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await socket_client._request("GET", "/platform/test")
            assert result == {"ok": True}
            call_kwargs = MockClient.call_args[1]
            assert call_kwargs.get("transport") is not None

    @pytest.mark.asyncio
    async def test_no_socket_transport(self, client):
        client._tokens["billing:platform:read billing:admin"] = (
            "token",
            datetime.now(UTC) + timedelta(hours=1),
        )
        mock_http = AsyncMock()
        mock_http.request.return_value = _json_response({"ok": True})

        with patch("internal.services.billing_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client._request("GET", "/platform/test")
            assert result == {"ok": True}
            call_kwargs = MockClient.call_args[1]
            assert call_kwargs.get("transport") is None


# =========================================================================
# SaaS Apps
# =========================================================================


class TestListSaasApps:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value=[_saas_app_data("app1"), _saas_app_data("app2")],
        ):
            result = await client.list_saas_apps()
            assert len(result) == 2
            assert isinstance(result[0], SaasApp)
            assert result[0].id == "app1"

    @pytest.mark.asyncio
    async def test_include_inactive(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=[]) as mock_req:
            await client.list_saas_apps(include_inactive=True)
            mock_req.assert_called_once_with(
                "GET", "/platform/saas", params={"include_inactive": "true"}
            )

    @pytest.mark.asyncio
    async def test_inactive_apps_are_hidden_by_default(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=[]) as mock_req:
            await client.list_saas_apps()
            mock_req.assert_called_once_with("GET", "/platform/saas", params=None)

    @pytest.mark.asyncio
    async def test_error_returns_empty(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.list_saas_apps()
            assert result == []


class TestGetSaasApp:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value=_saas_app_data("app1"),
        ):
            result = await client.get_saas_app("app1")
            assert isinstance(result, SaasApp)
            assert result.slug == "test-app"

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self, client):
        error_response = httpx.Response(
            404,
            request=httpx.Request("GET", "https://billing.example.com/platform/saas/xxx"),
        )
        with patch.object(
            client,
            "_request",
            side_effect=httpx.HTTPStatusError(
                "404", request=error_response.request, response=error_response
            ),
        ):
            result = await client.get_saas_app("xxx")
            assert result is None

    @pytest.mark.asyncio
    async def test_http_error_non_404_returns_none(self, client):
        error_response = httpx.Response(
            500,
            request=httpx.Request("GET", "https://billing.example.com/platform/saas/xxx"),
        )
        with patch.object(
            client,
            "_request",
            side_effect=httpx.HTTPStatusError(
                "500", request=error_response.request, response=error_response
            ),
        ):
            result = await client.get_saas_app("xxx")
            assert result is None

    @pytest.mark.asyncio
    async def test_generic_error_returns_none(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_saas_app("xxx")
            assert result is None


class TestCreateSaasApp:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value=_saas_app_data("new-app"),
        ) as mock_req:
            result = await client.create_saas_app(
                name="Test App",
                slug="test-app",
                description="A test app",
                webhook_url="https://hook.example.com",
                webhook_secret="secret123",
            )
            assert isinstance(result, SaasApp)
            call_kwargs = mock_req.call_args[1]
            assert call_kwargs["json_data"]["webhook_secret"] == "secret123"
            assert call_kwargs["access"] == "admin"

    @pytest.mark.asyncio
    async def test_without_webhook_secret(self, client):
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value=_saas_app_data("new-app"),
        ) as mock_req:
            result = await client.create_saas_app(name="Test", slug="test")
            assert isinstance(result, SaasApp)
            json_data = mock_req.call_args[1]["json_data"]
            assert "webhook_secret" not in json_data

    @pytest.mark.asyncio
    async def test_error_returns_none(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.create_saas_app(name="Test", slug="test")
            assert result is None


class TestUpdateSaasApp:
    @pytest.mark.asyncio
    async def test_success_all_fields(self, client):
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value=_saas_app_data("app1"),
        ) as mock_req:
            result = await client.update_saas_app(
                saas_id="app1",
                name="Updated",
                description="New desc",
                webhook_url="https://new-hook.com",
                webhook_secret="new-secret",
                is_active=False,
            )
            assert isinstance(result, SaasApp)
            json_data = mock_req.call_args[1]["json_data"]
            assert json_data["name"] == "Updated"
            assert json_data["description"] == "New desc"
            assert json_data["webhook_url"] == "https://new-hook.com"
            assert json_data["webhook_secret"] == "new-secret"
            assert json_data["is_active"] is False

    @pytest.mark.asyncio
    async def test_partial_update(self, client):
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value=_saas_app_data("app1"),
        ) as mock_req:
            result = await client.update_saas_app(saas_id="app1", name="Updated")
            assert isinstance(result, SaasApp)
            json_data = mock_req.call_args[1]["json_data"]
            assert json_data == {"name": "Updated"}

    @pytest.mark.asyncio
    async def test_partial_update_no_name(self, client):
        """Covers branch 272->274: name=None skips adding name to update_data."""
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value=_saas_app_data("app1"),
        ) as mock_req:
            result = await client.update_saas_app(
                saas_id="app1",
                description="Only desc",
            )
            assert isinstance(result, SaasApp)
            json_data = mock_req.call_args[1]["json_data"]
            assert "name" not in json_data
            assert json_data["description"] == "Only desc"

    @pytest.mark.asyncio
    async def test_error_returns_none(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.update_saas_app(saas_id="app1", name="Updated")
            assert result is None


# =========================================================================
# Products
# =========================================================================


class TestListProducts:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value=[_product_data("prod1"), _product_data("prod2")],
        ):
            result = await client.list_products("app1")
            assert len(result) == 2
            assert isinstance(result[0], BillingProduct)

    @pytest.mark.asyncio
    async def test_include_inactive(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=[]) as mock_req:
            await client.list_products("app1", include_inactive=True)
            mock_req.assert_called_once_with(
                "GET", "/platform/app1/products", params={"include_inactive": "true"}
            )

    @pytest.mark.asyncio
    async def test_error_returns_empty(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.list_products("app1")
            assert result == []


class TestGetProduct:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value=_product_data("prod1"),
        ):
            result = await client.get_product("app1", "prod1")
            assert isinstance(result, BillingProduct)
            assert result.name == "Test Product"

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self, client):
        error_response = httpx.Response(
            404,
            request=httpx.Request("GET", "https://billing.example.com/platform/app1/products/xxx"),
        )
        with patch.object(
            client,
            "_request",
            side_effect=httpx.HTTPStatusError(
                "404", request=error_response.request, response=error_response
            ),
        ):
            result = await client.get_product("app1", "xxx")
            assert result is None

    @pytest.mark.asyncio
    async def test_http_error_non_404_returns_none(self, client):
        error_response = httpx.Response(
            500,
            request=httpx.Request("GET", "https://billing.example.com/platform/app1/products/xxx"),
        )
        with patch.object(
            client,
            "_request",
            side_effect=httpx.HTTPStatusError(
                "500", request=error_response.request, response=error_response
            ),
        ):
            result = await client.get_product("app1", "xxx")
            assert result is None

    @pytest.mark.asyncio
    async def test_generic_error_returns_none(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_product("app1", "xxx")
            assert result is None


class TestCreateProduct:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value=_product_data("new-prod"),
        ) as mock_req:
            result = await client.create_product(
                saas_id="app1",
                name="New Product",
                description="A new product",
                metadata={"feature_limit": 100},
            )
            assert isinstance(result, BillingProduct)
            json_data = mock_req.call_args[1]["json_data"]
            assert json_data["metadata"] == {"feature_limit": 100}

    @pytest.mark.asyncio
    async def test_without_metadata(self, client):
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value=_product_data("new-prod"),
        ) as mock_req:
            result = await client.create_product(saas_id="app1", name="New")
            assert isinstance(result, BillingProduct)
            json_data = mock_req.call_args[1]["json_data"]
            assert "metadata" not in json_data

    @pytest.mark.asyncio
    async def test_error_returns_none(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.create_product(saas_id="app1", name="New")
            assert result is None


class TestUpdateProduct:
    @pytest.mark.asyncio
    async def test_success_all_fields(self, client):
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value=_product_data("prod1"),
        ) as mock_req:
            result = await client.update_product(
                saas_id="app1",
                product_id="prod1",
                name="Updated",
                description="New desc",
                metadata={"limit": 200},
                is_active=False,
            )
            assert isinstance(result, BillingProduct)
            json_data = mock_req.call_args[1]["json_data"]
            assert json_data["name"] == "Updated"
            assert json_data["is_active"] is False
            assert json_data["metadata"] == {"limit": 200}

    @pytest.mark.asyncio
    async def test_partial_update(self, client):
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value=_product_data("prod1"),
        ) as mock_req:
            await client.update_product(saas_id="app1", product_id="prod1", name="Updated")
            json_data = mock_req.call_args[1]["json_data"]
            assert json_data == {"name": "Updated"}

    @pytest.mark.asyncio
    async def test_error_returns_none(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.update_product(saas_id="app1", product_id="prod1")
            assert result is None


# =========================================================================
# Prices
# =========================================================================


class TestListPrices:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value=[_price_data("price1")],
        ):
            result = await client.list_prices("app1", "prod1")
            assert len(result) == 1
            assert isinstance(result[0], BillingPrice)

    @pytest.mark.asyncio
    async def test_include_inactive(self, client):
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value=[_price_data("price1")],
        ) as mock_req:
            result = await client.list_prices("app1", "prod1", include_inactive=True)
            assert len(result) == 1
            params = mock_req.call_args[1].get("params")
            assert params == {"include_inactive": True}

    @pytest.mark.asyncio
    async def test_without_include_inactive(self, client):
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_req:
            result = await client.list_prices("app1", "prod1", include_inactive=False)
            assert result == []
            params = mock_req.call_args[1].get("params")
            assert params is None

    @pytest.mark.asyncio
    async def test_error_returns_empty(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.list_prices("app1", "prod1")
            assert result == []


class TestCreatePrice:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value=_price_data("new-price"),
        ) as mock_req:
            result = await client.create_price(
                saas_id="app1",
                product_id="prod1",
                unit_amount=1000,
                currency="eur",
                billing_type="recurring",
                recurring_interval="month",
                usage_type="licensed",
                nickname="Monthly Plan",
            )
            assert isinstance(result, BillingPrice)
            json_data = mock_req.call_args[1]["json_data"]
            assert json_data["unit_amount"] == 1000
            assert json_data["nickname"] == "Monthly Plan"

    @pytest.mark.asyncio
    async def test_unset_fields_are_left_to_the_billing_service(self, client):
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=_price_data("p")
        ) as mock_req:
            await client.create_price(saas_id="app1", product_id="prod1", unit_amount=500)
            assert mock_req.call_args[1]["json_data"] == {"unit_amount": 500}

    @pytest.mark.asyncio
    async def test_error_returns_none(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.create_price(saas_id="app1", product_id="prod1", unit_amount=500)
            assert result is None


class TestUpdatePrice:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value=_price_data("price1"),
        ) as mock_req:
            result = await client.update_price(
                saas_id="app1",
                product_id="prod1",
                price_id="price1",
                nickname="Yearly Plan",
                is_active=False,
            )
            assert isinstance(result, BillingPrice)
            json_data = mock_req.call_args[1]["json_data"]
            assert json_data["nickname"] == "Yearly Plan"
            assert json_data["is_active"] is False

    @pytest.mark.asyncio
    async def test_partial_update(self, client):
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value=_price_data("price1"),
        ) as mock_req:
            await client.update_price(
                saas_id="app1", product_id="prod1", price_id="price1", nickname="New"
            )
            json_data = mock_req.call_args[1]["json_data"]
            assert json_data == {"nickname": "New"}

    @pytest.mark.asyncio
    async def test_error_returns_none(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.update_price(
                saas_id="app1", product_id="prod1", price_id="price1"
            )
            assert result is None


# =========================================================================
# Customers
# =========================================================================


class TestListCustomers:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value=[_customer_data("cust1"), _customer_data("cust2")],
        ):
            result = await client.list_customers("app1", limit=50, offset=0)
            assert len(result) == 2
            assert isinstance(result[0], Customer)

    @pytest.mark.asyncio
    async def test_error_returns_empty(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.list_customers("app1")
            assert result == []


class TestGetCustomer:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value=_customer_data("cust1"),
        ):
            result = await client.get_customer("app1", "cust1")
            assert isinstance(result, Customer)
            assert result.email == "customer@example.com"

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self, client):
        error_response = httpx.Response(
            404,
            request=httpx.Request("GET", "https://billing.example.com/platform/app1/customers/xxx"),
        )
        with patch.object(
            client,
            "_request",
            side_effect=httpx.HTTPStatusError(
                "404", request=error_response.request, response=error_response
            ),
        ):
            result = await client.get_customer("app1", "xxx")
            assert result is None

    @pytest.mark.asyncio
    async def test_http_error_non_404_returns_none(self, client):
        error_response = httpx.Response(
            500,
            request=httpx.Request("GET", "https://billing.example.com/platform/app1/customers/xxx"),
        )
        with patch.object(
            client,
            "_request",
            side_effect=httpx.HTTPStatusError(
                "500", request=error_response.request, response=error_response
            ),
        ):
            result = await client.get_customer("app1", "xxx")
            assert result is None

    @pytest.mark.asyncio
    async def test_generic_error_returns_none(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_customer("app1", "xxx")
            assert result is None


class TestGetCustomerPortal:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value={"url": "https://billing.stripe.com/session/xxx"},
        ):
            result = await client.get_customer_portal("app1", "cust1", "https://app.example.test")
            assert isinstance(result, CustomerPortal)
            assert result.url == "https://billing.stripe.com/session/xxx"

    @pytest.mark.asyncio
    async def test_sends_the_return_url(self, client):
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value={"url": "https://x.test/p"}
        ) as mock_req:
            await client.get_customer_portal("app1", "cust1", "https://app.example.test/done")
            mock_req.assert_called_once_with(
                "GET",
                "/platform/app1/customers/cust1/portal",
                params={"return_url": "https://app.example.test/done"},
            )

    @pytest.mark.asyncio
    async def test_error_returns_none(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_customer_portal("app1", "cust1", "https://app.example.test")
            assert result is None


# =========================================================================
# Subscriptions
# =========================================================================


class TestListSubscriptions:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value=[_subscription_data("sub1")],
        ):
            result = await client.list_subscriptions("app1")
            assert len(result) == 1
            assert isinstance(result[0], Subscription)
            assert result[0].status == "active"

    @pytest.mark.asyncio
    async def test_with_status_filter(self, client):
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value=[_subscription_data("sub1")],
        ) as mock_req:
            result = await client.list_subscriptions("app1", status="active", limit=10, offset=5)
            assert len(result) == 1
            params = mock_req.call_args[1]["params"]
            assert params["status"] == "active"
            assert params["limit"] == 10
            assert params["offset"] == 5

    @pytest.mark.asyncio
    async def test_without_status(self, client):
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_req:
            result = await client.list_subscriptions("app1")
            assert result == []
            params = mock_req.call_args[1]["params"]
            assert "status" not in params

    @pytest.mark.asyncio
    async def test_error_returns_empty(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.list_subscriptions("app1")
            assert result == []


class TestGetSubscription:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value=_subscription_data("sub1"),
        ):
            result = await client.get_subscription("app1", "sub1")
            assert isinstance(result, Subscription)
            assert result.stripe_subscription_id == "stripe_sub_1"

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self, client):
        error_response = httpx.Response(
            404,
            request=httpx.Request(
                "GET", "https://billing.example.com/platform/app1/subscriptions/xxx"
            ),
        )
        with patch.object(
            client,
            "_request",
            side_effect=httpx.HTTPStatusError(
                "404", request=error_response.request, response=error_response
            ),
        ):
            result = await client.get_subscription("app1", "xxx")
            assert result is None

    @pytest.mark.asyncio
    async def test_http_error_non_404_returns_none(self, client):
        error_response = httpx.Response(
            500,
            request=httpx.Request(
                "GET", "https://billing.example.com/platform/app1/subscriptions/xxx"
            ),
        )
        with patch.object(
            client,
            "_request",
            side_effect=httpx.HTTPStatusError(
                "500", request=error_response.request, response=error_response
            ),
        ):
            result = await client.get_subscription("app1", "xxx")
            assert result is None

    @pytest.mark.asyncio
    async def test_generic_error_returns_none(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_subscription("app1", "xxx")
            assert result is None


class TestCancelSubscription:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value=_subscription_data("sub1"),
        ) as mock_req:
            result = await client.cancel_subscription("app1", "sub1", cancel_at_period_end=True)
            assert isinstance(result, Subscription)
            mock_req.assert_called_once_with(
                "POST",
                "/platform/app1/subscriptions/sub1/cancel",
                json_data={"cancel_at_period_end": True},
                access="write",
            )

    @pytest.mark.asyncio
    async def test_immediately(self, client):
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=_subscription_data("sub1")
        ) as mock_req:
            await client.cancel_subscription("app1", "sub1", cancel_at_period_end=False)
            assert mock_req.call_args[1]["json_data"] == {"cancel_at_period_end": False}

    @pytest.mark.asyncio
    async def test_error_returns_none(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.cancel_subscription("app1", "sub1")
            assert result is None


class TestReactivateSubscription:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=_subscription_data("sub1")
        ) as mock_req:
            result = await client.reactivate_subscription("app1", "sub1")
            assert isinstance(result, Subscription)
            mock_req.assert_called_once_with(
                "POST", "/platform/app1/subscriptions/sub1/reactivate", access="write"
            )

    @pytest.mark.asyncio
    async def test_error_returns_none(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            assert await client.reactivate_subscription("app1", "sub1") is None


class TestListCustomerSubscriptions:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=[_subscription_data("sub1")]
        ) as mock_req:
            result = await client.list_customer_subscriptions("app1", "cust1")
            assert [sub.id for sub in result] == ["sub1"]
            mock_req.assert_called_once_with("GET", "/platform/app1/customers/cust1/subscriptions")

    @pytest.mark.asyncio
    async def test_error_returns_empty(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            assert await client.list_customer_subscriptions("app1", "cust1") == []


class TestSyncSubscription:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value=_subscription_data("sub1"),
        ) as mock_req:
            result = await client.sync_subscription("app1", "sub1")
            assert isinstance(result, Subscription)
            mock_req.assert_called_once_with(
                "POST",
                "/platform/app1/subscriptions/sub1/sync",
                access="write",
            )

    @pytest.mark.asyncio
    async def test_error_returns_none(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.sync_subscription("app1", "sub1")
            assert result is None


# =========================================================================
# Checkout URL allow-list and branding
# =========================================================================


class TestSaasAppCheckoutSettings:
    @pytest.mark.asyncio
    async def test_create_sends_the_allowlist_and_branding(self, client):
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=_saas_app_data("new")
        ) as mock_req:
            await client.create_saas_app(
                name="App",
                slug="app",
                branding={"locale": "xx"},
                checkout_url_allowlist=["https://app.example.test"],
            )
            json_data = mock_req.call_args[1]["json_data"]
            assert json_data["branding"] == {"locale": "xx"}
            assert json_data["checkout_url_allowlist"] == ["https://app.example.test"]

    @pytest.mark.asyncio
    async def test_create_leaves_them_out_when_not_given(self, client):
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=_saas_app_data("new")
        ) as mock_req:
            await client.create_saas_app(name="App", slug="app")
            json_data = mock_req.call_args[1]["json_data"]
            assert "branding" not in json_data
            assert "checkout_url_allowlist" not in json_data

    @pytest.mark.asyncio
    async def test_update_sends_them(self, client):
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=_saas_app_data()
        ) as mock_req:
            await client.update_saas_app(
                "app1",
                branding={"locale": "xx"},
                checkout_url_allowlist=["https://app.example.test"],
            )
            assert mock_req.call_args[1]["json_data"] == {
                "branding": {"locale": "xx"},
                "checkout_url_allowlist": ["https://app.example.test"],
            }

    @pytest.mark.asyncio
    async def test_update_clears_them_with_none(self, client):
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=_saas_app_data()
        ) as mock_req:
            await client.update_saas_app("app1", branding=None, checkout_url_allowlist=None)
            assert mock_req.call_args[1]["json_data"] == {
                "branding": None,
                "checkout_url_allowlist": None,
            }

    @pytest.mark.asyncio
    async def test_update_leaves_them_alone_when_not_given(self, client):
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=_saas_app_data()
        ) as mock_req:
            await client.update_saas_app("app1", name="Renamed")
            assert mock_req.call_args[1]["json_data"] == {"name": "Renamed"}

    def test_model_reads_the_fields(self):
        app = SaasApp(
            **_saas_app_data(),
            branding={"locale": "xx"},
            checkout_url_allowlist=["https://app.example.test"],
        )
        assert app.branding == {"locale": "xx"}
        assert app.checkout_url_allowlist == ["https://app.example.test"]

    def test_model_defaults_to_none(self):
        app = SaasApp(**_saas_app_data())
        assert app.branding is None
        assert app.checkout_url_allowlist is None


# =========================================================================
# Plan slug
# =========================================================================


class TestProductSlug:
    @pytest.mark.asyncio
    async def test_create_sends_the_slug(self, client):
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=_product_data("p")
        ) as mock_req:
            await client.create_product("app1", "Pro", slug="pro")
            assert mock_req.call_args[1]["json_data"]["slug"] == "pro"

    @pytest.mark.asyncio
    async def test_create_without_slug_lets_the_service_derive_it(self, client):
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=_product_data("p")
        ) as mock_req:
            await client.create_product("app1", "Pro")
            assert "slug" not in mock_req.call_args[1]["json_data"]

    @pytest.mark.asyncio
    async def test_update_sends_the_slug(self, client):
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=_product_data("p")
        ) as mock_req:
            await client.update_product("app1", "p", slug="business")
            assert mock_req.call_args[1]["json_data"] == {"slug": "business"}

    @pytest.mark.asyncio
    async def test_update_without_slug_leaves_it(self, client):
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=_product_data("p")
        ) as mock_req:
            await client.update_product("app1", "p", name="Renamed")
            assert mock_req.call_args[1]["json_data"] == {"name": "Renamed"}

    def test_product_reads_the_slug(self):
        assert BillingProduct(**_product_data()).slug == "test-product"


# =========================================================================
# OAuth client bindings
# =========================================================================


class TestListSaasClients:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value=[_binding_data("client-a"), _binding_data("client-b")],
        ) as mock_req:
            result = await client.list_saas_clients("app1")
            assert [binding.client_id for binding in result] == ["client-a", "client-b"]
            assert isinstance(result[0], ClientBinding)
            mock_req.assert_called_once_with("GET", "/platform/saas/app1/clients", access="admin")

    @pytest.mark.asyncio
    async def test_error_returns_empty(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            assert await client.list_saas_clients("app1") == []


class TestBindClient:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=_binding_data("client-a")
        ) as mock_req:
            result = await client.bind_client("app1", "client-a")
            assert isinstance(result, ClientBinding)
            assert result.saas_app_id == "app1"
            mock_req.assert_called_once_with(
                "PUT", "/platform/saas/app1/clients/client-a", access="admin"
            )

    @pytest.mark.asyncio
    async def test_client_id_is_escaped_in_the_path(self, client):
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=_binding_data("a?b#c")
        ) as mock_req:
            await client.bind_client("app1", "a?b#c")
            assert mock_req.call_args[0][1] == "/platform/saas/app1/clients/a%3Fb%23c"

    @pytest.mark.asyncio
    async def test_error_returns_none(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            assert await client.bind_client("app1", "client-a") is None


class TestUnbindClient:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={}) as mock_req:
            assert await client.unbind_client("app1", "client-a") is True
            mock_req.assert_called_once_with(
                "DELETE", "/platform/saas/app1/clients/client-a", access="admin"
            )

    @pytest.mark.asyncio
    async def test_not_bound_returns_false(self, client):
        error = httpx.HTTPStatusError(
            "404",
            request=httpx.Request("DELETE", "https://billing.example.com/x"),
            response=httpx.Response(404),
        )
        with patch.object(client, "_request", side_effect=error):
            assert await client.unbind_client("app1", "client-a") is False


# =========================================================================
# Pydantic Models
# =========================================================================


class TestPydanticModels:
    def test_saas_app_defaults(self):
        app = SaasApp(
            id="1",
            name="Test",
            slug="test",
            created_at=datetime(2024, 1, 1),
            updated_at=datetime(2024, 1, 2),
        )
        assert app.description is None
        assert app.webhook_url is None
        assert app.is_active is True

    def test_billing_product_defaults(self):
        prod = BillingProduct(
            id="1",
            saas_app_id="app1",
            stripe_product_id="sp1",
            slug="test",
            name="Test",
            created_at=datetime(2024, 1, 1),
            updated_at=datetime(2024, 1, 2),
        )
        assert prod.description is None
        assert prod.extra_data is None
        assert prod.is_active is True

    def test_billing_price_defaults(self):
        price = BillingPrice(
            id="1",
            product_id="prod1",
            stripe_price_id="sp1",
            created_at=datetime(2024, 1, 1),
            updated_at=datetime(2024, 1, 2),
        )
        assert price.nickname is None
        assert price.currency == "usd"
        assert price.billing_type == "recurring"
        assert price.usage_type == "licensed"
        assert price.recurring_interval_count == 1

    def test_subscription_defaults(self):
        sub = Subscription(
            id="1",
            customer_id="c1",
            stripe_subscription_id="ss1",
            status="active",
            created_at=datetime(2024, 1, 1),
            updated_at=datetime(2024, 1, 2),
        )
        assert sub.price_id is None
        assert sub.cancel_at_period_end is False
        assert sub.canceled_at is None

    def test_customer_portal(self):
        portal = CustomerPortal(url="https://billing.stripe.com/session/xxx")
        assert portal.url == "https://billing.stripe.com/session/xxx"
