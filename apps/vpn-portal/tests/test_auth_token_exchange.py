# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for vpn_portal/auth/token_exchange.py."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from vpn_portal.auth.token_exchange import (
    TokenExchangeClient,
    TokenExchangeError,
    token_exchange_client,
)


class TestTokenExchangeError:
    """Tests for TokenExchangeError exception."""

    def test_message_and_error_code(self):
        err = TokenExchangeError("msg", error_code="custom")
        assert str(err) == "msg"
        assert err.error_code == "custom"

    def test_default_error_code(self):
        err = TokenExchangeError("msg")
        assert err.error_code == "exchange_error"

    def test_is_exception_subclass(self):
        assert issubclass(TokenExchangeError, Exception)


class TestTokenExchangeClientInit:
    """Tests for TokenExchangeClient initialization."""

    def test_init_empty_state(self):
        client = TokenExchangeClient()
        assert client._http_client is None
        assert client._redis_client is None


class TestTokenExchangeClientProperties:
    """Tests for is_configured property and class constants."""

    def test_is_configured_when_all_set(self):
        with patch("vpn_portal.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_client_id = "client-id"
            mock_settings.oauth2_client_secret = "client-secret"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            client = TokenExchangeClient()
            assert client.is_configured is True

    def test_not_configured_without_client_id(self):
        with patch("vpn_portal.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_client_id = ""
            mock_settings.oauth2_client_secret = "secret"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            client = TokenExchangeClient()
            assert client.is_configured is False

    def test_not_configured_without_secret(self):
        with patch("vpn_portal.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_client_id = "client"
            mock_settings.oauth2_client_secret = ""
            mock_settings.oauth2_issuer = "https://auth.example.com"
            client = TokenExchangeClient()
            assert client.is_configured is False

    def test_not_configured_without_issuer(self):
        with patch("vpn_portal.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_client_id = "client"
            mock_settings.oauth2_client_secret = "secret"
            mock_settings.oauth2_issuer = ""
            client = TokenExchangeClient()
            assert client.is_configured is False

    def test_grant_type_constant(self):
        assert TokenExchangeClient.GRANT_TYPE == "urn:ietf:params:oauth:grant-type:token-exchange"

    def test_token_type_constant(self):
        assert (
            TokenExchangeClient.TOKEN_TYPE_ACCESS == "urn:ietf:params:oauth:token-type:access_token"
        )


class TestTokenExchangeClientHttpClient:
    """Tests for _get_http_client()."""

    @pytest.mark.asyncio
    async def test_creates_on_first_call(self):
        client = TokenExchangeClient()
        assert client._http_client is None
        http_client = await client._get_http_client()
        assert http_client is not None
        assert client._http_client is http_client
        await client.close()

    @pytest.mark.asyncio
    async def test_reuses_existing(self):
        client = TokenExchangeClient()
        c1 = await client._get_http_client()
        c2 = await client._get_http_client()
        assert c1 is c2
        await client.close()


class TestTokenExchangeClientRedisClient:
    """Tests for _get_redis_client()."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_redis_url(self):
        with patch("vpn_portal.auth.token_exchange.settings") as mock_settings:
            mock_settings.redis_url = ""
            client = TokenExchangeClient()
            result = await client._get_redis_client()
            assert result is None

    @pytest.mark.asyncio
    async def test_creates_redis_client(self):
        with (
            patch("vpn_portal.auth.token_exchange.settings") as mock_settings,
            patch("vpn_portal.auth.token_exchange.redis.from_url") as mock_from_url,
        ):
            mock_settings.redis_url = "redis://localhost:6379/0"
            mock_redis = MagicMock()
            mock_from_url.return_value = mock_redis
            client = TokenExchangeClient()
            result = await client._get_redis_client()
            assert result is mock_redis
            mock_from_url.assert_called_once_with(
                "redis://localhost:6379/0",
                decode_responses=True,
            )

    @pytest.mark.asyncio
    async def test_reuses_existing(self):
        mock_redis = MagicMock()
        client = TokenExchangeClient()
        client._redis_client = mock_redis

        with (
            patch("vpn_portal.auth.token_exchange.settings") as mock_settings,
            patch("vpn_portal.auth.token_exchange.redis.from_url") as mock_from_url,
        ):
            mock_settings.redis_url = "redis://localhost:6379/0"
            result = await client._get_redis_client()
            assert result is mock_redis
            mock_from_url.assert_not_called()


class TestTokenExchangeClientCacheKey:
    """Tests for _cache_key()."""

    @patch("vpn_portal.auth.token_exchange.settings")
    def test_deterministic(self, mock_settings):
        mock_settings.redis_key_prefix = "test"
        client = TokenExchangeClient()
        key1 = client._cache_key("token", ["scope1", "scope2"])
        key2 = client._cache_key("token", ["scope1", "scope2"])
        assert key1 == key2

    @patch("vpn_portal.auth.token_exchange.settings")
    def test_uses_redis_key_prefix(self, mock_settings):
        mock_settings.redis_key_prefix = "myapp"
        client = TokenExchangeClient()
        key = client._cache_key("token", ["scope1"])
        assert key.startswith("myapp:tex:")

    @patch("vpn_portal.auth.token_exchange.settings")
    def test_different_tokens(self, mock_settings):
        mock_settings.redis_key_prefix = "test"
        client = TokenExchangeClient()
        key1 = client._cache_key("token1", ["scope1"])
        key2 = client._cache_key("token2", ["scope1"])
        assert key1 != key2

    @patch("vpn_portal.auth.token_exchange.settings")
    def test_different_scopes(self, mock_settings):
        mock_settings.redis_key_prefix = "test"
        client = TokenExchangeClient()
        key1 = client._cache_key("token", ["scope1"])
        key2 = client._cache_key("token", ["scope2"])
        assert key1 != key2

    @patch("vpn_portal.auth.token_exchange.settings")
    def test_scope_order_independent(self, mock_settings):
        mock_settings.redis_key_prefix = "test"
        client = TokenExchangeClient()
        key1 = client._cache_key("token", ["scope1", "scope2"])
        key2 = client._cache_key("token", ["scope2", "scope1"])
        assert key1 == key2


class TestTokenExchangeClientGetCached:
    """Tests for _get_cached()."""

    @pytest.mark.asyncio
    async def test_returns_none_without_redis(self):
        client = TokenExchangeClient()
        client._get_redis_client = AsyncMock(return_value=None)
        result = await client._get_cached("token", ["scope1"])
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_cached_data(self):
        cached_data = {"access_token": "new-token", "scope": "resource:read"}
        client = TokenExchangeClient()
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_data))
        client._get_redis_client = AsyncMock(return_value=mock_redis)

        result = await client._get_cached("token", ["resource:read"])
        assert result == cached_data

    @pytest.mark.asyncio
    async def test_returns_none_on_miss(self):
        client = TokenExchangeClient()
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        client._get_redis_client = AsyncMock(return_value=mock_redis)

        result = await client._get_cached("token", ["scope1"])
        assert result is None

    @pytest.mark.asyncio
    async def test_handles_redis_error(self):
        client = TokenExchangeClient()
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=Exception("redis down"))
        client._get_redis_client = AsyncMock(return_value=mock_redis)

        result = await client._get_cached("token", ["scope1"])
        assert result is None


class TestTokenExchangeClientSetCached:
    """Tests for _set_cached()."""

    @pytest.mark.asyncio
    async def test_stores_json_value(self):
        client = TokenExchangeClient()
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()
        client._get_redis_client = AsyncMock(return_value=mock_redis)

        with patch("vpn_portal.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_client_cache_ttl = 300
            await client._set_cached("token", ["scope1"], {"access_token": "new"})
            mock_redis.setex.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_without_redis(self):
        client = TokenExchangeClient()
        client._get_redis_client = AsyncMock(return_value=None)
        await client._set_cached("token", ["scope1"], {"access_token": "new"})

    @pytest.mark.asyncio
    async def test_handles_redis_error(self):
        client = TokenExchangeClient()
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock(side_effect=Exception("redis down"))
        client._get_redis_client = AsyncMock(return_value=mock_redis)

        with patch("vpn_portal.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_client_cache_ttl = 300
            await client._set_cached("token", ["scope1"], {"access_token": "new"})


class TestTokenExchangeClientExchangeToken:
    """Tests for exchange_token()."""

    @pytest.fixture(autouse=True)
    def _mock_jwks(self):
        with patch("vpn_portal.auth.token_exchange.jwks_manager") as mock:
            mock.fetch_issuer_config = AsyncMock(
                return_value={"token_endpoint": "https://auth.example.com/oauth2/token"}
            )
            yield mock

    @pytest.mark.asyncio
    async def test_not_configured_raises(self):
        with patch("vpn_portal.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_client_id = ""
            mock_settings.oauth2_client_secret = ""
            mock_settings.oauth2_issuer = ""
            client = TokenExchangeClient()
            with pytest.raises(TokenExchangeError, match="not configured"):
                await client.exchange_token("token", ["scope1"])

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached(self):
        cached = {"access_token": "cached-token", "scope": "resource:read"}
        client = TokenExchangeClient()
        client._get_cached = AsyncMock(return_value=cached)

        with patch("vpn_portal.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_client_id = "client"
            mock_settings.oauth2_client_secret = "secret"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            result = await client.exchange_token("token", ["resource:read"])
            assert result == cached

    @pytest.mark.asyncio
    async def test_successful_exchange(self):
        client = TokenExchangeClient()
        client._get_cached = AsyncMock(return_value=None)
        client._set_cached = AsyncMock()

        exchange_result = {
            "access_token": "new-token",
            "token_type": "Bearer",
            "scope": "resource:read",
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = exchange_result

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        client._get_http_client = AsyncMock(return_value=mock_http)

        with patch("vpn_portal.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_client_id = "client"
            mock_settings.oauth2_client_secret = "secret"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            result = await client.exchange_token("user-token", ["resource:read"])
            assert result == exchange_result
            client._set_cached.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exchange_with_scopes(self):
        """Verify scope is included in POST data when scopes are provided."""
        client = TokenExchangeClient()
        client._get_cached = AsyncMock(return_value=None)
        client._set_cached = AsyncMock()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "new", "scope": "a b"}

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        client._get_http_client = AsyncMock(return_value=mock_http)

        with patch("vpn_portal.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_client_id = "client"
            mock_settings.oauth2_client_secret = "secret"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            await client.exchange_token("user-token", ["scope1", "scope2"])

            call_kwargs = mock_http.post.call_args
            post_data = call_kwargs.kwargs.get("data", call_kwargs[1].get("data", {}))
            assert post_data["scope"] == "scope1 scope2"

    @pytest.mark.asyncio
    async def test_exchange_without_scopes(self):
        """Verify scope is NOT in POST data when no scopes requested."""
        client = TokenExchangeClient()
        client._get_cached = AsyncMock(return_value=None)
        client._set_cached = AsyncMock()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "new", "scope": "original"}

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        client._get_http_client = AsyncMock(return_value=mock_http)

        with patch("vpn_portal.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_client_id = "client"
            mock_settings.oauth2_client_secret = "secret"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            await client.exchange_token("user-token", None)

            call_kwargs = mock_http.post.call_args
            post_data = call_kwargs.kwargs.get("data", call_kwargs[1].get("data", {}))
            assert "scope" not in post_data

    @pytest.mark.asyncio
    async def test_missing_token_endpoint_raises(self):
        """Raise when issuer config has no token_endpoint."""
        client = TokenExchangeClient()
        client._get_cached = AsyncMock(return_value=None)

        with (
            patch("vpn_portal.auth.token_exchange.settings") as mock_settings,
            patch("vpn_portal.auth.token_exchange.jwks_manager") as mock_jwks,
        ):
            mock_settings.oauth2_client_id = "client"
            mock_settings.oauth2_client_secret = "secret"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_jwks.fetch_issuer_config = AsyncMock(return_value={})

            with pytest.raises(TokenExchangeError, match="Token endpoint not found"):
                await client.exchange_token("token", ["scope1"])

    @pytest.mark.asyncio
    async def test_error_invalid_grant(self):
        client = TokenExchangeClient()
        client._get_cached = AsyncMock(return_value=None)

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.content = b'{"error":"invalid_grant","error_description":"Token expired"}'
        mock_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Token expired",
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        client._get_http_client = AsyncMock(return_value=mock_http)

        with patch("vpn_portal.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_client_id = "client"
            mock_settings.oauth2_client_secret = "secret"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            with pytest.raises(TokenExchangeError) as exc_info:
                await client.exchange_token("token", ["resource:read"])
            assert exc_info.value.error_code == "invalid_grant"

    @pytest.mark.asyncio
    async def test_error_insufficient_scope(self):
        client = TokenExchangeClient()
        client._get_cached = AsyncMock(return_value=None)

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.content = b'{"error":"insufficient_scope"}'
        mock_response.json.return_value = {
            "error": "insufficient_scope",
            "error_description": "Token exchange failed",
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        client._get_http_client = AsyncMock(return_value=mock_http)

        with patch("vpn_portal.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_client_id = "client"
            mock_settings.oauth2_client_secret = "secret"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            with pytest.raises(TokenExchangeError) as exc_info:
                await client.exchange_token("token", ["admin:write"])
            assert exc_info.value.error_code == "insufficient_scope"

    @pytest.mark.asyncio
    async def test_error_with_empty_body(self):
        client = TokenExchangeClient()
        client._get_cached = AsyncMock(return_value=None)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.content = b""
        mock_response.json.side_effect = Exception("no json")

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        client._get_http_client = AsyncMock(return_value=mock_http)

        with patch("vpn_portal.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_client_id = "client"
            mock_settings.oauth2_client_secret = "secret"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            with pytest.raises(TokenExchangeError) as exc_info:
                await client.exchange_token("token", ["resource:read"])
            assert exc_info.value.error_code == "unknown_error"

    @pytest.mark.asyncio
    async def test_error_with_non_json_body(self):
        client = TokenExchangeClient()
        client._get_cached = AsyncMock(return_value=None)

        mock_response = MagicMock()
        mock_response.status_code = 502
        mock_response.content = b"Bad Gateway"
        mock_response.json.side_effect = ValueError("Invalid JSON")

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        client._get_http_client = AsyncMock(return_value=mock_http)

        with patch("vpn_portal.auth.token_exchange.settings") as mock_settings:
            mock_settings.oauth2_client_id = "client"
            mock_settings.oauth2_client_secret = "secret"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            with pytest.raises(TokenExchangeError) as exc_info:
                await client.exchange_token("token", ["resource:read"])
            assert exc_info.value.error_code == "unknown_error"
            assert "Token exchange failed" in str(exc_info.value)


class TestTokenExchangeClientValidateScopes:
    """Tests for validate_token_scopes()."""

    @pytest.mark.asyncio
    async def test_parses_exchanged_token_claims(self):
        """When exchange returns access_token, parse claims via jwks_manager."""
        client = TokenExchangeClient()
        exchange_result = {"access_token": "jwt-token", "scope": "resource:read"}
        expected_claims = {"sub": "user1", "scope": "resource:read"}
        client.exchange_token = AsyncMock(return_value=exchange_result)

        with patch("vpn_portal.auth.token_exchange.jwks_manager") as mock_jwks:
            mock_jwks.validate_token = AsyncMock(return_value=expected_claims)
            result = await client.validate_token_scopes("token", ["resource:read"])

        assert result["claims"] == expected_claims
        assert result["access_token"] == "jwt-token"

    @pytest.mark.asyncio
    async def test_no_access_token_skips_validation(self):
        """When exchange returns no access_token, skip claim parsing."""
        client = TokenExchangeClient()
        exchange_result = {"scope": "resource:read"}
        client.exchange_token = AsyncMock(return_value=exchange_result)

        with patch("vpn_portal.auth.token_exchange.jwks_manager") as mock_jwks:
            mock_jwks.validate_token = AsyncMock()
            result = await client.validate_token_scopes("token", ["resource:read"])

        assert "claims" not in result
        mock_jwks.validate_token.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_handles_token_validation_failure(self):
        """When jwks_manager.validate_token fails, result has no claims key."""
        client = TokenExchangeClient()
        exchange_result = {"access_token": "bad-jwt", "scope": "resource:read"}
        client.exchange_token = AsyncMock(return_value=exchange_result)

        with patch("vpn_portal.auth.token_exchange.jwks_manager") as mock_jwks:
            mock_jwks.validate_token = AsyncMock(side_effect=Exception("decode failed"))
            result = await client.validate_token_scopes("token", ["resource:read"])

        assert "claims" not in result
        assert result["access_token"] == "bad-jwt"


class TestTokenExchangeClientClose:
    """Tests for close()."""

    @pytest.mark.asyncio
    async def test_closes_both_clients(self):
        client = TokenExchangeClient()
        mock_http = AsyncMock()
        mock_redis = AsyncMock()
        client._http_client = mock_http
        client._redis_client = mock_redis

        await client.close()
        mock_http.aclose.assert_awaited_once()
        mock_redis.aclose.assert_awaited_once()
        assert client._http_client is None
        assert client._redis_client is None

    @pytest.mark.asyncio
    async def test_noop_when_no_clients(self):
        client = TokenExchangeClient()
        await client.close()
        assert client._http_client is None
        assert client._redis_client is None


class TestModuleLevelInstance:
    """Tests for module-level singleton."""

    def test_token_exchange_client_exists(self):
        assert isinstance(token_exchange_client, TokenExchangeClient)
