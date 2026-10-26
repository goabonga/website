# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for billing operations tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import team.services.tools  # noqa: F401
from team.services.tool_service import ToolService


def _mock_context(*, base_url="http://billing.internal", token="tok-billing"):
    service = ToolService()
    mock_client = AsyncMock()
    service._client = mock_client
    ctx = {
        "tool_service": service,
        "agent_config": {
            "credentials": {
                "billing_base_url": base_url,
                "billing_token": token,
            },
        },
    }
    return ctx, mock_client


def _json_response(status_code, data=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data if data is not None else {}
    resp.text = text
    return resp


# --- billing_list_subscriptions ---


class TestBillingListSubscriptions:
    async def test_success(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(
            return_value=_json_response(200, [{"id": "sub_1", "status": "active"}])
        )
        result = await ToolService._registry["billing_list_subscriptions"][0](
            {"saas_id": "app1"}, ctx
        )
        assert isinstance(result, list)
        assert result[0]["id"] == "sub_1"
        call_url = client.get.call_args[0][0]
        assert "/platform/app1/subscriptions" in call_url

    async def test_with_filters(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_json_response(200, []))
        await ToolService._registry["billing_list_subscriptions"][0](
            {"saas_id": "app1", "status_filter": "active", "limit": 10}, ctx
        )
        call_params = client.get.call_args[1]["params"]
        assert call_params["status"] == "active"
        assert call_params["limit"] == 10

    async def test_api_error(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_json_response(500, text="Server Error"))
        result = await ToolService._registry["billing_list_subscriptions"][0](
            {"saas_id": "app1"}, ctx
        )
        assert "error" in result
        assert "500" in result["error"]

    async def test_no_base_url(self):
        ctx, _ = _mock_context(base_url="")
        result = await ToolService._registry["billing_list_subscriptions"][0](
            {"saas_id": "app1"}, ctx
        )
        assert "not configured" in result["error"]

    async def test_falls_back_to_global_settings(self):
        service = ToolService()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_json_response(200, []))
        service._client = mock_client

        ctx = {"tool_service": service, "agent_config": {"credentials": {}}}
        with patch("team.services.tools.billing_ops.get_settings") as m:
            m.return_value.billing_base_url = "http://global-billing:8000"
            m.return_value.oauth2_client_secret = "global-secret"
            result = await ToolService._registry["billing_list_subscriptions"][0](
                {"saas_id": "app1"}, ctx
            )
        assert isinstance(result, list)
        call_url = mock_client.get.call_args[0][0]
        assert "global-billing" in call_url

    async def test_unix_socket(self):
        ctx, _ = _mock_context(base_url="unix:///run/billing/billing.sock")
        with patch("team.services.tools._http.httpx") as mock_httpx:
            mock_uds_client = AsyncMock()
            mock_uds_client.get = AsyncMock(return_value=_json_response(200, []))
            mock_uds_client.aclose = AsyncMock()
            mock_httpx.AsyncHTTPTransport.return_value = AsyncMock()
            mock_httpx.AsyncClient.return_value = mock_uds_client

            result = await ToolService._registry["billing_list_subscriptions"][0](
                {"saas_id": "app1"}, ctx
            )
        assert isinstance(result, list)
        call_url = mock_uds_client.get.call_args[0][0]
        assert call_url.startswith("http://localhost")
        mock_uds_client.aclose.assert_awaited_once()


# --- billing_get_customer ---


class TestBillingGetCustomer:
    async def test_success(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(
            return_value=_json_response(200, {"id": "cus_1", "email": "a@b.com"})
        )
        result = await ToolService._registry["billing_get_customer"][0](
            {"saas_id": "app1", "customer_id": "cus_1"}, ctx
        )
        assert result["id"] == "cus_1"
        call_url = client.get.call_args[0][0]
        assert "/customers/cus_1" in call_url

    async def test_not_found(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_json_response(404, text="Not Found"))
        result = await ToolService._registry["billing_get_customer"][0](
            {"saas_id": "app1", "customer_id": "missing"}, ctx
        )
        assert "error" in result
        assert "404" in result["error"]

    async def test_no_base_url(self):
        ctx, _ = _mock_context(base_url="")
        result = await ToolService._registry["billing_get_customer"][0](
            {"saas_id": "app1", "customer_id": "cus_1"}, ctx
        )
        assert "not configured" in result["error"]

    async def test_unix_socket(self):
        ctx, _ = _mock_context(base_url="unix:///run/billing/billing.sock")
        with patch("team.services.tools._http.httpx") as mock_httpx:
            mock_uds_client = AsyncMock()
            mock_uds_client.get = AsyncMock(return_value=_json_response(200, {"id": "cus_1"}))
            mock_uds_client.aclose = AsyncMock()
            mock_httpx.AsyncHTTPTransport.return_value = AsyncMock()
            mock_httpx.AsyncClient.return_value = mock_uds_client

            result = await ToolService._registry["billing_get_customer"][0](
                {"saas_id": "app1", "customer_id": "cus_1"}, ctx
            )
        assert result["id"] == "cus_1"
        mock_uds_client.aclose.assert_awaited_once()


# --- billing_report_usage ---


class TestBillingReportUsage:
    async def test_success(self):
        ctx, client = _mock_context()
        client.post = AsyncMock(return_value=_json_response(201, {"recorded": True}))
        result = await ToolService._registry["billing_report_usage"][0](
            {"saas_id": "app1", "subscription_id": "sub_1", "quantity": 5}, ctx
        )
        assert result["recorded"] is True
        payload = client.post.call_args[1]["json"]
        assert payload["subscription_id"] == "sub_1"
        assert payload["quantity"] == 5

    async def test_with_action(self):
        ctx, client = _mock_context()
        client.post = AsyncMock(return_value=_json_response(200, {"recorded": True}))
        await ToolService._registry["billing_report_usage"][0](
            {"saas_id": "app1", "subscription_id": "sub_1", "quantity": 1, "action": "set"},
            ctx,
        )
        payload = client.post.call_args[1]["json"]
        assert payload["action"] == "set"

    async def test_api_error(self):
        ctx, client = _mock_context()
        client.post = AsyncMock(return_value=_json_response(422, text="Invalid"))
        result = await ToolService._registry["billing_report_usage"][0](
            {"saas_id": "app1", "subscription_id": "sub_1", "quantity": 5}, ctx
        )
        assert "error" in result

    async def test_no_base_url(self):
        ctx, _ = _mock_context(base_url="")
        result = await ToolService._registry["billing_report_usage"][0](
            {"saas_id": "app1", "subscription_id": "sub_1", "quantity": 5}, ctx
        )
        assert "not configured" in result["error"]

    async def test_unix_socket(self):
        ctx, _ = _mock_context(base_url="unix:///run/billing/billing.sock")
        with patch("team.services.tools._http.httpx") as mock_httpx:
            mock_uds_client = AsyncMock()
            mock_uds_client.post = AsyncMock(return_value=_json_response(201, {"recorded": True}))
            mock_uds_client.aclose = AsyncMock()
            mock_httpx.AsyncHTTPTransport.return_value = AsyncMock()
            mock_httpx.AsyncClient.return_value = mock_uds_client

            result = await ToolService._registry["billing_report_usage"][0](
                {"saas_id": "app1", "subscription_id": "sub_1", "quantity": 5}, ctx
            )
        assert result["recorded"] is True
        mock_uds_client.aclose.assert_awaited_once()


# --- billing_get_subscription ---


class TestBillingGetSubscription:
    async def test_success(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(
            return_value=_json_response(200, {"id": "sub_1", "status": "active"})
        )
        result = await ToolService._registry["billing_get_subscription"][0](
            {"saas_id": "app1", "subscription_id": "sub_1"}, ctx
        )
        assert result["id"] == "sub_1"
        call_url = client.get.call_args[0][0]
        assert "/subscriptions/sub_1" in call_url

    async def test_api_error(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_json_response(500, text="Error"))
        result = await ToolService._registry["billing_get_subscription"][0](
            {"saas_id": "app1", "subscription_id": "sub_1"}, ctx
        )
        assert "error" in result

    async def test_no_base_url(self):
        ctx, _ = _mock_context(base_url="")
        result = await ToolService._registry["billing_get_subscription"][0](
            {"saas_id": "app1", "subscription_id": "sub_1"}, ctx
        )
        assert "not configured" in result["error"]

    async def test_unix_socket(self):
        ctx, _ = _mock_context(base_url="unix:///run/billing/billing.sock")
        with patch("team.services.tools._http.httpx") as mock_httpx:
            mock_uds_client = AsyncMock()
            mock_uds_client.get = AsyncMock(return_value=_json_response(200, {"id": "sub_1"}))
            mock_uds_client.aclose = AsyncMock()
            mock_httpx.AsyncHTTPTransport.return_value = AsyncMock()
            mock_httpx.AsyncClient.return_value = mock_uds_client

            result = await ToolService._registry["billing_get_subscription"][0](
                {"saas_id": "app1", "subscription_id": "sub_1"}, ctx
            )
        assert result["id"] == "sub_1"
        mock_uds_client.aclose.assert_awaited_once()
