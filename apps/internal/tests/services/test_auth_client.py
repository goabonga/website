# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth API client."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from internal.services.auth_client import AuthClient, UserInfo


@pytest.fixture
def client():
    with patch("internal.services.auth_client.settings") as s:
        s.oauth2_issuer = "https://auth.example.com"
        s.oauth2_client_id = "test-client"
        s.oauth2_client_secret = "test-secret"
        yield AuthClient()


def _token_response(token="test-token"):
    return httpx.Response(
        200,
        json={"access_token": token, "expires_in": 3600},
        request=httpx.Request("POST", "https://auth.example.com/oauth2/token"),
    )


class TestGetAccessToken:
    @pytest.mark.asyncio
    async def test_fetches_new_token(self, client):
        mock_http = AsyncMock()
        mock_http.post.return_value = _token_response("fresh-token")

        with patch("internal.services.auth_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            token = await client._get_access_token()
            assert token == "fresh-token"

    @pytest.mark.asyncio
    async def test_returns_cached_token(self, client):
        client._access_token = "cached-token"
        client._token_expires_at = datetime.now(UTC) + timedelta(hours=1)
        token = await client._get_access_token()
        assert token == "cached-token"

    @pytest.mark.asyncio
    async def test_refreshes_near_expiry(self, client):
        client._access_token = "old-token"
        client._token_expires_at = datetime.now(UTC) + timedelta(seconds=10)

        mock_http = AsyncMock()
        mock_http.post.return_value = _token_response("new-token")

        with patch("internal.services.auth_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            token = await client._get_access_token()
            assert token == "new-token"

    @pytest.mark.asyncio
    async def test_raises_when_no_issuer(self):
        with patch("internal.services.auth_client.settings") as s:
            s.oauth2_issuer = ""
            s.oauth2_client_id = "test"
            s.oauth2_client_secret = "test"
            c = AuthClient()
            with pytest.raises(ValueError, match="oauth2_issuer not configured"):
                await c._get_access_token()


class TestGetUser:
    @pytest.mark.asyncio
    async def test_success(self, client):
        user_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        client._access_token = "token"
        client._token_expires_at = datetime.now(UTC) + timedelta(hours=1)

        user_response = httpx.Response(
            200,
            json={
                "user": {
                    "id": str(user_id),
                    "email": "user@example.com",
                    "profile": {"name": "Test User"},
                    "is_active": True,
                    "created_at": "2024-01-01T00:00:00Z",
                }
            },
            request=httpx.Request("GET", f"https://auth.example.com/admin/api/users/{user_id}"),
        )

        mock_http = AsyncMock()
        mock_http.get.return_value = user_response

        with patch("internal.services.auth_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            user = await client.get_user(user_id)
            assert user is not None
            assert user.id == user_id
            assert user.email == "user@example.com"
            assert user.name == "Test User"

    @pytest.mark.asyncio
    async def test_user_404(self, client):
        user_id = uuid.uuid4()
        client._access_token = "token"
        client._token_expires_at = datetime.now(UTC) + timedelta(hours=1)

        mock_http = AsyncMock()
        mock_http.get.return_value = httpx.Response(
            404,
            request=httpx.Request("GET", f"https://auth.example.com/admin/api/users/{user_id}"),
        )

        with patch("internal.services.auth_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            user = await client.get_user(user_id)
            assert user is None

    @pytest.mark.asyncio
    async def test_returns_none_when_not_configured(self):
        with patch("internal.services.auth_client.settings") as s:
            s.oauth2_issuer = ""
            s.oauth2_client_id = ""
            s.oauth2_client_secret = ""
            c = AuthClient()
            result = await c.get_user(uuid.uuid4())
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_token_error(self, client):
        with patch.object(client, "_get_access_token", side_effect=Exception("token error")):
            result = await client.get_user(uuid.uuid4())
            assert result is None

    @pytest.mark.asyncio
    async def test_non_200_status(self, client):
        user_id = uuid.uuid4()
        client._access_token = "token"
        client._token_expires_at = datetime.now(UTC) + timedelta(hours=1)

        mock_http = AsyncMock()
        mock_http.get.return_value = httpx.Response(
            500,
            text="Internal Server Error",
            request=httpx.Request("GET", f"https://auth.example.com/admin/api/users/{user_id}"),
        )

        with patch("internal.services.auth_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            user = await client.get_user(user_id)
            assert user is None

    @pytest.mark.asyncio
    async def test_http_exception_returns_none(self, client):
        user_id = uuid.uuid4()
        client._access_token = "token"
        client._token_expires_at = datetime.now(UTC) + timedelta(hours=1)

        mock_http = AsyncMock()
        mock_http.get.side_effect = httpx.ConnectError("connection refused")

        with patch("internal.services.auth_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            user = await client.get_user(user_id)
            assert user is None


class TestUserInfo:
    def test_model_creation(self):
        info = UserInfo(
            id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
            email="test@example.com",
            name="Test",
            is_active=True,
        )
        assert info.email == "test@example.com"
        assert info.is_active is True

    def test_optional_fields(self):
        info = UserInfo(id=uuid.uuid4())
        assert info.email is None
        assert info.name is None
        assert info.is_active is True
        assert info.created_at is None
