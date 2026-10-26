# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for service_call tool."""

from unittest.mock import AsyncMock, MagicMock, patch

import team.services.tools  # noqa: F401
from team.services.tool_service import ToolService


def _mock_context(*, base_url="http://services:8000", api_key=""):
    service = ToolService()
    mock_client = AsyncMock()
    service._client = mock_client
    ctx = {
        "tool_service": service,
        "agent_config": {
            "credentials": {
                "services_base_url": base_url,
                "services_api_key": api_key,
            },
        },
    }
    return ctx, mock_client


class TestServiceCall:
    async def test_call_success(self):
        ctx, client = _mock_context()
        resp = MagicMock()
        resp.status_code = 200
        resp.text = '{"sent": true}'
        client.request = AsyncMock(return_value=resp)

        result = await ToolService._registry["service_call"][0](
            {"service": "mailer", "endpoint": "send", "method": "POST", "body": {"to": "a@b.com"}},
            ctx,
        )
        assert result["status_code"] == 200
        # Verify URL construction
        call_args = client.request.call_args
        assert call_args[0] == ("POST", "http://services:8000/mailer/send")

    async def test_call_strips_leading_slash(self):
        ctx, client = _mock_context()
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "OK"
        client.request = AsyncMock(return_value=resp)

        await ToolService._registry["service_call"][0](
            {"service": "analytics", "endpoint": "/track"},
            ctx,
        )
        call_args = client.request.call_args
        assert call_args[0] == ("GET", "http://services:8000/analytics/track")

    async def test_call_with_api_key(self):
        ctx, client = _mock_context(api_key="sk-service-123")
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "OK"
        client.request = AsyncMock(return_value=resp)

        await ToolService._registry["service_call"][0](
            {"service": "mailer", "endpoint": "status"},
            ctx,
        )
        headers = client.request.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer sk-service-123"

    async def test_call_api_key_does_not_override_explicit_header(self):
        ctx, client = _mock_context(api_key="sk-service-123")
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "OK"
        client.request = AsyncMock(return_value=resp)

        await ToolService._registry["service_call"][0](
            {
                "service": "mailer",
                "endpoint": "status",
                "headers": {"Authorization": "Bearer custom"},
            },
            ctx,
        )
        headers = client.request.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer custom"

    async def test_call_no_base_url(self):
        ctx, _ = _mock_context(base_url="")
        result = await ToolService._registry["service_call"][0](
            {"service": "mailer", "endpoint": "send"},
            ctx,
        )
        assert "not configured" in result["error"]

    async def test_call_falls_back_to_global_settings(self):
        service = ToolService()
        mock_client = AsyncMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "OK"
        mock_client.request = AsyncMock(return_value=resp)
        service._client = mock_client

        ctx = {"tool_service": service, "agent_config": {"credentials": {}}}
        with patch("team.services.tools.service_call.get_settings") as m:
            m.return_value.services_base_url = "http://global:9000"
            result = await ToolService._registry["service_call"][0](
                {"service": "analytics", "endpoint": "track"},
                ctx,
            )
        assert result["status_code"] == 200
        call_url = mock_client.request.call_args[0][1]
        assert "global:9000" in call_url

    async def test_call_truncates_body(self):
        ctx, client = _mock_context()
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "x" * 5000
        client.request = AsyncMock(return_value=resp)

        result = await ToolService._registry["service_call"][0](
            {"service": "mailer", "endpoint": "send"},
            ctx,
        )
        assert len(result["body"]) == 4000

    async def test_call_unix_socket(self):
        ctx, _ = _mock_context(base_url="unix:///run/services/services.sock")
        with patch("team.services.tools._http.httpx") as mock_httpx:
            mock_uds_client = AsyncMock()
            resp = MagicMock()
            resp.status_code = 200
            resp.text = '{"ok": true}'
            mock_uds_client.request = AsyncMock(return_value=resp)
            mock_uds_client.aclose = AsyncMock()
            mock_httpx.AsyncHTTPTransport.return_value = AsyncMock()
            mock_httpx.AsyncClient.return_value = mock_uds_client

            result = await ToolService._registry["service_call"][0](
                {"service": "mailer", "endpoint": "send"},
                ctx,
            )
        assert result["status_code"] == 200
        call_url = mock_uds_client.request.call_args[0][1]
        assert call_url == "http://localhost/mailer/send"
        mock_uds_client.aclose.assert_awaited_once()
