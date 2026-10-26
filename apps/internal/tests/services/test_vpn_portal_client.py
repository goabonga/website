# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for VPN Portal API client."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from internal.services.vpn_portal_client import VPNPortalClient, VPNSessionsResponse


@pytest.fixture
def client():
    with patch("internal.services.vpn_portal_client.settings") as s:
        s.vpn_portal_api_url = "https://vpn.example.com"
        s.oauth2_client_id = "test-client"
        s.oauth2_client_secret = "test-secret"
        s.oauth2_issuer = "https://auth.example.com"
        yield VPNPortalClient()


def _token_response(token="test-token"):
    return httpx.Response(
        200,
        json={"access_token": token, "expires_in": 3600},
        request=httpx.Request("POST", "https://auth.example.com/oauth2/token"),
    )


class TestGetSessions:
    @pytest.mark.asyncio
    async def test_success(self, client):
        sessions_data = {
            "sessions": [
                {
                    "id": "sess-1",
                    "user_id": "user-1",
                    "username": "testuser",
                    "device_name": "laptop",
                    "connected_at": "2024-01-01T00:00:00Z",
                    "assigned_ip": "10.0.0.2",
                    "certificate_serial": "ABC123",
                    "expires_at": "2024-01-02T00:00:00Z",
                    "scopes": ["vpn:connect"],
                    "routes": ["10.0.0.0/24"],
                }
            ],
            "total": 1,
            "page": 1,
            "per_page": 50,
        }
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=sessions_data):
            result = await client.get_sessions()
            assert result is not None
            assert isinstance(result, VPNSessionsResponse)
            assert result.total == 1
            assert result.sessions[0].username == "testuser"

    @pytest.mark.asyncio
    async def test_error_returns_none(self, client):
        with patch.object(client, "_request", side_effect=Exception("connection error")):
            result = await client.get_sessions()
            assert result is None


class TestRevokeSession:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=None):
            result = await client.revoke_session("ABC123")
            assert result is True

    @pytest.mark.asyncio
    async def test_not_found(self, client):
        error_response = httpx.Response(
            404,
            request=httpx.Request("DELETE", "https://vpn.example.com/api/v1/admin/sessions/ABC123"),
        )
        with patch.object(
            client,
            "_request",
            side_effect=httpx.HTTPStatusError(
                "404", request=error_response.request, response=error_response
            ),
        ):
            result = await client.revoke_session("ABC123")
            assert result is False

    @pytest.mark.asyncio
    async def test_generic_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.revoke_session("ABC123")
            assert result is False


class TestTokenCaching:
    @pytest.mark.asyncio
    async def test_returns_cached_token(self, client):
        client._access_token = "cached-token"
        client._token_expires_at = datetime.now(UTC) + timedelta(hours=1)
        token = await client._get_access_token()
        assert token == "cached-token"

    @pytest.mark.asyncio
    async def test_fetches_new_when_expired(self, client):
        client._access_token = "old"
        client._token_expires_at = datetime.now(UTC) - timedelta(hours=1)

        mock_http = AsyncMock()
        mock_http.post.return_value = _token_response("new-token")

        with patch("internal.services.vpn_portal_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            token = await client._get_access_token()
            assert token == "new-token"


class TestGetAccessTokenIssuerCheck:
    @pytest.mark.asyncio
    async def test_raises_when_no_issuer(self):
        with patch("internal.services.vpn_portal_client.settings") as s:
            s.vpn_portal_api_url = "https://vpn.example.com"
            s.oauth2_client_id = "test"
            s.oauth2_client_secret = "test"
            s.oauth2_issuer = ""
            c = VPNPortalClient()
            with pytest.raises(ValueError, match="oauth2_issuer not configured"):
                await c._get_access_token()


class TestRequestMethod:
    @pytest.mark.asyncio
    async def test_raises_when_not_configured(self):
        with patch("internal.services.vpn_portal_client.settings") as s:
            s.vpn_portal_api_url = ""
            s.oauth2_client_id = "test"
            s.oauth2_client_secret = "test"
            s.oauth2_issuer = "https://auth.example.com"
            c = VPNPortalClient()
            with pytest.raises(ValueError, match="vpn_portal_api_url not configured"):
                await c._request("GET", "/test")

    @pytest.mark.asyncio
    async def test_full_request_flow(self, client):
        client._access_token = "token"
        client._token_expires_at = datetime.now(UTC) + timedelta(hours=1)

        mock_http = AsyncMock()
        mock_http.request.return_value = httpx.Response(
            200,
            json={"data": "value"},
            request=httpx.Request("GET", "https://vpn.example.com/api/v1/test"),
        )

        with patch("internal.services.vpn_portal_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client._request("GET", "/api/v1/test")
            assert result == {"data": "value"}

    @pytest.mark.asyncio
    async def test_request_204_returns_none(self, client):
        client._access_token = "token"
        client._token_expires_at = datetime.now(UTC) + timedelta(hours=1)

        mock_http = AsyncMock()
        mock_http.request.return_value = httpx.Response(
            204,
            request=httpx.Request("DELETE", "https://vpn.example.com/api/v1/test"),
        )

        with patch("internal.services.vpn_portal_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client._request("DELETE", "/api/v1/test")
            assert result is None

    @pytest.mark.asyncio
    async def test_request_propagates_token_error(self, client):
        with (
            patch.object(
                client, "_get_access_token", side_effect=ValueError("oauth2_issuer not configured")
            ),
            pytest.raises(ValueError, match="oauth2_issuer not configured"),
        ):
            await client._request("GET", "/test")


class TestRevokeSessionNon404:
    @pytest.mark.asyncio
    async def test_non_404_http_error(self, client):
        error_response = httpx.Response(
            500,
            request=httpx.Request("DELETE", "https://vpn.example.com/api/v1/admin/sessions/ABC123"),
        )
        with patch.object(
            client,
            "_request",
            side_effect=httpx.HTTPStatusError(
                "500", request=error_response.request, response=error_response
            ),
        ):
            result = await client.revoke_session("ABC123")
            assert result is False
