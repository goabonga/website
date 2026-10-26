# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the shared _http helper (Unix socket + HTTP support)."""

from unittest.mock import AsyncMock, patch

from team.services.tool_service import ToolService
from team.services.tools._http import get_service_client


class TestGetServiceClient:
    async def test_http_url_uses_tool_service_client(self):
        service = ToolService()
        mock_client = AsyncMock()
        service._client = mock_client

        client, effective_url, should_close = await get_service_client(
            service, "http://billing.internal"
        )
        assert client is mock_client
        assert effective_url == "http://billing.internal"
        assert should_close is False

    async def test_unix_socket_creates_dedicated_client(self):
        service = ToolService()

        with patch("team.services.tools._http.httpx") as mock_httpx:
            mock_transport = AsyncMock()
            mock_httpx.AsyncHTTPTransport.return_value = mock_transport
            mock_uds_client = AsyncMock()
            mock_httpx.AsyncClient.return_value = mock_uds_client

            client, effective_url, should_close = await get_service_client(
                service, "unix:///run/billing/billing.sock"
            )

        assert client is mock_uds_client
        assert effective_url == "http://localhost"
        assert should_close is True
        mock_httpx.AsyncHTTPTransport.assert_called_once_with(uds="/run/billing/billing.sock")
        mock_httpx.AsyncClient.assert_called_once_with(transport=mock_transport)

    async def test_https_url_uses_tool_service_client(self):
        service = ToolService()
        mock_client = AsyncMock()
        service._client = mock_client

        client, effective_url, should_close = await get_service_client(
            service, "https://billing.goabonga.com"
        )
        assert client is mock_client
        assert effective_url == "https://billing.goabonga.com"
        assert should_close is False
