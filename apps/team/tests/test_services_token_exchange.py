# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for token exchange service."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from team.services.token_exchange import (
    TokenExchangeClient,
    TokenExchangeError,
    get_token_exchange_client,
)


class TestTokenExchangeError:
    def test_creation(self):
        err = TokenExchangeError("test error", error_code="test_code")
        assert str(err) == "test error"
        assert err.error_code == "test_code"

    def test_default_error_code(self):
        err = TokenExchangeError("fail")
        assert err.error_code == "exchange_error"


class TestTokenExchangeClient:
    @patch("team.services.token_exchange.settings")
    def test_is_configured_true(self, mock_settings):
        mock_settings.oauth2_client_id = "client-id"
        mock_settings.oauth2_client_secret = "secret"
        mock_settings.oauth2_issuer = "https://auth.example.com"
        client = TokenExchangeClient()
        assert client.is_configured is True

    @patch("team.services.token_exchange.settings")
    def test_is_configured_false(self, mock_settings):
        mock_settings.oauth2_client_id = ""
        mock_settings.oauth2_client_secret = "secret"
        mock_settings.oauth2_issuer = "https://auth.example.com"
        client = TokenExchangeClient()
        assert client.is_configured is False

    @patch("team.services.token_exchange.settings")
    def test_issuer(self, mock_settings):
        mock_settings.oauth2_issuer = "https://auth.example.com/"
        client = TokenExchangeClient()
        assert client.issuer == "https://auth.example.com"

    def test_cache_key(self):
        client = TokenExchangeClient()
        key = client._cache_key("test-token")
        assert key.startswith("tex:billing:")
        assert len(key) > len("tex:billing:")

    @pytest.mark.asyncio
    async def test_get_http_client(self):
        client = TokenExchangeClient()
        http_client = await client._get_http_client()
        assert http_client is not None
        assert client._http_client is http_client
        # Second call should return same instance
        http_client2 = await client._get_http_client()
        assert http_client is http_client2
        await client.close()

    @pytest.mark.asyncio
    @patch("team.services.token_exchange.settings")
    async def test_get_redis_client_no_url(self, mock_settings):
        mock_settings.redis_url = ""
        client = TokenExchangeClient()
        result = await client._get_redis_client()
        assert result is None

    @pytest.mark.asyncio
    @patch("team.services.token_exchange.settings")
    async def test_get_cached_no_redis(self, mock_settings):
        mock_settings.redis_url = ""
        client = TokenExchangeClient()
        result = await client._get_cached("token")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_cached_hit(self):
        client = TokenExchangeClient()
        mock_redis = AsyncMock()
        mock_redis.get.return_value = json.dumps({"scope": "billing:*"})
        client._redis_client = mock_redis

        with patch.object(client, "_get_redis_client", return_value=mock_redis):
            result = await client._get_cached("token")

        assert result == {"scope": "billing:*"}

    @pytest.mark.asyncio
    async def test_get_cached_miss(self):
        client = TokenExchangeClient()
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        client._redis_client = mock_redis

        with patch.object(client, "_get_redis_client", return_value=mock_redis):
            result = await client._get_cached("token")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_cached_redis_error(self):
        client = TokenExchangeClient()
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = Exception("Redis down")

        with patch.object(client, "_get_redis_client", return_value=mock_redis):
            result = await client._get_cached("token")

        assert result is None

    @pytest.mark.asyncio
    @patch("team.services.token_exchange.settings")
    async def test_set_cached_no_redis(self, mock_settings):
        mock_settings.redis_url = ""
        client = TokenExchangeClient()
        await client._set_cached("token", {"result": "ok"})
        # Should not raise

    @pytest.mark.asyncio
    async def test_set_cached_success(self):
        client = TokenExchangeClient()
        mock_redis = AsyncMock()

        with (
            patch.object(client, "_get_redis_client", return_value=mock_redis),
            patch("team.services.token_exchange.settings") as mock_settings,
        ):
            mock_settings.oauth2_token_cache_ttl = 300
            await client._set_cached("token", {"scope": "billing:*"})

        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_cached_redis_error(self):
        client = TokenExchangeClient()
        mock_redis = AsyncMock()
        mock_redis.setex.side_effect = Exception("Redis down")

        with (
            patch.object(client, "_get_redis_client", return_value=mock_redis),
            patch("team.services.token_exchange.settings") as mock_settings,
        ):
            mock_settings.oauth2_token_cache_ttl = 300
            await client._set_cached("token", {"result": "ok"})
        # Should not raise


class TestExchangeToken:
    @pytest.mark.asyncio
    @patch("team.services.token_exchange.settings")
    async def test_not_configured(self, mock_settings):
        mock_settings.oauth2_client_id = ""
        mock_settings.oauth2_client_secret = ""
        mock_settings.oauth2_issuer = ""
        client = TokenExchangeClient()

        with pytest.raises(TokenExchangeError, match="not configured"):
            await client.exchange_token("token")

    @pytest.mark.asyncio
    @patch("team.services.token_exchange.settings")
    async def test_cache_hit(self, mock_settings):
        mock_settings.oauth2_client_id = "id"
        mock_settings.oauth2_client_secret = "secret"
        mock_settings.oauth2_issuer = "https://auth.example.com"
        client = TokenExchangeClient()

        with patch.object(client, "_get_cached", return_value={"scope": "billing:*"}):
            result = await client.exchange_token("cached-token")

        assert result == {"scope": "billing:*"}

    @pytest.mark.asyncio
    @patch("team.services.token_exchange.settings")
    async def test_success(self, mock_settings):
        mock_settings.oauth2_client_id = "id"
        mock_settings.oauth2_client_secret = "secret"
        mock_settings.oauth2_issuer = "https://auth.example.com"
        client = TokenExchangeClient()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new-token",
            "scope": "billing:*",
        }

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response

        with (
            patch.object(client, "_get_cached", return_value=None),
            patch.object(client, "_get_http_client", return_value=mock_http),
            patch.object(client, "_set_cached", new_callable=AsyncMock),
        ):
            result = await client.exchange_token("subject-token")

        assert result["access_token"] == "new-token"

    @pytest.mark.asyncio
    @patch("team.services.token_exchange.settings")
    async def test_error_response(self, mock_settings):
        mock_settings.oauth2_client_id = "id"
        mock_settings.oauth2_client_secret = "secret"
        mock_settings.oauth2_issuer = "https://auth.example.com"
        client = TokenExchangeClient()

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.content = b'{"error": "invalid_grant", "error_description": "Token expired"}'
        mock_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Token expired",
        }

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response

        with (
            patch.object(client, "_get_cached", return_value=None),
            patch.object(client, "_get_http_client", return_value=mock_http),
            pytest.raises(TokenExchangeError) as exc_info,
        ):
            await client.exchange_token("bad-token")

        assert exc_info.value.error_code == "invalid_grant"

    @pytest.mark.asyncio
    @patch("team.services.token_exchange.settings")
    async def test_error_no_content(self, mock_settings):
        mock_settings.oauth2_client_id = "id"
        mock_settings.oauth2_client_secret = "secret"
        mock_settings.oauth2_issuer = "https://auth.example.com"
        client = TokenExchangeClient()

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.content = b""
        mock_response.json.side_effect = Exception("no json")

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response

        with (
            patch.object(client, "_get_cached", return_value=None),
            patch.object(client, "_get_http_client", return_value=mock_http),
            pytest.raises(TokenExchangeError) as exc_info,
        ):
            await client.exchange_token("token")

        assert exc_info.value.error_code == "unknown_error"

    @pytest.mark.asyncio
    @patch("team.services.token_exchange.settings")
    async def test_error_content_but_invalid_json(self, mock_settings):
        """Cover lines 159-160: content is truthy but json() raises."""
        mock_settings.oauth2_client_id = "id"
        mock_settings.oauth2_client_secret = "secret"
        mock_settings.oauth2_issuer = "https://auth.example.com"
        client = TokenExchangeClient()

        mock_response = MagicMock()
        mock_response.status_code = 502
        mock_response.content = b"Bad Gateway"
        mock_response.json.side_effect = ValueError("not json")

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response

        with (
            patch.object(client, "_get_cached", return_value=None),
            patch.object(client, "_get_http_client", return_value=mock_http),
            pytest.raises(TokenExchangeError) as exc_info,
        ):
            await client.exchange_token("token")

        assert exc_info.value.error_code == "unknown_error"


class TestRedisClientLazyInit:
    @pytest.mark.asyncio
    @patch("team.services.token_exchange.redis")
    @patch("team.services.token_exchange.settings")
    async def test_get_redis_client_creates_instance(self, mock_settings, mock_redis):
        """Cover lines 64-69: lazy Redis client creation when url is set."""
        mock_settings.redis_url = "redis://localhost:6379/0"
        mock_redis_instance = AsyncMock()
        mock_redis.from_url.return_value = mock_redis_instance
        client = TokenExchangeClient()

        result = await client._get_redis_client()

        assert result is mock_redis_instance
        mock_redis.from_url.assert_called_once_with(
            "redis://localhost:6379/0",
            decode_responses=True,
        )

    @pytest.mark.asyncio
    @patch("team.services.token_exchange.redis")
    @patch("team.services.token_exchange.settings")
    async def test_get_redis_client_reuses_instance(self, mock_settings, mock_redis):
        """Cover line 64: when _redis_client already exists, skip creation."""
        mock_settings.redis_url = "redis://localhost:6379/0"
        existing_redis = AsyncMock()
        client = TokenExchangeClient()
        client._redis_client = existing_redis

        result = await client._get_redis_client()

        assert result is existing_redis
        mock_redis.from_url.assert_not_called()


class TestClose:
    @pytest.mark.asyncio
    async def test_close_both_clients(self):
        client = TokenExchangeClient()
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
    async def test_close_no_clients(self):
        client = TokenExchangeClient()
        await client.close()  # Should not raise


class TestGetTokenExchangeClient:
    def test_singleton(self):
        import team.services.token_exchange as mod

        mod._token_exchange_client = None
        client1 = get_token_exchange_client()
        client2 = get_token_exchange_client()
        assert client1 is client2
        mod._token_exchange_client = None  # Cleanup
