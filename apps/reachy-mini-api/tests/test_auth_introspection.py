# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for reachy_mini_api/auth/introspection.py."""

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from reachy_mini_api.auth.introspection import (
    IntrospectionClient,
    TokenRevokedError,
    introspection_client,
)


class TestTokenRevokedError:
    """Tests for TokenRevokedError exception."""

    def test_message(self):
        err = TokenRevokedError("Token revoked")
        assert str(err) == "Token revoked"

    def test_is_exception_subclass(self):
        assert issubclass(TokenRevokedError, Exception)


class TestIntrospectionClientInit:
    """Tests for IntrospectionClient initialization."""

    def test_init_empty_state(self):
        client = IntrospectionClient()
        assert client._http_client is None
        assert client._redis_client is None


class TestIntrospectionClientProperties:
    """Tests for is_configured and introspection_uri."""

    @patch("reachy_mini_api.auth.introspection.settings")
    @patch("reachy_mini_api.auth.introspection.jwks_manager")
    def test_is_configured_true(self, mock_jwks, mock_settings):
        mock_settings.oauth2_client_id = "client-id"
        mock_settings.oauth2_client_secret = "secret"
        mock_jwks.is_configured = True
        client = IntrospectionClient()
        assert client.is_configured is True

    @patch("reachy_mini_api.auth.introspection.settings")
    @patch("reachy_mini_api.auth.introspection.jwks_manager")
    def test_not_configured_without_client_id(self, mock_jwks, mock_settings):
        mock_settings.oauth2_client_id = ""
        mock_settings.oauth2_client_secret = "secret"
        mock_jwks.is_configured = True
        client = IntrospectionClient()
        assert client.is_configured is False

    @patch("reachy_mini_api.auth.introspection.settings")
    @patch("reachy_mini_api.auth.introspection.jwks_manager")
    def test_not_configured_without_client_secret(self, mock_jwks, mock_settings):
        mock_settings.oauth2_client_id = "client-id"
        mock_settings.oauth2_client_secret = ""
        mock_jwks.is_configured = True
        client = IntrospectionClient()
        assert client.is_configured is False

    @patch("reachy_mini_api.auth.introspection.settings")
    @patch("reachy_mini_api.auth.introspection.jwks_manager")
    def test_not_configured_without_jwks(self, mock_jwks, mock_settings):
        mock_settings.oauth2_client_id = "client-id"
        mock_settings.oauth2_client_secret = "secret"
        mock_jwks.is_configured = False
        client = IntrospectionClient()
        assert client.is_configured is False

    @patch("reachy_mini_api.auth.introspection.jwks_manager")
    def test_introspection_uri(self, mock_jwks):
        mock_jwks.issuer = "https://auth.example.com"
        client = IntrospectionClient()
        assert client.introspection_uri == "https://auth.example.com/oauth2/introspect"


class TestIntrospectionClientHttpClient:
    """Tests for _get_http_client()."""

    @pytest.mark.asyncio
    async def test_creates_on_first_call(self):
        client = IntrospectionClient()
        http_client = await client._get_http_client()
        assert http_client is not None
        await client.close()

    @pytest.mark.asyncio
    async def test_reuses_existing(self):
        client = IntrospectionClient()
        c1 = await client._get_http_client()
        c2 = await client._get_http_client()
        assert c1 is c2
        await client.close()


class TestIntrospectionClientRedisClient:
    """Tests for _get_redis_client()."""

    @pytest.mark.asyncio
    @patch("reachy_mini_api.auth.introspection.settings")
    async def test_returns_none_when_no_redis_url(self, mock_settings):
        mock_settings.redis_url = ""
        client = IntrospectionClient()
        result = await client._get_redis_client()
        assert result is None

    @pytest.mark.asyncio
    @patch("reachy_mini_api.auth.introspection.redis")
    @patch("reachy_mini_api.auth.introspection.settings")
    async def test_creates_redis_client(self, mock_settings, mock_redis):
        mock_settings.redis_url = "redis://localhost:6379/0"
        mock_redis_instance = MagicMock()
        mock_redis.from_url.return_value = mock_redis_instance
        client = IntrospectionClient()

        result = await client._get_redis_client()
        assert result is mock_redis_instance
        mock_redis.from_url.assert_called_once_with(
            "redis://localhost:6379/0",
            decode_responses=True,
        )

    @pytest.mark.asyncio
    @patch("reachy_mini_api.auth.introspection.redis")
    @patch("reachy_mini_api.auth.introspection.settings")
    async def test_reuses_existing_redis_client(self, mock_settings, mock_redis):
        mock_settings.redis_url = "redis://localhost:6379/0"
        mock_redis_instance = MagicMock()
        mock_redis.from_url.return_value = mock_redis_instance
        client = IntrospectionClient()

        r1 = await client._get_redis_client()
        r2 = await client._get_redis_client()
        assert r1 is r2
        mock_redis.from_url.assert_called_once()


class TestIntrospectionClientCacheKey:
    """Tests for _cache_key()."""

    @patch("reachy_mini_api.auth.introspection.settings")
    def test_deterministic(self, mock_settings):
        mock_settings.redis_key_prefix = "test"
        client = IntrospectionClient()
        key1 = client._cache_key("test-token")
        key2 = client._cache_key("test-token")
        assert key1 == key2

    @patch("reachy_mini_api.auth.introspection.settings")
    def test_uses_redis_key_prefix(self, mock_settings):
        mock_settings.redis_key_prefix = "myapp"
        client = IntrospectionClient()
        key = client._cache_key("test-token")
        token_hash = hashlib.sha256(b"test-token").hexdigest()[:16]
        assert key == f"myapp:introspect:{token_hash}"

    @patch("reachy_mini_api.auth.introspection.settings")
    def test_different_tokens_produce_different_keys(self, mock_settings):
        mock_settings.redis_key_prefix = "test"
        client = IntrospectionClient()
        key1 = client._cache_key("token-a")
        key2 = client._cache_key("token-b")
        assert key1 != key2


class TestIntrospectionClientGetCached:
    """Tests for _get_cached()."""

    @pytest.mark.asyncio
    @patch("reachy_mini_api.auth.introspection.settings")
    async def test_returns_none_without_redis(self, mock_settings):
        mock_settings.redis_url = ""
        client = IntrospectionClient()
        result = await client._get_cached("token")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_true_for_cached_active(self):
        client = IntrospectionClient()
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="1")

        with patch.object(client, "_get_redis_client", return_value=mock_redis):
            result = await client._get_cached("token")
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_for_cached_inactive(self):
        client = IntrospectionClient()
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="0")

        with patch.object(client, "_get_redis_client", return_value=mock_redis):
            result = await client._get_cached("token")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_none_on_cache_miss(self):
        client = IntrospectionClient()
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with patch.object(client, "_get_redis_client", return_value=mock_redis):
            result = await client._get_cached("token")
        assert result is None

    @pytest.mark.asyncio
    async def test_handles_redis_error(self):
        client = IntrospectionClient()
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=Exception("Redis down"))

        with patch.object(client, "_get_redis_client", return_value=mock_redis):
            result = await client._get_cached("token")
        assert result is None


class TestIntrospectionClientSetCached:
    """Tests for _set_cached()."""

    @pytest.mark.asyncio
    @patch("reachy_mini_api.auth.introspection.settings")
    async def test_skips_without_redis(self, mock_settings):
        mock_settings.redis_url = ""
        client = IntrospectionClient()
        await client._set_cached("token", True)  # should not raise

    @pytest.mark.asyncio
    @patch("reachy_mini_api.auth.introspection.settings")
    async def test_caches_active_token(self, mock_settings):
        mock_settings.token_introspection_cache_ttl = 60
        client = IntrospectionClient()
        mock_redis = AsyncMock()

        with patch.object(client, "_get_redis_client", return_value=mock_redis):
            await client._set_cached("token", True)

        mock_redis.setex.assert_awaited_once()
        args = mock_redis.setex.call_args
        assert args[0][2] == "1"

    @pytest.mark.asyncio
    @patch("reachy_mini_api.auth.introspection.settings")
    async def test_caches_inactive_token(self, mock_settings):
        mock_settings.token_introspection_cache_ttl = 60
        client = IntrospectionClient()
        mock_redis = AsyncMock()

        with patch.object(client, "_get_redis_client", return_value=mock_redis):
            await client._set_cached("token", False)

        args = mock_redis.setex.call_args
        assert args[0][2] == "0"

    @pytest.mark.asyncio
    async def test_handles_redis_write_error(self):
        client = IntrospectionClient()
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock(side_effect=Exception("Redis write failed"))

        with patch.object(client, "_get_redis_client", return_value=mock_redis):
            await client._set_cached("token", True)  # should not raise


class TestIntrospectionClientIntrospectRequest:
    """Tests for _introspect_request()."""

    @pytest.mark.asyncio
    @patch("reachy_mini_api.auth.introspection.settings")
    @patch("reachy_mini_api.auth.introspection.jwks_manager")
    async def test_sends_with_token_type_hint(self, mock_jwks, mock_settings):
        mock_settings.oauth2_client_id = "cid"
        mock_settings.oauth2_client_secret = "sec"
        mock_jwks.issuer = "https://auth.example.com"
        client = IntrospectionClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {"active": True}
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_http_client", return_value=mock_http):
            result = await client._introspect_request("my-token", token_type_hint="access_token")

        assert result == {"active": True}
        call_kwargs = mock_http.post.call_args
        assert call_kwargs[1]["data"]["token_type_hint"] == "access_token"
        assert call_kwargs[1]["data"]["client_id"] == "cid"
        assert call_kwargs[1]["data"]["client_secret"] == "sec"

    @pytest.mark.asyncio
    @patch("reachy_mini_api.auth.introspection.settings")
    @patch("reachy_mini_api.auth.introspection.jwks_manager")
    async def test_sends_without_token_type_hint(self, mock_jwks, mock_settings):
        mock_settings.oauth2_client_id = "cid"
        mock_settings.oauth2_client_secret = "sec"
        mock_jwks.issuer = "https://auth.example.com"
        client = IntrospectionClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {"active": True}
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_http_client", return_value=mock_http):
            await client._introspect_request("my-token", token_type_hint=None)

        call_kwargs = mock_http.post.call_args
        assert "token_type_hint" not in call_kwargs[1]["data"]

    @pytest.mark.asyncio
    @patch("reachy_mini_api.auth.introspection.settings")
    @patch("reachy_mini_api.auth.introspection.jwks_manager")
    async def test_raises_on_http_error(self, mock_jwks, mock_settings):
        mock_settings.oauth2_client_id = "cid"
        mock_settings.oauth2_client_secret = "sec"
        mock_jwks.issuer = "https://auth.example.com"
        client = IntrospectionClient()

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("HTTP 500")

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)

        with (
            patch.object(client, "_get_http_client", return_value=mock_http),
            pytest.raises(Exception, match="HTTP 500"),
        ):
            await client._introspect_request("my-token")


class TestIntrospectionClientIntrospectToken:
    """Tests for introspect_token()."""

    @pytest.mark.asyncio
    @patch("reachy_mini_api.auth.introspection.settings")
    @patch("reachy_mini_api.auth.introspection.jwks_manager")
    async def test_returns_true_when_not_configured(self, mock_jwks, mock_settings):
        mock_settings.oauth2_client_id = ""
        mock_settings.oauth2_client_secret = ""
        mock_jwks.is_configured = False
        client = IntrospectionClient()
        result = await client.introspect_token("token")
        assert result is True

    @pytest.mark.asyncio
    @patch("reachy_mini_api.auth.introspection.settings")
    @patch("reachy_mini_api.auth.introspection.jwks_manager")
    async def test_returns_cached_result(self, mock_jwks, mock_settings):
        mock_settings.oauth2_client_id = "cid"
        mock_settings.oauth2_client_secret = "sec"
        mock_jwks.is_configured = True
        client = IntrospectionClient()

        with patch.object(client, "_get_cached", return_value=True):
            result = await client.introspect_token("token")
        assert result is True

    @pytest.mark.asyncio
    @patch("reachy_mini_api.auth.introspection.settings")
    @patch("reachy_mini_api.auth.introspection.jwks_manager")
    async def test_active_token(self, mock_jwks, mock_settings):
        mock_settings.oauth2_client_id = "cid"
        mock_settings.oauth2_client_secret = "sec"
        mock_jwks.is_configured = True
        mock_jwks.issuer = "https://auth.example.com"
        client = IntrospectionClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {"active": True}
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)

        with (
            patch.object(client, "_get_cached", return_value=None),
            patch.object(client, "_get_http_client", return_value=mock_http),
            patch.object(client, "_set_cached", new_callable=AsyncMock) as mock_set,
        ):
            result = await client.introspect_token("token")

        assert result is True
        mock_set.assert_awaited_once_with("token", True)

    @pytest.mark.asyncio
    @patch("reachy_mini_api.auth.introspection.settings")
    @patch("reachy_mini_api.auth.introspection.jwks_manager")
    async def test_inactive_token(self, mock_jwks, mock_settings):
        mock_settings.oauth2_client_id = "cid"
        mock_settings.oauth2_client_secret = "sec"
        mock_jwks.is_configured = True
        mock_jwks.issuer = "https://auth.example.com"
        client = IntrospectionClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {"active": False}
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)

        with (
            patch.object(client, "_get_cached", return_value=None),
            patch.object(client, "_get_http_client", return_value=mock_http),
            patch.object(client, "_set_cached", new_callable=AsyncMock),
        ):
            result = await client.introspect_token("token")

        assert result is False

    @pytest.mark.asyncio
    @patch("reachy_mini_api.auth.introspection.settings")
    @patch("reachy_mini_api.auth.introspection.jwks_manager")
    async def test_returns_true_on_http_error(self, mock_jwks, mock_settings):
        """Graceful fallback: returns True on introspection failure."""
        mock_settings.oauth2_client_id = "cid"
        mock_settings.oauth2_client_secret = "sec"
        mock_jwks.is_configured = True
        mock_jwks.issuer = "https://auth.example.com"
        client = IntrospectionClient()

        with (
            patch.object(client, "_get_cached", return_value=None),
            patch.object(client, "_introspect_request", side_effect=Exception("connection failed")),
        ):
            result = await client.introspect_token("token")

        assert result is True


class TestIntrospectionClientValidateOpaqueToken:
    """Tests for validate_opaque_token()."""

    @pytest.mark.asyncio
    async def test_success(self):
        client = IntrospectionClient()
        introspection_result = {"active": True, "sub": "user1", "scope": "openid"}

        with (
            patch.object(client, "_introspect_request", return_value=introspection_result),
            patch.object(client, "_set_cached", new_callable=AsyncMock) as mock_set,
        ):
            result = await client.validate_opaque_token("opaque-token")

        assert result == introspection_result
        mock_set.assert_awaited_once_with("opaque-token", True)

    @pytest.mark.asyncio
    async def test_inactive_raises_token_revoked_error(self):
        client = IntrospectionClient()

        with (
            patch.object(client, "_introspect_request", return_value={"active": False}),
            pytest.raises(TokenRevokedError, match="not active"),
        ):
            await client.validate_opaque_token("opaque-token")

    @pytest.mark.asyncio
    async def test_request_failure_raises_invalid_token_error(self):
        client = IntrospectionClient()

        with (
            patch.object(client, "_introspect_request", side_effect=Exception("connection failed")),
            pytest.raises(jwt.InvalidTokenError, match="introspection failed"),
        ):
            await client.validate_opaque_token("opaque-token")

    @pytest.mark.asyncio
    async def test_passes_none_token_type_hint(self):
        """validate_opaque_token passes token_type_hint=None."""
        client = IntrospectionClient()

        with (
            patch.object(
                client,
                "_introspect_request",
                return_value={"active": True, "sub": "user1"},
            ) as mock_req,
            patch.object(client, "_set_cached", new_callable=AsyncMock),
        ):
            await client.validate_opaque_token("opaque-token")

        mock_req.assert_awaited_once_with("opaque-token", token_type_hint=None)


class TestIntrospectionClientValidateTokenWithIntrospection:
    """Tests for validate_token_with_introspection()."""

    @pytest.mark.asyncio
    async def test_success(self):
        client = IntrospectionClient()
        expected_claims = {"sub": "user1", "scope": "openid"}

        with (
            patch.object(client, "introspect_token", return_value=True),
            patch("reachy_mini_api.auth.introspection.jwks_manager") as mock_jwks,
        ):
            mock_jwks.validate_token = AsyncMock(return_value=expected_claims)
            result = await client.validate_token_with_introspection("token")

        assert result == expected_claims

    @pytest.mark.asyncio
    async def test_revoked_raises_token_revoked_error(self):
        client = IntrospectionClient()

        with (
            patch.object(client, "introspect_token", return_value=False),
            patch("reachy_mini_api.auth.introspection.jwks_manager") as mock_jwks,
        ):
            mock_jwks.validate_token = AsyncMock(return_value={"sub": "user1"})
            with pytest.raises(TokenRevokedError, match="revoked"):
                await client.validate_token_with_introspection("token")


class TestIntrospectionClientClose:
    """Tests for close()."""

    @pytest.mark.asyncio
    async def test_closes_both_clients(self):
        client = IntrospectionClient()
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
        client = IntrospectionClient()
        await client.close()
        assert client._http_client is None
        assert client._redis_client is None


class TestModuleLevelInstance:
    """Tests for module-level singleton."""

    def test_introspection_client_exists(self):
        assert isinstance(introspection_client, IntrospectionClient)
