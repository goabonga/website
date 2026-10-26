# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for internal.auth.jwt module."""

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from internal.auth.jwt import JWTValidator, TokenRevokedError
from jose import JWTError

# ---------------------------------------------------------------------------
# TestTokenRevokedError
# ---------------------------------------------------------------------------


class TestTokenRevokedError:
    """Test the TokenRevokedError exception class."""

    def test_is_exception(self):
        assert issubclass(TokenRevokedError, Exception)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(TokenRevokedError, match="revoked"):
            raise TokenRevokedError("Token has been revoked")

    def test_message_preserved(self):
        err = TokenRevokedError("my message")
        assert str(err) == "my message"


# ---------------------------------------------------------------------------
# TestJWTValidatorInit
# ---------------------------------------------------------------------------


class TestJWTValidatorInit:
    """Test __init__ sets correct defaults."""

    def test_defaults(self):
        v = JWTValidator()
        assert v._jwks is None
        assert v._jwks_expires_at == 0
        assert v._jwks_cache_ttl == 3600
        assert v._http_client is None
        assert v._redis_client is None


# ---------------------------------------------------------------------------
# TestProperties
# ---------------------------------------------------------------------------


class TestProperties:
    """Test issuer, jwks_uri, and introspection_uri properties."""

    @patch("internal.auth.jwt.settings")
    def test_issuer_strips_trailing_slash(self, mock_settings):
        mock_settings.oauth2_issuer = "https://auth.example.com/"
        v = JWTValidator()
        assert v.issuer == "https://auth.example.com"

    @patch("internal.auth.jwt.settings")
    def test_issuer_no_trailing_slash(self, mock_settings):
        mock_settings.oauth2_issuer = "https://auth.example.com"
        v = JWTValidator()
        assert v.issuer == "https://auth.example.com"

    @patch("internal.auth.jwt.settings")
    def test_jwks_uri(self, mock_settings):
        mock_settings.oauth2_issuer = "https://auth.example.com"
        v = JWTValidator()
        assert v.jwks_uri == "https://auth.example.com/.well-known/jwks.json"

    @patch("internal.auth.jwt.settings")
    def test_introspection_uri(self, mock_settings):
        mock_settings.oauth2_issuer = "https://auth.example.com"
        v = JWTValidator()
        assert v.introspection_uri == "https://auth.example.com/oauth2/introspect"


# ---------------------------------------------------------------------------
# TestGetHttpClient
# ---------------------------------------------------------------------------


class TestGetHttpClient:
    """Test _get_http_client creates or reuses HTTP client."""

    @pytest.mark.asyncio
    async def test_creates_client_when_none(self):
        v = JWTValidator()
        assert v._http_client is None
        client = await v._get_http_client()
        assert client is not None
        assert v._http_client is client
        # Cleanup
        await client.aclose()

    @pytest.mark.asyncio
    async def test_returns_existing_client(self):
        v = JWTValidator()
        mock_client = AsyncMock()
        v._http_client = mock_client
        client = await v._get_http_client()
        assert client is mock_client


# ---------------------------------------------------------------------------
# TestGetRedisClient
# ---------------------------------------------------------------------------


class TestGetRedisClient:
    """Test _get_redis_client returns None or creates Redis client."""

    @pytest.mark.asyncio
    @patch("internal.auth.jwt.settings")
    async def test_returns_none_when_no_redis_url(self, mock_settings):
        mock_settings.redis_url = ""
        v = JWTValidator()
        result = await v._get_redis_client()
        assert result is None

    @pytest.mark.asyncio
    @patch("internal.auth.jwt.redis")
    @patch("internal.auth.jwt.settings")
    async def test_creates_client_when_configured(self, mock_settings, mock_redis_mod):
        mock_settings.redis_url = "redis://localhost:6379/0"
        mock_redis_instance = MagicMock()
        mock_redis_mod.from_url.return_value = mock_redis_instance
        v = JWTValidator()
        client = await v._get_redis_client()
        assert client is mock_redis_instance
        mock_redis_mod.from_url.assert_called_once_with(
            "redis://localhost:6379/0", decode_responses=True
        )

    @pytest.mark.asyncio
    @patch("internal.auth.jwt.settings")
    async def test_returns_existing_client(self, mock_settings):
        mock_settings.redis_url = "redis://localhost:6379/0"
        v = JWTValidator()
        mock_redis = MagicMock()
        v._redis_client = mock_redis
        client = await v._get_redis_client()
        assert client is mock_redis


# ---------------------------------------------------------------------------
# TestFetchJwks
# ---------------------------------------------------------------------------


class TestFetchJwks:
    """Test _fetch_jwks makes HTTP request for JWKS."""

    @pytest.mark.asyncio
    @patch("internal.auth.jwt.settings")
    async def test_success(self, mock_settings):
        mock_settings.oauth2_issuer = "https://auth.example.com"
        v = JWTValidator()
        mock_response = MagicMock()
        mock_response.json.return_value = {"keys": [{"kid": "key1"}]}
        mock_response.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        v._http_client = mock_client
        result = await v._fetch_jwks()
        assert result == {"keys": [{"kid": "key1"}]}
        mock_client.get.assert_called_once_with("https://auth.example.com/.well-known/jwks.json")
        mock_response.raise_for_status.assert_called_once()


# ---------------------------------------------------------------------------
# TestGetJwks
# ---------------------------------------------------------------------------


class TestGetJwks:
    """Test get_jwks with caching logic."""

    @pytest.mark.asyncio
    @patch("internal.auth.jwt.settings")
    async def test_first_call_fetches(self, mock_settings):
        mock_settings.oauth2_issuer = "https://auth.example.com"
        v = JWTValidator()
        jwks_data = {"keys": [{"kid": "k1"}]}
        v._fetch_jwks = AsyncMock(return_value=jwks_data)
        result = await v.get_jwks()
        assert result == jwks_data
        v._fetch_jwks.assert_called_once()
        assert v._jwks is jwks_data
        assert v._jwks_expires_at > 0

    @pytest.mark.asyncio
    @patch("internal.auth.jwt.settings")
    async def test_cached_call_returns_cache(self, mock_settings):
        mock_settings.oauth2_issuer = "https://auth.example.com"
        v = JWTValidator()
        jwks_data = {"keys": [{"kid": "k1"}]}
        v._jwks = jwks_data
        # Set expiry far in the future
        v._jwks_expires_at = 9999999999.0
        v._fetch_jwks = AsyncMock()
        result = await v.get_jwks()
        assert result == jwks_data
        v._fetch_jwks.assert_not_called()

    @pytest.mark.asyncio
    @patch("internal.auth.jwt.settings")
    async def test_expired_cache_refetches(self, mock_settings):
        mock_settings.oauth2_issuer = "https://auth.example.com"
        v = JWTValidator()
        old_jwks = {"keys": [{"kid": "old"}]}
        new_jwks = {"keys": [{"kid": "new"}]}
        v._jwks = old_jwks
        v._jwks_expires_at = 0  # Already expired
        v._fetch_jwks = AsyncMock(return_value=new_jwks)
        result = await v.get_jwks()
        assert result == new_jwks
        v._fetch_jwks.assert_called_once()

    @pytest.mark.asyncio
    @patch("internal.auth.jwt.settings")
    async def test_fetch_fails_with_existing_cache_returns_old(self, mock_settings):
        mock_settings.oauth2_issuer = "https://auth.example.com"
        v = JWTValidator()
        old_jwks = {"keys": [{"kid": "old"}]}
        v._jwks = old_jwks
        v._jwks_expires_at = 0  # Expired
        v._fetch_jwks = AsyncMock(side_effect=Exception("network error"))
        result = await v.get_jwks()
        assert result == old_jwks

    @pytest.mark.asyncio
    @patch("internal.auth.jwt.settings")
    async def test_fetch_fails_with_no_cache_raises(self, mock_settings):
        mock_settings.oauth2_issuer = "https://auth.example.com"
        v = JWTValidator()
        assert v._jwks is None
        v._fetch_jwks = AsyncMock(side_effect=Exception("network error"))
        with pytest.raises(Exception, match="network error"):
            await v.get_jwks()


# ---------------------------------------------------------------------------
# TestValidateToken
# ---------------------------------------------------------------------------


class TestValidateToken:
    """Test validate_token with various scenarios."""

    @pytest.mark.asyncio
    @patch("internal.auth.jwt.jwt")
    @patch("internal.auth.jwt.settings")
    async def test_success_matching_kid(self, mock_settings, mock_jose_jwt):
        mock_settings.oauth2_issuer = "https://auth.example.com"
        v = JWTValidator()
        jwks_data = {"keys": [{"kid": "key1", "kty": "RSA"}]}
        v.get_jwks = AsyncMock(return_value=jwks_data)
        mock_jose_jwt.get_unverified_header.return_value = {"kid": "key1", "alg": "RS256"}
        expected_claims = {"sub": "user1", "iss": "https://auth.example.com"}
        mock_jose_jwt.decode.return_value = expected_claims
        result = await v.validate_token("fake.jwt.token")
        assert result == expected_claims
        mock_jose_jwt.decode.assert_called_once_with(
            "fake.jwt.token",
            {"kid": "key1", "kty": "RSA"},
            algorithms=["RS256", "ES256"],
            issuer="https://auth.example.com",
            options={"verify_aud": False},
        )

    @pytest.mark.asyncio
    @patch("internal.auth.jwt.jwt")
    @patch("internal.auth.jwt.settings")
    async def test_no_matching_kid_raises_jwt_error(self, mock_settings, mock_jose_jwt):
        mock_settings.oauth2_issuer = "https://auth.example.com"
        v = JWTValidator()
        jwks_data = {"keys": [{"kid": "key1"}]}
        v.get_jwks = AsyncMock(return_value=jwks_data)
        mock_jose_jwt.get_unverified_header.return_value = {"kid": "nonexistent"}
        with pytest.raises(JWTError, match="No matching key found in JWKS"):
            await v.validate_token("fake.jwt.token")

    @pytest.mark.asyncio
    @patch("internal.auth.jwt.jwt")
    @patch("internal.auth.jwt.settings")
    async def test_jwt_error_from_decode_reraises(self, mock_settings, mock_jose_jwt):
        mock_settings.oauth2_issuer = "https://auth.example.com"
        v = JWTValidator()
        jwks_data = {"keys": [{"kid": "key1"}]}
        v.get_jwks = AsyncMock(return_value=jwks_data)
        mock_jose_jwt.get_unverified_header.return_value = {"kid": "key1"}
        mock_jose_jwt.decode.side_effect = JWTError("Invalid signature")
        with pytest.raises(JWTError, match="Invalid signature"):
            await v.validate_token("fake.jwt.token")

    @pytest.mark.asyncio
    @patch("internal.auth.jwt.jwt")
    @patch("internal.auth.jwt.settings")
    async def test_other_exception_wraps_in_jwt_error(self, mock_settings, mock_jose_jwt):
        mock_settings.oauth2_issuer = "https://auth.example.com"
        v = JWTValidator()
        jwks_data = {"keys": [{"kid": "key1"}]}
        v.get_jwks = AsyncMock(return_value=jwks_data)
        mock_jose_jwt.get_unverified_header.return_value = {"kid": "key1"}
        mock_jose_jwt.decode.side_effect = ValueError("unexpected error")
        with pytest.raises(JWTError, match="Token validation failed: unexpected error"):
            await v.validate_token("fake.jwt.token")

    @pytest.mark.asyncio
    @patch("internal.auth.jwt.jwt")
    @patch("internal.auth.jwt.settings")
    async def test_empty_keys_list_raises_jwt_error(self, mock_settings, mock_jose_jwt):
        mock_settings.oauth2_issuer = "https://auth.example.com"
        v = JWTValidator()
        jwks_data = {"keys": []}
        v.get_jwks = AsyncMock(return_value=jwks_data)
        mock_jose_jwt.get_unverified_header.return_value = {"kid": "key1"}
        with pytest.raises(JWTError, match="No matching key found in JWKS"):
            await v.validate_token("fake.jwt.token")


# ---------------------------------------------------------------------------
# TestCacheKey
# ---------------------------------------------------------------------------


class TestCacheKey:
    """Test _cache_key returns expected format."""

    def test_returns_expected_format(self):
        v = JWTValidator()
        token = "my-test-token"
        expected_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
        result = v._cache_key(token)
        assert result == f"introspect:{expected_hash}"

    def test_different_tokens_different_keys(self):
        v = JWTValidator()
        key1 = v._cache_key("token-a")
        key2 = v._cache_key("token-b")
        assert key1 != key2

    def test_same_token_same_key(self):
        v = JWTValidator()
        key1 = v._cache_key("same-token")
        key2 = v._cache_key("same-token")
        assert key1 == key2


# ---------------------------------------------------------------------------
# TestGetCachedIntrospection
# ---------------------------------------------------------------------------


class TestGetCachedIntrospection:
    """Test _get_cached_introspection for all paths."""

    @pytest.mark.asyncio
    @patch("internal.auth.jwt.settings")
    async def test_no_redis_returns_none(self, mock_settings):
        mock_settings.redis_url = ""
        v = JWTValidator()
        result = await v._get_cached_introspection("token")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_hit_active(self):
        v = JWTValidator()
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "1"
        v._get_redis_client = AsyncMock(return_value=mock_redis)
        result = await v._get_cached_introspection("token")
        assert result is True

    @pytest.mark.asyncio
    async def test_cache_hit_inactive(self):
        v = JWTValidator()
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "0"
        v._get_redis_client = AsyncMock(return_value=mock_redis)
        result = await v._get_cached_introspection("token")
        assert result is False

    @pytest.mark.asyncio
    async def test_cache_miss(self):
        v = JWTValidator()
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        v._get_redis_client = AsyncMock(return_value=mock_redis)
        result = await v._get_cached_introspection("token")
        assert result is None

    @pytest.mark.asyncio
    async def test_redis_error_returns_none(self):
        v = JWTValidator()
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = Exception("connection refused")
        v._get_redis_client = AsyncMock(return_value=mock_redis)
        result = await v._get_cached_introspection("token")
        assert result is None


# ---------------------------------------------------------------------------
# TestCacheIntrospection
# ---------------------------------------------------------------------------


class TestCacheIntrospection:
    """Test _cache_introspection for all paths."""

    @pytest.mark.asyncio
    @patch("internal.auth.jwt.settings")
    async def test_no_redis_returns_immediately(self, mock_settings):
        mock_settings.redis_url = ""
        v = JWTValidator()
        # Should not raise, just return
        await v._cache_introspection("token", True)

    @pytest.mark.asyncio
    @patch("internal.auth.jwt.settings")
    async def test_success_active(self, mock_settings):
        mock_settings.token_introspection_cache_ttl = 60
        v = JWTValidator()
        mock_redis = AsyncMock()
        v._get_redis_client = AsyncMock(return_value=mock_redis)
        await v._cache_introspection("token", True)
        mock_redis.setex.assert_called_once_with(v._cache_key("token"), 60, "1")

    @pytest.mark.asyncio
    @patch("internal.auth.jwt.settings")
    async def test_success_inactive(self, mock_settings):
        mock_settings.token_introspection_cache_ttl = 60
        v = JWTValidator()
        mock_redis = AsyncMock()
        v._get_redis_client = AsyncMock(return_value=mock_redis)
        await v._cache_introspection("token", False)
        mock_redis.setex.assert_called_once_with(v._cache_key("token"), 60, "0")

    @pytest.mark.asyncio
    @patch("internal.auth.jwt.settings")
    async def test_redis_error_does_not_raise(self, mock_settings):
        mock_settings.token_introspection_cache_ttl = 60
        v = JWTValidator()
        mock_redis = AsyncMock()
        mock_redis.setex.side_effect = Exception("connection refused")
        v._get_redis_client = AsyncMock(return_value=mock_redis)
        # Should not raise
        await v._cache_introspection("token", True)


# ---------------------------------------------------------------------------
# TestIntrospectToken
# ---------------------------------------------------------------------------


class TestIntrospectToken:
    """Test introspect_token for all paths."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached(self):
        v = JWTValidator()
        v._get_cached_introspection = AsyncMock(return_value=True)
        result = await v.introspect_token("token")
        assert result is True
        v._get_cached_introspection.assert_called_once_with("token")

    @pytest.mark.asyncio
    async def test_cache_hit_inactive(self):
        v = JWTValidator()
        v._get_cached_introspection = AsyncMock(return_value=False)
        result = await v.introspect_token("token")
        assert result is False

    @pytest.mark.asyncio
    @patch("internal.auth.jwt.settings")
    async def test_cache_miss_fetches_and_caches(self, mock_settings):
        mock_settings.oauth2_issuer = "https://auth.example.com"
        mock_settings.oauth2_client_id = "client-id"
        mock_settings.oauth2_client_secret = "client-secret"
        v = JWTValidator()
        v._get_cached_introspection = AsyncMock(return_value=None)
        v._cache_introspection = AsyncMock()

        mock_response = MagicMock()
        mock_response.json.return_value = {"active": True}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        v._http_client = mock_client

        result = await v.introspect_token("token")
        assert result is True
        mock_client.post.assert_called_once_with(
            "https://auth.example.com/oauth2/introspect",
            data={
                "token": "token",
                "token_type_hint": "access_token",
                "client_id": "client-id",
                "client_secret": "client-secret",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        v._cache_introspection.assert_called_once_with("token", True)

    @pytest.mark.asyncio
    @patch("internal.auth.jwt.settings")
    async def test_cache_miss_inactive_token(self, mock_settings):
        mock_settings.oauth2_issuer = "https://auth.example.com"
        mock_settings.oauth2_client_id = "client-id"
        mock_settings.oauth2_client_secret = "client-secret"
        v = JWTValidator()
        v._get_cached_introspection = AsyncMock(return_value=None)
        v._cache_introspection = AsyncMock()

        mock_response = MagicMock()
        mock_response.json.return_value = {"active": False}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        v._http_client = mock_client

        result = await v.introspect_token("token")
        assert result is False
        v._cache_introspection.assert_called_once_with("token", False)

    @pytest.mark.asyncio
    @patch("internal.auth.jwt.settings")
    async def test_fetch_error_returns_true(self, mock_settings):
        mock_settings.oauth2_issuer = "https://auth.example.com"
        mock_settings.oauth2_client_id = "client-id"
        mock_settings.oauth2_client_secret = "client-secret"
        v = JWTValidator()
        v._get_cached_introspection = AsyncMock(return_value=None)

        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("network error")
        v._http_client = mock_client

        result = await v.introspect_token("token")
        assert result is True


# ---------------------------------------------------------------------------
# TestValidateTokenWithIntrospection
# ---------------------------------------------------------------------------


class TestValidateTokenWithIntrospection:
    """Test validate_token_with_introspection for active and revoked tokens."""

    @pytest.mark.asyncio
    async def test_active_token_returns_claims(self):
        v = JWTValidator()
        expected_claims = {"sub": "user1", "iss": "https://auth.example.com"}
        v.validate_token = AsyncMock(return_value=expected_claims)
        v.introspect_token = AsyncMock(return_value=True)
        result = await v.validate_token_with_introspection("token")
        assert result == expected_claims
        v.validate_token.assert_called_once_with("token")
        v.introspect_token.assert_called_once_with("token")

    @pytest.mark.asyncio
    async def test_revoked_token_raises(self):
        v = JWTValidator()
        expected_claims = {"sub": "user1"}
        v.validate_token = AsyncMock(return_value=expected_claims)
        v.introspect_token = AsyncMock(return_value=False)
        with pytest.raises(TokenRevokedError, match="Token has been revoked"):
            await v.validate_token_with_introspection("token")


# ---------------------------------------------------------------------------
# TestClose
# ---------------------------------------------------------------------------


class TestClose:
    """Test close method cleans up clients properly."""

    @pytest.mark.asyncio
    async def test_close_with_clients(self):
        v = JWTValidator()
        mock_http = AsyncMock()
        mock_redis = AsyncMock()
        v._http_client = mock_http
        v._redis_client = mock_redis
        await v.close()
        mock_http.aclose.assert_called_once()
        mock_redis.aclose.assert_called_once()
        assert v._http_client is None
        assert v._redis_client is None

    @pytest.mark.asyncio
    async def test_close_without_clients(self):
        v = JWTValidator()
        assert v._http_client is None
        assert v._redis_client is None
        # Should not raise
        await v.close()
        assert v._http_client is None
        assert v._redis_client is None

    @pytest.mark.asyncio
    async def test_close_with_only_http_client(self):
        v = JWTValidator()
        mock_http = AsyncMock()
        v._http_client = mock_http
        await v.close()
        mock_http.aclose.assert_called_once()
        assert v._http_client is None
        assert v._redis_client is None

    @pytest.mark.asyncio
    async def test_close_with_only_redis_client(self):
        v = JWTValidator()
        mock_redis = AsyncMock()
        v._redis_client = mock_redis
        await v.close()
        mock_redis.aclose.assert_called_once()
        assert v._http_client is None
        assert v._redis_client is None
