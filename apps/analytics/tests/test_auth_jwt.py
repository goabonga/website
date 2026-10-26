# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for analytics.auth.jwt module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from analytics.auth.jwt import JWTValidator, TokenRevokedError
from jose import JWTError


class TestTokenRevokedError:
    """Tests for TokenRevokedError."""

    def test_is_exception(self):
        err = TokenRevokedError("revoked")
        assert isinstance(err, Exception)
        assert str(err) == "revoked"


class TestJWTValidator:
    """Tests for JWTValidator class."""

    def test_issuer_strips_trailing_slash(self):
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com/"
            validator = JWTValidator()
            assert validator.issuer == "https://auth.example.com"

    def test_jwks_uri(self):
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            assert validator.jwks_uri == "https://auth.example.com/.well-known/jwks.json"

    def test_introspection_uri(self):
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            assert validator.introspection_uri == "https://auth.example.com/oauth2/introspect"

    def test_cache_key_is_deterministic(self):
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            key1 = validator._cache_key("token123")
            key2 = validator._cache_key("token123")
            assert key1 == key2

    def test_cache_key_differs_for_different_tokens(self):
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            key1 = validator._cache_key("token1")
            key2 = validator._cache_key("token2")
            assert key1 != key2

    async def test_close_without_clients(self):
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            await validator.close()  # Should not raise

    async def test_close_with_clients(self):
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            mock_http = AsyncMock()
            mock_redis = AsyncMock()
            validator._http_client = mock_http
            validator._redis_client = mock_redis
            await validator.close()
            mock_http.aclose.assert_called_once()
            mock_redis.aclose.assert_called_once()
            assert validator._http_client is None
            assert validator._redis_client is None

    async def test_get_redis_client_returns_none_when_no_url(self):
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.redis_url = ""
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            result = await validator._get_redis_client()
            assert result is None

    async def test_get_cached_introspection_returns_none_without_redis(self):
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.redis_url = ""
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            result = await validator._get_cached_introspection("token")
            assert result is None

    async def test_validate_token_with_introspection_raises_on_revoked(self):
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            validator.validate_token = AsyncMock(return_value={"sub": "user"})
            validator.introspect_token = AsyncMock(return_value=False)
            with pytest.raises(TokenRevokedError):
                await validator.validate_token_with_introspection("token")

    async def test_validate_token_with_introspection_success(self):
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            validator.validate_token = AsyncMock(return_value={"sub": "user"})
            validator.introspect_token = AsyncMock(return_value=True)
            result = await validator.validate_token_with_introspection("token")
            assert result == {"sub": "user"}

    # --- NEW TESTS for _get_http_client ---

    async def test_get_http_client_creates_new_client(self):
        """Test that _get_http_client creates a new httpx.AsyncClient when none exists."""
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            assert validator._http_client is None
            with patch("analytics.auth.jwt.httpx.AsyncClient") as mock_async_client:
                mock_instance = MagicMock()
                mock_async_client.return_value = mock_instance
                client = await validator._get_http_client()
                mock_async_client.assert_called_once_with(timeout=10.0)
                assert client is mock_instance
                assert validator._http_client is mock_instance

    async def test_get_http_client_reuses_existing_client(self):
        """Test that _get_http_client reuses existing client."""
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            mock_client = MagicMock()
            validator._http_client = mock_client
            client = await validator._get_http_client()
            assert client is mock_client

    # --- NEW TESTS for _get_redis_client when redis_url IS set ---

    async def test_get_redis_client_creates_client_when_url_set(self):
        """Test _get_redis_client creates a redis client when redis_url is configured."""
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.redis_url = "redis://localhost:6379/0"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            assert validator._redis_client is None
            with patch("analytics.auth.jwt.redis.from_url") as mock_from_url:
                mock_redis_instance = MagicMock()
                mock_from_url.return_value = mock_redis_instance
                result = await validator._get_redis_client()
                mock_from_url.assert_called_once_with(
                    "redis://localhost:6379/0",
                    decode_responses=True,
                )
                assert result is mock_redis_instance
                assert validator._redis_client is mock_redis_instance

    async def test_get_redis_client_reuses_existing_client(self):
        """Test _get_redis_client reuses existing redis client."""
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.redis_url = "redis://localhost:6379/0"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            mock_redis = MagicMock()
            validator._redis_client = mock_redis
            result = await validator._get_redis_client()
            assert result is mock_redis

    # --- NEW TESTS for _fetch_jwks ---

    async def test_fetch_jwks_success(self):
        """Test _fetch_jwks fetches and returns JWKS JSON."""
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            mock_response = MagicMock()
            mock_response.json.return_value = {"keys": [{"kid": "key1"}]}
            mock_response.raise_for_status = MagicMock()
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            validator._http_client = mock_client
            result = await validator._fetch_jwks()
            mock_client.get.assert_called_once_with(
                "https://auth.example.com/.well-known/jwks.json"
            )
            mock_response.raise_for_status.assert_called_once()
            assert result == {"keys": [{"kid": "key1"}]}

    # --- NEW TESTS for get_jwks ---

    async def test_get_jwks_fresh_fetch(self):
        """Test get_jwks fetches JWKS when cache is empty."""
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            assert validator._jwks is None
            jwks_data = {"keys": [{"kid": "key1"}]}
            validator._fetch_jwks = AsyncMock(return_value=jwks_data)
            result = await validator.get_jwks()
            assert result == jwks_data
            assert validator._jwks == jwks_data
            assert validator._jwks_expires_at > 0

    async def test_get_jwks_uses_cache_when_not_expired(self):
        """Test get_jwks returns cached JWKS when not expired."""
        import time

        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            cached_jwks = {"keys": [{"kid": "cached_key"}]}
            validator._jwks = cached_jwks
            validator._jwks_expires_at = time.time() + 9999
            validator._fetch_jwks = AsyncMock()
            result = await validator.get_jwks()
            assert result == cached_jwks
            validator._fetch_jwks.assert_not_called()

    async def test_get_jwks_refreshes_when_expired(self):
        """Test get_jwks refreshes JWKS when cache has expired."""
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            validator._jwks = {"keys": [{"kid": "old_key"}]}
            validator._jwks_expires_at = 0  # Expired
            new_jwks = {"keys": [{"kid": "new_key"}]}
            validator._fetch_jwks = AsyncMock(return_value=new_jwks)
            result = await validator.get_jwks()
            assert result == new_jwks
            validator._fetch_jwks.assert_called_once()

    async def test_get_jwks_failed_refresh_with_fallback(self):
        """Test get_jwks uses cached JWKS when refresh fails and cache exists."""
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            old_jwks = {"keys": [{"kid": "old_key"}]}
            validator._jwks = old_jwks
            validator._jwks_expires_at = 0  # Expired
            validator._fetch_jwks = AsyncMock(side_effect=Exception("network error"))
            result = await validator.get_jwks()
            assert result == old_jwks

    async def test_get_jwks_failed_without_cache_raises(self):
        """Test get_jwks raises exception when fetch fails and no cache exists."""
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            assert validator._jwks is None
            validator._fetch_jwks = AsyncMock(side_effect=Exception("network error"))
            with pytest.raises(Exception, match="network error"):
                await validator.get_jwks()

    # --- NEW TESTS for validate_token ---

    async def test_validate_token_success(self):
        """Test validate_token full successful flow."""
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            jwks_data = {"keys": [{"kid": "test-kid", "kty": "RSA"}]}
            validator.get_jwks = AsyncMock(return_value=jwks_data)
            expected_claims = {"sub": "user123", "iss": "https://auth.example.com"}
            with patch("analytics.auth.jwt.jwt.get_unverified_header") as mock_header:
                mock_header.return_value = {"kid": "test-kid", "alg": "RS256"}
                with patch("analytics.auth.jwt.jwt.decode") as mock_decode:
                    mock_decode.return_value = expected_claims
                    result = await validator.validate_token("some.jwt.token")
                    assert result == expected_claims
                    mock_decode.assert_called_once_with(
                        "some.jwt.token",
                        {"kid": "test-kid", "kty": "RSA"},
                        algorithms=["RS256", "ES256"],
                        issuer="https://auth.example.com",
                        options={"verify_aud": False},
                    )

    async def test_validate_token_no_matching_key(self):
        """Test validate_token raises JWTError when no matching key found."""
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            jwks_data = {"keys": [{"kid": "other-kid", "kty": "RSA"}]}
            validator.get_jwks = AsyncMock(return_value=jwks_data)
            with patch("analytics.auth.jwt.jwt.get_unverified_header") as mock_header:
                mock_header.return_value = {"kid": "test-kid", "alg": "RS256"}
                with pytest.raises(JWTError, match="No matching key found"):
                    await validator.validate_token("some.jwt.token")

    async def test_validate_token_jwt_error_reraise(self):
        """Test validate_token re-raises JWTError from decode."""
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            jwks_data = {"keys": [{"kid": "test-kid", "kty": "RSA"}]}
            validator.get_jwks = AsyncMock(return_value=jwks_data)
            with patch("analytics.auth.jwt.jwt.get_unverified_header") as mock_header:
                mock_header.return_value = {"kid": "test-kid", "alg": "RS256"}
                with patch("analytics.auth.jwt.jwt.decode") as mock_decode:
                    mock_decode.side_effect = JWTError("Invalid signature")
                    with pytest.raises(JWTError, match="Invalid signature"):
                        await validator.validate_token("some.jwt.token")

    async def test_validate_token_other_exception_wrapped_in_jwt_error(self):
        """Test validate_token wraps non-JWTError exceptions in JWTError."""
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            jwks_data = {"keys": [{"kid": "test-kid", "kty": "RSA"}]}
            validator.get_jwks = AsyncMock(return_value=jwks_data)
            with patch("analytics.auth.jwt.jwt.get_unverified_header") as mock_header:
                mock_header.side_effect = ValueError("unexpected error")
                with pytest.raises(JWTError, match="Token validation failed: unexpected error"):
                    await validator.validate_token("some.jwt.token")

    async def test_validate_token_empty_keys_list(self):
        """Test validate_token when JWKS has empty keys list."""
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            jwks_data = {"keys": []}
            validator.get_jwks = AsyncMock(return_value=jwks_data)
            with patch("analytics.auth.jwt.jwt.get_unverified_header") as mock_header:
                mock_header.return_value = {"kid": "test-kid", "alg": "RS256"}
                with pytest.raises(JWTError, match="No matching key found"):
                    await validator.validate_token("some.jwt.token")

    # --- NEW TESTS for _get_cached_introspection ---

    async def test_get_cached_introspection_cache_hit_active(self):
        """Test _get_cached_introspection returns True when cached value is '1'."""
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.redis_url = "redis://localhost:6379/0"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            mock_redis = AsyncMock()
            mock_redis.get.return_value = "1"
            validator._redis_client = mock_redis
            result = await validator._get_cached_introspection("token123")
            assert result is True

    async def test_get_cached_introspection_cache_hit_inactive(self):
        """Test _get_cached_introspection returns False when cached value is '0'."""
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.redis_url = "redis://localhost:6379/0"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            mock_redis = AsyncMock()
            mock_redis.get.return_value = "0"
            validator._redis_client = mock_redis
            result = await validator._get_cached_introspection("token123")
            assert result is False

    async def test_get_cached_introspection_cache_miss(self):
        """Test _get_cached_introspection returns None on cache miss."""
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.redis_url = "redis://localhost:6379/0"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            mock_redis = AsyncMock()
            mock_redis.get.return_value = None
            validator._redis_client = mock_redis
            result = await validator._get_cached_introspection("token123")
            assert result is None

    async def test_get_cached_introspection_redis_exception(self):
        """Test _get_cached_introspection returns None on Redis exception."""
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.redis_url = "redis://localhost:6379/0"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            mock_redis = AsyncMock()
            mock_redis.get.side_effect = Exception("Redis connection error")
            validator._redis_client = mock_redis
            result = await validator._get_cached_introspection("token123")
            assert result is None

    # --- NEW TESTS for _cache_introspection ---

    async def test_cache_introspection_success_active(self):
        """Test _cache_introspection caches active token."""
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.redis_url = "redis://localhost:6379/0"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.token_introspection_cache_ttl = 60
            validator = JWTValidator()
            mock_redis = AsyncMock()
            validator._redis_client = mock_redis
            await validator._cache_introspection("token123", True)
            mock_redis.setex.assert_called_once_with(
                validator._cache_key("token123"),
                60,
                "1",
            )

    async def test_cache_introspection_success_inactive(self):
        """Test _cache_introspection caches inactive token."""
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.redis_url = "redis://localhost:6379/0"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.token_introspection_cache_ttl = 60
            validator = JWTValidator()
            mock_redis = AsyncMock()
            validator._redis_client = mock_redis
            await validator._cache_introspection("token123", False)
            mock_redis.setex.assert_called_once_with(
                validator._cache_key("token123"),
                60,
                "0",
            )

    async def test_cache_introspection_no_redis(self):
        """Test _cache_introspection returns early when no Redis client."""
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.redis_url = ""
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            # Should not raise
            await validator._cache_introspection("token123", True)

    async def test_cache_introspection_redis_exception(self):
        """Test _cache_introspection handles Redis exception gracefully."""
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.redis_url = "redis://localhost:6379/0"
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.token_introspection_cache_ttl = 60
            validator = JWTValidator()
            mock_redis = AsyncMock()
            mock_redis.setex.side_effect = Exception("Redis write error")
            validator._redis_client = mock_redis
            # Should not raise
            await validator._cache_introspection("token123", True)

    # --- NEW TESTS for introspect_token ---

    async def test_introspect_token_cached_hit(self):
        """Test introspect_token returns cached result."""
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            validator._get_cached_introspection = AsyncMock(return_value=True)
            result = await validator.introspect_token("token123")
            assert result is True
            validator._get_cached_introspection.assert_called_once_with("token123")

    async def test_introspect_token_cached_hit_false(self):
        """Test introspect_token returns cached False result."""
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            validator = JWTValidator()
            validator._get_cached_introspection = AsyncMock(return_value=False)
            result = await validator.introspect_token("token123")
            assert result is False

    async def test_introspect_token_post_success_active(self):
        """Test introspect_token successful POST with active token."""
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_client_id = "client-id"
            mock_settings.oauth2_client_secret = "client-secret"
            validator = JWTValidator()
            validator._get_cached_introspection = AsyncMock(return_value=None)
            validator._cache_introspection = AsyncMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {"active": True}
            mock_response.raise_for_status = MagicMock()
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            validator._http_client = mock_client
            result = await validator.introspect_token("token123")
            assert result is True
            mock_client.post.assert_called_once_with(
                "https://auth.example.com/oauth2/introspect",
                data={
                    "token": "token123",
                    "token_type_hint": "access_token",
                    "client_id": "client-id",
                    "client_secret": "client-secret",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            validator._cache_introspection.assert_called_once_with("token123", True)

    async def test_introspect_token_post_success_inactive(self):
        """Test introspect_token successful POST with inactive token."""
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_client_id = "client-id"
            mock_settings.oauth2_client_secret = "client-secret"
            validator = JWTValidator()
            validator._get_cached_introspection = AsyncMock(return_value=None)
            validator._cache_introspection = AsyncMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {"active": False}
            mock_response.raise_for_status = MagicMock()
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            validator._http_client = mock_client
            result = await validator.introspect_token("token123")
            assert result is False
            validator._cache_introspection.assert_called_once_with("token123", False)

    async def test_introspect_token_post_exception_fallback(self):
        """Test introspect_token returns True when POST raises exception."""
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_client_id = "client-id"
            mock_settings.oauth2_client_secret = "client-secret"
            validator = JWTValidator()
            validator._get_cached_introspection = AsyncMock(return_value=None)
            mock_client = AsyncMock()
            mock_client.post.side_effect = Exception("Connection refused")
            validator._http_client = mock_client
            result = await validator.introspect_token("token123")
            assert result is True

    async def test_introspect_token_post_response_missing_active_field(self):
        """Test introspect_token defaults to False when 'active' field missing."""
        with patch("analytics.auth.jwt.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_client_id = "client-id"
            mock_settings.oauth2_client_secret = "client-secret"
            validator = JWTValidator()
            validator._get_cached_introspection = AsyncMock(return_value=None)
            validator._cache_introspection = AsyncMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {}  # No "active" field
            mock_response.raise_for_status = MagicMock()
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            validator._http_client = mock_client
            result = await validator.introspect_token("token123")
            assert result is False
            validator._cache_introspection.assert_called_once_with("token123", False)
