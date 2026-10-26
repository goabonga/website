# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for analytics operations tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import team.services.tools  # noqa: F401
from team.services.tool_service import ToolService


def _mock_context(*, base_url="http://analytics.internal", token="tok-analytics"):
    service = ToolService()
    mock_client = AsyncMock()
    service._client = mock_client
    ctx = {
        "tool_service": service,
        "agent_config": {
            "credentials": {
                "analytics_base_url": base_url,
                "analytics_token": token,
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


# --- analytics_overview ---


class TestAnalyticsOverview:
    async def test_success(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(
            return_value=_json_response(200, {"sessions": 500, "visitors": 300, "pageviews": 1200})
        )
        result = await ToolService._registry["analytics_overview"][0]({}, ctx)
        assert result["sessions"] == 500
        call_url = client.get.call_args[0][0]
        assert "/api/v1/stats/overview" in call_url

    async def test_with_days(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_json_response(200, {}))
        await ToolService._registry["analytics_overview"][0]({"days": 7}, ctx)
        call_params = client.get.call_args[1]["params"]
        assert call_params["days"] == 7

    async def test_api_error(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_json_response(500, text="Error"))
        result = await ToolService._registry["analytics_overview"][0]({}, ctx)
        assert "error" in result
        assert "500" in result["error"]

    async def test_no_base_url(self):
        ctx, _ = _mock_context(base_url="")
        result = await ToolService._registry["analytics_overview"][0]({}, ctx)
        assert "not configured" in result["error"]

    async def test_falls_back_to_global_settings(self):
        service = ToolService()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_json_response(200, {"sessions": 1}))
        service._client = mock_client

        ctx = {"tool_service": service, "agent_config": {"credentials": {}}}
        with patch("team.services.tools.analytics_ops.get_settings") as m:
            m.return_value.analytics_base_url = "http://global-analytics:8000"
            m.return_value.oauth2_client_secret = "global-secret"
            result = await ToolService._registry["analytics_overview"][0]({}, ctx)
        assert result["sessions"] == 1

    async def test_unix_socket(self):
        ctx, _ = _mock_context(base_url="unix:///run/analytics/analytics.sock")
        with patch("team.services.tools._http.httpx") as mock_httpx:
            mock_uds_client = AsyncMock()
            mock_uds_client.get = AsyncMock(return_value=_json_response(200, {"sessions": 42}))
            mock_uds_client.aclose = AsyncMock()
            mock_httpx.AsyncHTTPTransport.return_value = AsyncMock()
            mock_httpx.AsyncClient.return_value = mock_uds_client

            result = await ToolService._registry["analytics_overview"][0]({}, ctx)
        assert result["sessions"] == 42
        mock_uds_client.aclose.assert_awaited_once()


# --- analytics_pages ---


class TestAnalyticsPages:
    async def test_success(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(
            return_value=_json_response(200, {"pages": [{"path": "/", "views": 100}]})
        )
        result = await ToolService._registry["analytics_pages"][0]({}, ctx)
        assert "pages" in result
        call_url = client.get.call_args[0][0]
        assert "/api/v1/stats/pages" in call_url

    async def test_with_params(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_json_response(200, {}))
        await ToolService._registry["analytics_pages"][0]({"days": 14, "limit": 5}, ctx)
        call_params = client.get.call_args[1]["params"]
        assert call_params["days"] == 14
        assert call_params["limit"] == 5

    async def test_api_error(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_json_response(403, text="Forbidden"))
        result = await ToolService._registry["analytics_pages"][0]({}, ctx)
        assert "error" in result

    async def test_no_base_url(self):
        ctx, _ = _mock_context(base_url="")
        result = await ToolService._registry["analytics_pages"][0]({}, ctx)
        assert "not configured" in result["error"]

    async def test_unix_socket(self):
        ctx, _ = _mock_context(base_url="unix:///run/analytics/analytics.sock")
        with patch("team.services.tools._http.httpx") as mock_httpx:
            mock_uds_client = AsyncMock()
            mock_uds_client.get = AsyncMock(return_value=_json_response(200, {"pages": []}))
            mock_uds_client.aclose = AsyncMock()
            mock_httpx.AsyncHTTPTransport.return_value = AsyncMock()
            mock_httpx.AsyncClient.return_value = mock_uds_client

            result = await ToolService._registry["analytics_pages"][0]({}, ctx)
        assert "pages" in result
        mock_uds_client.aclose.assert_awaited_once()


# --- analytics_campaigns ---


class TestAnalyticsCampaigns:
    async def test_success(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(
            return_value=_json_response(200, {"campaigns": [{"name": "Launch", "clicks": 50}]})
        )
        result = await ToolService._registry["analytics_campaigns"][0]({}, ctx)
        assert "campaigns" in result
        call_url = client.get.call_args[0][0]
        assert "/api/v1/stats/campaigns" in call_url

    async def test_with_params(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_json_response(200, {}))
        await ToolService._registry["analytics_campaigns"][0](
            {"include_inactive": True, "limit": 10}, ctx
        )
        call_params = client.get.call_args[1]["params"]
        assert call_params["include_inactive"] == "true"
        assert call_params["limit"] == 10

    async def test_api_error(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_json_response(500, text="Error"))
        result = await ToolService._registry["analytics_campaigns"][0]({}, ctx)
        assert "error" in result

    async def test_no_base_url(self):
        ctx, _ = _mock_context(base_url="")
        result = await ToolService._registry["analytics_campaigns"][0]({}, ctx)
        assert "not configured" in result["error"]

    async def test_unix_socket(self):
        ctx, _ = _mock_context(base_url="unix:///run/analytics/analytics.sock")
        with patch("team.services.tools._http.httpx") as mock_httpx:
            mock_uds_client = AsyncMock()
            mock_uds_client.get = AsyncMock(return_value=_json_response(200, {"campaigns": []}))
            mock_uds_client.aclose = AsyncMock()
            mock_httpx.AsyncHTTPTransport.return_value = AsyncMock()
            mock_httpx.AsyncClient.return_value = mock_uds_client

            result = await ToolService._registry["analytics_campaigns"][0]({}, ctx)
        assert "campaigns" in result
        mock_uds_client.aclose.assert_awaited_once()
