# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for Token Exchange client."""

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from internal.services.token_exchange import TokenExchangeClient, TokenExchangeError


@pytest.fixture
def client():
    with patch("internal.services.token_exchange.settings") as s:
        s.oauth2_client_id = "test-client"
        s.oauth2_client_secret = "test-secret"
        s.oauth2_issuer = "https://auth.example.com"
        s.redis_url = "redis://localhost:6379/0"
        s.oauth2_client_cache_ttl = 300
        c = TokenExchangeClient()
        c._http_client = AsyncMock()
        c._redis_client = None
        yield c


class TestIsConfigured:
    def test_configured(self):
        with patch("internal.services.token_exchange.settings") as s:
            s.oauth2_client_id = "id"
            s.oauth2_client_secret = "secret"
            s.oauth2_issuer = "https://auth.example.com"
            c = TokenExchangeClient()
            assert c.is_configured is True

    def test_not_configured_missing_id(self):
        with patch("internal.services.token_exchange.settings") as s:
            s.oauth2_client_id = ""
            s.oauth2_client_secret = "secret"
            s.oauth2_issuer = "https://auth.example.com"
            c = TokenExchangeClient()
            assert c.is_configured is False

    def test_not_configured_missing_issuer(self):
        with patch("internal.services.token_exchange.settings") as s:
            s.oauth2_client_id = "id"
            s.oauth2_client_secret = "secret"
            s.oauth2_issuer = ""
            c = TokenExchangeClient()
            assert c.is_configured is False


class TestExchangeToken:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {
            "access_token": "exchanged-token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "knowledge:read",
        }
        client._http_client.post.return_value = httpx.Response(
            200,
            json=expected,
            request=httpx.Request("POST", "https://auth.example.com/oauth2/token"),
        )

        result = await client.exchange_token("user-token", ["knowledge:read"])
        assert result["access_token"] == "exchanged-token"

    @pytest.mark.asyncio
    async def test_error_response(self, client):
        client._http_client.post.return_value = httpx.Response(
            400,
            json={"error": "invalid_grant", "error_description": "Token expired"},
            request=httpx.Request("POST", "https://auth.example.com/oauth2/token"),
        )

        with pytest.raises(TokenExchangeError) as exc_info:
            await client.exchange_token("bad-token")
        assert "invalid_grant" in str(exc_info.value)
        assert exc_info.value.error_code == "invalid_grant"

    @pytest.mark.asyncio
    async def test_error_response_wrapped_in_detail(self, client):
        # The auth server returns OAuth2 errors as FastAPI's {"detail": {...}}
        client._http_client.post.return_value = httpx.Response(
            400,
            json={
                "detail": {
                    "error": "insufficient_scope",
                    "error_description": "User does not have permission",
                }
            },
            request=httpx.Request("POST", "https://auth.example.com/oauth2/token"),
        )

        with pytest.raises(TokenExchangeError) as exc_info:
            await client.exchange_token("user-token", ["knowledge:read"])
        assert exc_info.value.error_code == "insufficient_scope"
        assert "User does not have permission" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_not_configured_raises(self):
        with patch("internal.services.token_exchange.settings") as s:
            s.oauth2_client_id = ""
            s.oauth2_client_secret = ""
            s.oauth2_issuer = ""
            s.redis_url = ""
            c = TokenExchangeClient()
            with pytest.raises(TokenExchangeError, match="not configured"):
                await c.exchange_token("token")


class TestCaching:
    @pytest.mark.asyncio
    async def test_cache_hit(self, client):
        cached_result = json.dumps(
            {
                "access_token": "cached-token",
                "scope": "knowledge:read",
            }
        )
        mock_redis = AsyncMock()
        mock_redis.get.return_value = cached_result
        client._redis_client = mock_redis

        result = await client.exchange_token("user-token", ["knowledge:read"])
        assert result["access_token"] == "cached-token"
        client._http_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_fetches_and_caches(self, client):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_redis.setex.return_value = True
        client._redis_client = mock_redis

        expected = {"access_token": "new-token", "scope": "knowledge:read"}
        client._http_client.post.return_value = httpx.Response(
            200,
            json=expected,
            request=httpx.Request("POST", "https://auth.example.com/oauth2/token"),
        )

        result = await client.exchange_token("user-token", ["knowledge:read"])
        assert result["access_token"] == "new-token"
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_redis_error_still_works(self, client):
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = Exception("Redis down")
        mock_redis.setex.side_effect = Exception("Redis down")
        client._redis_client = mock_redis

        expected = {"access_token": "token", "scope": "knowledge:read"}
        client._http_client.post.return_value = httpx.Response(
            200,
            json=expected,
            request=httpx.Request("POST", "https://auth.example.com/oauth2/token"),
        )

        result = await client.exchange_token("user-token", ["knowledge:read"])
        assert result["access_token"] == "token"


class TestValidateTokenScopes:
    @pytest.mark.asyncio
    async def test_delegates_to_exchange(self, client):
        expected = {"access_token": "token", "scope": "knowledge:read"}
        client._http_client.post.return_value = httpx.Response(
            200,
            json=expected,
            request=httpx.Request("POST", "https://auth.example.com/oauth2/token"),
        )

        result = await client.validate_token_scopes("user-token", ["knowledge:read"])
        assert result["access_token"] == "token"


class TestCacheKey:
    def test_deterministic(self):
        with patch("internal.services.token_exchange.settings") as s:
            s.oauth2_client_id = "id"
            s.oauth2_client_secret = "secret"
            s.oauth2_issuer = "https://auth.example.com"
            s.redis_url = ""
            c = TokenExchangeClient()
            key1 = c._cache_key("token", ["scope1", "scope2"])
            key2 = c._cache_key("token", ["scope1", "scope2"])
            assert key1 == key2

    def test_different_scopes_different_keys(self):
        with patch("internal.services.token_exchange.settings") as s:
            s.oauth2_client_id = "id"
            s.oauth2_client_secret = "secret"
            s.oauth2_issuer = "https://auth.example.com"
            s.redis_url = ""
            c = TokenExchangeClient()
            key1 = c._cache_key("token", ["scope1"])
            key2 = c._cache_key("token", ["scope2"])
            assert key1 != key2

    def test_scope_order_irrelevant(self):
        with patch("internal.services.token_exchange.settings") as s:
            s.oauth2_client_id = "id"
            s.oauth2_client_secret = "secret"
            s.oauth2_issuer = "https://auth.example.com"
            s.redis_url = ""
            c = TokenExchangeClient()
            key1 = c._cache_key("token", ["a", "b"])
            key2 = c._cache_key("token", ["b", "a"])
            assert key1 == key2


class TestGetHttpClient:
    @pytest.mark.asyncio
    async def test_creates_client_when_none(self):
        with patch("internal.services.token_exchange.settings") as s:
            s.oauth2_client_id = "id"
            s.oauth2_client_secret = "secret"
            s.oauth2_issuer = "https://auth.example.com"
            s.redis_url = ""
            c = TokenExchangeClient()
            c._http_client = None
            http_client = await c._get_http_client()
            assert http_client is not None
            assert c._http_client is http_client
            await c.close()

    @pytest.mark.asyncio
    async def test_returns_existing_client(self, client):
        existing = client._http_client
        result = await client._get_http_client()
        assert result is existing


class TestGetRedisClient:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_redis_url(self):
        with patch("internal.services.token_exchange.settings") as s:
            s.oauth2_client_id = "id"
            s.oauth2_client_secret = "secret"
            s.oauth2_issuer = "https://auth.example.com"
            s.redis_url = ""
            c = TokenExchangeClient()
            result = await c._get_redis_client()
            assert result is None

    @pytest.mark.asyncio
    async def test_creates_redis_when_configured(self):
        with (
            patch("internal.services.token_exchange.settings") as s,
            patch("internal.services.token_exchange.redis") as mock_redis,
        ):
            s.oauth2_client_id = "id"
            s.oauth2_client_secret = "secret"
            s.oauth2_issuer = "https://auth.example.com"
            s.redis_url = "redis://localhost:6379/0"
            mock_redis.from_url.return_value = AsyncMock()
            c = TokenExchangeClient()
            result = await c._get_redis_client()
            assert result is not None
            mock_redis.from_url.assert_called_once()


class TestIssuerProperty:
    def test_returns_stripped_issuer(self):
        with patch("internal.services.token_exchange.settings") as s:
            s.oauth2_client_id = "id"
            s.oauth2_client_secret = "secret"
            s.oauth2_issuer = "https://auth.example.com/"
            c = TokenExchangeClient()
            assert c.issuer == "https://auth.example.com"


class TestGetCached:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_redis(self, client):
        client._redis_client = None
        with patch("internal.services.token_exchange.settings") as s:
            s.redis_url = ""
            result = await client._get_cached("token", ["scope"])
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_cache_miss(self, client):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        client._redis_client = mock_redis
        result = await client._get_cached("token", ["scope"])
        assert result is None


class TestSetCached:
    @pytest.mark.asyncio
    async def test_skips_when_no_redis(self, client):
        client._redis_client = None
        with patch("internal.services.token_exchange.settings") as s:
            s.redis_url = ""
            await client._set_cached("token", ["scope"], {"result": "data"})


class TestExchangeTokenErrorParsing:
    @pytest.mark.asyncio
    async def test_error_without_json_body(self, client):
        client._http_client.post.return_value = httpx.Response(
            400,
            content=b"",
            request=httpx.Request("POST", "https://auth.example.com/oauth2/token"),
        )
        with pytest.raises(TokenExchangeError):
            await client.exchange_token("bad-token")

    @pytest.mark.asyncio
    async def test_error_with_invalid_json_body(self, client):
        client._http_client.post.return_value = httpx.Response(
            400,
            content=b"not json at all",
            request=httpx.Request("POST", "https://auth.example.com/oauth2/token"),
            headers={"content-type": "text/plain"},
        )
        with pytest.raises(TokenExchangeError) as exc_info:
            await client.exchange_token("bad-token")
        assert exc_info.value.error_code == "unknown_error"


class TestClose:
    @pytest.mark.asyncio
    async def test_closes_clients(self, client):
        mock_http = AsyncMock()
        mock_redis = AsyncMock()
        client._http_client = mock_http
        client._redis_client = mock_redis

        await client.close()
        mock_http.aclose.assert_called_once()
        mock_redis.aclose.assert_called_once()
        assert client._http_client is None
        assert client._redis_client is None

    @pytest.mark.asyncio
    async def test_close_when_no_clients(self):
        with patch("internal.services.token_exchange.settings") as s:
            s.oauth2_client_id = "id"
            s.oauth2_client_secret = "secret"
            s.oauth2_issuer = "https://auth.example.com"
            s.redis_url = ""
            c = TokenExchangeClient()
            await c.close()  # Should not raise
