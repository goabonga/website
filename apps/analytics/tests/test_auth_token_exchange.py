# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for analytics.auth.token_exchange module."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from analytics.auth.token_exchange import TokenExchangeClient, TokenExchangeError


class TestTokenExchangeError:
    """Tests for TokenExchangeError."""

    def test_message_and_error_code(self):
        err = TokenExchangeError("failed", error_code="invalid_grant")
        assert str(err) == "failed"
        assert err.error_code == "invalid_grant"

    def test_default_error_code(self):
        err = TokenExchangeError("failed")
        assert err.error_code == "exchange_error"


class TestTokenExchangeClient:
    """Tests for TokenExchangeClient class."""

    def test_is_configured_false_without_credentials(self):
        with patch("analytics.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_client_id = ""
            mock_settings.oauth2_client_secret = ""
            mock_settings.oauth2_issuer = ""
            client = TokenExchangeClient()
            assert client.is_configured is False

    def test_is_configured_true_with_all(self):
        with patch("analytics.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_client_id = "client"
            mock_settings.oauth2_client_secret = "secret"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            client = TokenExchangeClient()
            assert client.is_configured is True

    def test_issuer_strips_trailing_slash(self):
        with patch("analytics.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com/"
            client = TokenExchangeClient()
            assert client.issuer == "https://auth.example.com"

    def test_cache_key_deterministic(self):
        with patch("analytics.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            client = TokenExchangeClient()
            key1 = client._cache_key("token", ["scope1"])
            key2 = client._cache_key("token", ["scope1"])
            assert key1 == key2

    def test_cache_key_differs_for_different_scopes(self):
        with patch("analytics.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            client = TokenExchangeClient()
            key1 = client._cache_key("token", ["scope1"])
            key2 = client._cache_key("token", ["scope2"])
            assert key1 != key2

    async def test_exchange_token_raises_when_not_configured(self):
        with patch("analytics.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_client_id = ""
            mock_settings.oauth2_client_secret = ""
            mock_settings.oauth2_issuer = ""
            client = TokenExchangeClient()
            with pytest.raises(TokenExchangeError, match="not configured"):
                await client.exchange_token("token")

    async def test_close_without_clients(self):
        with patch("analytics.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            client = TokenExchangeClient()
            await client.close()  # Should not raise

    async def test_close_with_clients(self):
        with patch("analytics.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            client = TokenExchangeClient()
            mock_http = AsyncMock()
            mock_redis = AsyncMock()
            client._http_client = mock_http
            client._redis_client = mock_redis
            await client.close()
            mock_http.aclose.assert_called_once()
            mock_redis.aclose.assert_called_once()

    async def test_get_redis_client_returns_none_when_no_url(self):
        with patch("analytics.auth.token_exchange.settings") as mock_settings:
            mock_settings.redis_url = ""
            mock_settings.oauth2_issuer = "https://auth.example.com"
            client = TokenExchangeClient()
            result = await client._get_redis_client()
            assert result is None

    async def test_get_cached_returns_none_without_redis(self):
        with patch("analytics.auth.token_exchange.settings") as mock_settings:
            mock_settings.redis_url = ""
            mock_settings.oauth2_issuer = "https://auth.example.com"
            client = TokenExchangeClient()
            result = await client._get_cached("token", ["scope"])
            assert result is None

    async def test_validate_token_scopes_delegates_to_exchange(self):
        with patch("analytics.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_client_id = "client"
            mock_settings.oauth2_client_secret = "secret"
            client = TokenExchangeClient()
            client.exchange_token = AsyncMock(return_value={"scope": "analytics:read"})
            result = await client.validate_token_scopes("token", ["analytics:read"])
            assert result == {"scope": "analytics:read"}
            client.exchange_token.assert_called_once_with("token", ["analytics:read"])

    def test_grant_type_constant(self):
        assert TokenExchangeClient.GRANT_TYPE == "urn:ietf:params:oauth:grant-type:token-exchange"

    def test_token_type_constant(self):
        assert (
            TokenExchangeClient.TOKEN_TYPE_ACCESS == "urn:ietf:params:oauth:token-type:access_token"
        )

    # --- NEW TESTS for _get_http_client ---

    async def test_get_http_client_creates_new_client(self):
        """Test _get_http_client creates a new httpx.AsyncClient when none exists."""
        with patch("analytics.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            client = TokenExchangeClient()
            assert client._http_client is None
            with patch("analytics.auth.token_exchange.httpx.AsyncClient") as mock_async_client:
                mock_instance = MagicMock()
                mock_async_client.return_value = mock_instance
                result = await client._get_http_client()
                mock_async_client.assert_called_once_with(timeout=10.0)
                assert result is mock_instance
                assert client._http_client is mock_instance

    async def test_get_http_client_reuses_existing_client(self):
        """Test _get_http_client reuses existing client."""
        with patch("analytics.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            client = TokenExchangeClient()
            mock_http = MagicMock()
            client._http_client = mock_http
            result = await client._get_http_client()
            assert result is mock_http

    # --- NEW TESTS for _get_redis_client when redis_url IS set ---

    async def test_get_redis_client_creates_client_when_url_set(self):
        """Test _get_redis_client creates redis client when redis_url is configured."""
        with patch("analytics.auth.token_exchange.settings") as mock_settings:
            mock_settings.redis_url = "redis://localhost:6379/0"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            client = TokenExchangeClient()
            assert client._redis_client is None
            with patch("analytics.auth.token_exchange.redis.from_url") as mock_from_url:
                mock_redis_instance = MagicMock()
                mock_from_url.return_value = mock_redis_instance
                result = await client._get_redis_client()
                mock_from_url.assert_called_once_with(
                    "redis://localhost:6379/0",
                    decode_responses=True,
                )
                assert result is mock_redis_instance
                assert client._redis_client is mock_redis_instance

    async def test_get_redis_client_reuses_existing_client(self):
        """Test _get_redis_client reuses existing redis client."""
        with patch("analytics.auth.token_exchange.settings") as mock_settings:
            mock_settings.redis_url = "redis://localhost:6379/0"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            client = TokenExchangeClient()
            mock_redis = MagicMock()
            client._redis_client = mock_redis
            result = await client._get_redis_client()
            assert result is mock_redis

    # --- NEW TESTS for _get_cached with redis ---

    async def test_get_cached_cache_hit(self):
        """Test _get_cached returns deserialized data on cache hit."""
        with patch("analytics.auth.token_exchange.settings") as mock_settings:
            mock_settings.redis_url = "redis://localhost:6379/0"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            client = TokenExchangeClient()
            cached_data = {"scope": "analytics:read", "access_token": "new-token"}
            mock_redis = AsyncMock()
            mock_redis.get.return_value = json.dumps(cached_data)
            client._redis_client = mock_redis
            result = await client._get_cached("token123", ["analytics:read"])
            assert result == cached_data

    async def test_get_cached_cache_miss(self):
        """Test _get_cached returns None on cache miss."""
        with patch("analytics.auth.token_exchange.settings") as mock_settings:
            mock_settings.redis_url = "redis://localhost:6379/0"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            client = TokenExchangeClient()
            mock_redis = AsyncMock()
            mock_redis.get.return_value = None
            client._redis_client = mock_redis
            result = await client._get_cached("token123", ["analytics:read"])
            assert result is None

    async def test_get_cached_redis_exception(self):
        """Test _get_cached returns None on Redis exception."""
        with patch("analytics.auth.token_exchange.settings") as mock_settings:
            mock_settings.redis_url = "redis://localhost:6379/0"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            client = TokenExchangeClient()
            mock_redis = AsyncMock()
            mock_redis.get.side_effect = Exception("Redis connection error")
            client._redis_client = mock_redis
            result = await client._get_cached("token123", ["analytics:read"])
            assert result is None

    # --- NEW TESTS for _set_cached ---

    async def test_set_cached_success(self):
        """Test _set_cached writes to Redis successfully."""
        with patch("analytics.auth.token_exchange.settings") as mock_settings:
            mock_settings.redis_url = "redis://localhost:6379/0"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_client_cache_ttl = 300
            client = TokenExchangeClient()
            mock_redis = AsyncMock()
            client._redis_client = mock_redis
            result_data = {"scope": "analytics:read", "access_token": "new-token"}
            await client._set_cached("token123", ["analytics:read"], result_data)
            mock_redis.setex.assert_called_once_with(
                client._cache_key("token123", ["analytics:read"]),
                300,
                json.dumps(result_data),
            )

    async def test_set_cached_no_redis(self):
        """Test _set_cached returns early when no Redis client."""
        with patch("analytics.auth.token_exchange.settings") as mock_settings:
            mock_settings.redis_url = ""
            mock_settings.oauth2_issuer = "https://auth.example.com"
            client = TokenExchangeClient()
            # Should not raise
            await client._set_cached("token123", ["analytics:read"], {"scope": "analytics:read"})

    async def test_set_cached_redis_exception(self):
        """Test _set_cached handles Redis exception gracefully."""
        with patch("analytics.auth.token_exchange.settings") as mock_settings:
            mock_settings.redis_url = "redis://localhost:6379/0"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_client_cache_ttl = 300
            client = TokenExchangeClient()
            mock_redis = AsyncMock()
            mock_redis.setex.side_effect = Exception("Redis write error")
            client._redis_client = mock_redis
            # Should not raise
            await client._set_cached("token123", ["analytics:read"], {"scope": "analytics:read"})

    # --- NEW TESTS for exchange_token full flow ---

    async def test_exchange_token_cache_hit(self):
        """Test exchange_token returns cached result when available."""
        with patch("analytics.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_client_id = "client"
            mock_settings.oauth2_client_secret = "secret"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            client = TokenExchangeClient()
            cached_data = {"scope": "analytics:read", "access_token": "cached-token"}
            client._get_cached = AsyncMock(return_value=cached_data)
            result = await client.exchange_token("token123", ["analytics:read"])
            assert result == cached_data
            client._get_cached.assert_called_once_with("token123", ["analytics:read"])

    async def test_exchange_token_post_success_200(self):
        """Test exchange_token successful POST returns result and caches it."""
        with patch("analytics.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_client_id = "client"
            mock_settings.oauth2_client_secret = "secret"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            client = TokenExchangeClient()
            client._get_cached = AsyncMock(return_value=None)
            client._set_cached = AsyncMock()
            result_data = {
                "scope": "analytics:read",
                "access_token": "new-token",
                "token_type": "Bearer",
            }
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = result_data
            mock_http = AsyncMock()
            mock_http.post.return_value = mock_response
            client._http_client = mock_http
            result = await client.exchange_token("token123", ["analytics:read"])
            assert result == result_data
            client._set_cached.assert_called_once_with("token123", ["analytics:read"], result_data)
            mock_http.post.assert_called_once_with(
                "https://auth.example.com/oauth2/token",
                data={
                    "grant_type": TokenExchangeClient.GRANT_TYPE,
                    "subject_token": "token123",
                    "subject_token_type": TokenExchangeClient.TOKEN_TYPE_ACCESS,
                    "client_id": "client",
                    "client_secret": "secret",
                    "scope": "analytics:read",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

    async def test_exchange_token_post_non_200_with_json_error(self):
        """Test exchange_token raises TokenExchangeError on non-200 with JSON error body."""
        with patch("analytics.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_client_id = "client"
            mock_settings.oauth2_client_secret = "secret"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            client = TokenExchangeClient()
            client._get_cached = AsyncMock(return_value=None)
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.content = (
                b'{"error": "invalid_grant", "error_description": "Token expired"}'
            )
            mock_response.json.return_value = {
                "error": "invalid_grant",
                "error_description": "Token expired",
            }
            mock_http = AsyncMock()
            mock_http.post.return_value = mock_response
            client._http_client = mock_http
            with pytest.raises(TokenExchangeError) as exc_info:
                await client.exchange_token("token123", ["analytics:read"])
            assert exc_info.value.error_code == "invalid_grant"
            assert "Token expired" in str(exc_info.value)

    async def test_exchange_token_post_non_200_without_json(self):
        """Test exchange_token raises TokenExchangeError on non-200 without valid JSON."""
        with patch("analytics.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_client_id = "client"
            mock_settings.oauth2_client_secret = "secret"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            client = TokenExchangeClient()
            client._get_cached = AsyncMock(return_value=None)
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.content = b"Internal Server Error"
            mock_response.json.side_effect = Exception("Not JSON")
            mock_http = AsyncMock()
            mock_http.post.return_value = mock_response
            client._http_client = mock_http
            with pytest.raises(TokenExchangeError) as exc_info:
                await client.exchange_token("token123", ["analytics:read"])
            assert exc_info.value.error_code == "unknown_error"
            assert "Token exchange failed" in str(exc_info.value)

    async def test_exchange_token_post_non_200_empty_content(self):
        """Test exchange_token on non-200 with empty content."""
        with patch("analytics.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_client_id = "client"
            mock_settings.oauth2_client_secret = "secret"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            client = TokenExchangeClient()
            client._get_cached = AsyncMock(return_value=None)
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.content = b""  # Empty content
            mock_http = AsyncMock()
            mock_http.post.return_value = mock_response
            client._http_client = mock_http
            with pytest.raises(TokenExchangeError) as exc_info:
                await client.exchange_token("token123")
            assert exc_info.value.error_code == "unknown_error"

    async def test_exchange_token_scopes_in_data(self):
        """Test exchange_token includes scope in POST data when scopes provided."""
        with patch("analytics.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_client_id = "client"
            mock_settings.oauth2_client_secret = "secret"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            client = TokenExchangeClient()
            client._get_cached = AsyncMock(return_value=None)
            client._set_cached = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"scope": "analytics:read analytics:write"}
            mock_http = AsyncMock()
            mock_http.post.return_value = mock_response
            client._http_client = mock_http
            await client.exchange_token("token123", ["analytics:read", "analytics:write"])
            call_args = mock_http.post.call_args
            posted_data = call_args[1]["data"]
            assert posted_data["scope"] == "analytics:read analytics:write"

    async def test_exchange_token_no_scopes_omits_scope_field(self):
        """Test exchange_token does not include scope in POST data when no scopes."""
        with patch("analytics.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_client_id = "client"
            mock_settings.oauth2_client_secret = "secret"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            client = TokenExchangeClient()
            client._get_cached = AsyncMock(return_value=None)
            client._set_cached = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"scope": ""}
            mock_http = AsyncMock()
            mock_http.post.return_value = mock_response
            client._http_client = mock_http
            await client.exchange_token("token123")
            call_args = mock_http.post.call_args
            posted_data = call_args[1]["data"]
            assert "scope" not in posted_data

    async def test_exchange_token_none_scopes_treated_as_empty(self):
        """Test exchange_token treats None scopes as empty list."""
        with patch("analytics.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_client_id = "client"
            mock_settings.oauth2_client_secret = "secret"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            client = TokenExchangeClient()
            client._get_cached = AsyncMock(return_value=None)
            client._set_cached = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"access_token": "new"}
            mock_http = AsyncMock()
            mock_http.post.return_value = mock_response
            client._http_client = mock_http
            await client.exchange_token("token123", None)
            call_args = mock_http.post.call_args
            posted_data = call_args[1]["data"]
            assert "scope" not in posted_data
