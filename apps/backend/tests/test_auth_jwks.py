# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for backend/auth/jwks.py."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import jwt as pyjwt
import pytest
from backend.auth.jwks import JWKSManager, jwks_manager
from jwt import PyJWKClientError


class TestJWKSManagerInit:
    """Tests for JWKSManager initialization."""

    def test_init_empty_state(self):
        """Initialize with empty state."""
        mgr = JWKSManager()
        assert mgr._jwks_client is None
        assert mgr._issuer_config is None
        assert mgr._config_fetched_at == 0
        assert mgr._http_client is None


class TestJWKSManagerProperties:
    """Tests for JWKSManager properties."""

    @patch("backend.auth.jwks.settings")
    def test_issuer_strips_trailing_slash(self, mock_settings):
        mock_settings.oauth2_issuer = "https://auth.example.com/"
        mgr = JWKSManager()
        assert mgr.issuer == "https://auth.example.com"

    @patch("backend.auth.jwks.settings")
    def test_issuer_no_trailing_slash(self, mock_settings):
        mock_settings.oauth2_issuer = "https://auth.example.com"
        mgr = JWKSManager()
        assert mgr.issuer == "https://auth.example.com"

    @patch("backend.auth.jwks.settings")
    def test_is_configured_true(self, mock_settings):
        mock_settings.oauth2_issuer = "https://auth.example.com"
        mgr = JWKSManager()
        assert mgr.is_configured is True

    @patch("backend.auth.jwks.settings")
    def test_is_configured_false(self, mock_settings):
        mock_settings.oauth2_issuer = ""
        mgr = JWKSManager()
        assert mgr.is_configured is False


class TestJWKSManagerAcceptedIssuers:
    """Tests for accepted_issuers property."""

    @patch("backend.auth.jwks.settings")
    def test_primary_issuer_only(self, mock_settings):
        mock_settings.oauth2_issuer = "https://auth.example.com"
        mock_settings.oauth2_trusted_issuers = ""
        mgr = JWKSManager()
        assert mgr.accepted_issuers == ["https://auth.example.com"]

    @patch("backend.auth.jwks.settings")
    def test_primary_plus_trusted(self, mock_settings):
        mock_settings.oauth2_issuer = "https://auth.example.com"
        mock_settings.oauth2_trusted_issuers = "https://other.issuer.com"
        mgr = JWKSManager()
        assert mgr.accepted_issuers == ["https://auth.example.com", "https://other.issuer.com"]

    @patch("backend.auth.jwks.settings")
    def test_multiple_trusted_comma_separated(self, mock_settings):
        mock_settings.oauth2_issuer = "https://auth.example.com"
        mock_settings.oauth2_trusted_issuers = "https://a.com, https://b.com"
        mgr = JWKSManager()
        assert mgr.accepted_issuers == [
            "https://auth.example.com",
            "https://a.com",
            "https://b.com",
        ]

    @patch("backend.auth.jwks.settings")
    def test_empty_entries_filtered(self, mock_settings):
        mock_settings.oauth2_issuer = "https://auth.example.com"
        mock_settings.oauth2_trusted_issuers = ",, https://a.com,,"
        mgr = JWKSManager()
        assert mgr.accepted_issuers == ["https://auth.example.com", "https://a.com"]


class TestJWKSManagerHttpClient:
    """Tests for _get_http_client()."""

    @pytest.mark.asyncio
    async def test_creates_client_on_first_call(self):
        mgr = JWKSManager()
        client = await mgr._get_http_client()
        assert isinstance(client, httpx.AsyncClient)
        await mgr.close()

    @pytest.mark.asyncio
    async def test_reuses_existing_client(self):
        mgr = JWKSManager()
        c1 = await mgr._get_http_client()
        c2 = await mgr._get_http_client()
        assert c1 is c2
        await mgr.close()


class TestJWKSManagerFetchIssuerConfig:
    """Tests for fetch_issuer_config()."""

    @pytest.mark.asyncio
    @patch("backend.auth.jwks.settings")
    async def test_raises_when_not_configured(self, mock_settings):
        mock_settings.oauth2_issuer = ""
        mgr = JWKSManager()
        with pytest.raises(ValueError, match="not configured"):
            await mgr.fetch_issuer_config()

    @pytest.mark.asyncio
    @patch("backend.auth.jwks.settings")
    async def test_fetches_and_caches_config(self, mock_settings):
        mock_settings.oauth2_issuer = "https://auth.example.com"
        mock_settings.jwks_cache_ttl = 3600
        mgr = JWKSManager()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jwks_uri": "https://auth.example.com/.well-known/jwks.json",
            "token_endpoint": "https://auth.example.com/oauth2/token",
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mgr._http_client = mock_client

        config = await mgr.fetch_issuer_config()
        assert config["jwks_uri"] == "https://auth.example.com/.well-known/jwks.json"
        mock_client.get.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("backend.auth.jwks.settings")
    async def test_returns_cached_within_ttl(self, mock_settings):
        mock_settings.oauth2_issuer = "https://auth.example.com"
        mock_settings.jwks_cache_ttl = 3600
        mgr = JWKSManager()
        mgr._issuer_config = {"jwks_uri": "cached_uri"}
        mgr._config_fetched_at = time.time()

        config = await mgr.fetch_issuer_config()
        assert config["jwks_uri"] == "cached_uri"

    @pytest.mark.asyncio
    @patch("backend.auth.jwks.settings")
    async def test_refetches_when_ttl_expired(self, mock_settings):
        mock_settings.oauth2_issuer = "https://auth.example.com"
        mock_settings.jwks_cache_ttl = 3600
        mgr = JWKSManager()
        mgr._issuer_config = {"jwks_uri": "old_uri"}
        mgr._config_fetched_at = time.time() - 4000

        mock_response = MagicMock()
        mock_response.json.return_value = {"jwks_uri": "new_uri"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mgr._http_client = mock_client

        config = await mgr.fetch_issuer_config()
        assert config["jwks_uri"] == "new_uri"


class TestJWKSManagerGetJwksClient:
    """Tests for _get_jwks_client()."""

    @patch("backend.auth.jwks.settings")
    def test_creates_jwks_client(self, mock_settings):
        mock_settings.jwks_cache_ttl = 3600
        mgr = JWKSManager()
        client = mgr._get_jwks_client("https://auth.example.com/jwks")
        assert client is not None
        assert mgr._jwks_client is client

    @patch("backend.auth.jwks.settings")
    def test_reuses_existing_jwks_client(self, mock_settings):
        mock_settings.jwks_cache_ttl = 3600
        mgr = JWKSManager()
        c1 = mgr._get_jwks_client("https://auth.example.com/jwks")
        c2 = mgr._get_jwks_client("https://auth.example.com/jwks")
        assert c1 is c2


class TestJWKSManagerValidateToken:
    """Tests for validate_token()."""

    @pytest.mark.asyncio
    @patch("backend.auth.jwks.settings")
    async def test_raises_when_not_configured(self, mock_settings):
        mock_settings.oauth2_issuer = ""
        mgr = JWKSManager()
        with pytest.raises(ValueError, match="not configured"):
            await mgr.validate_token("some-token")

    @pytest.mark.asyncio
    @patch("backend.auth.jwks.settings")
    async def test_raises_when_no_jwks_uri(self, mock_settings):
        mock_settings.oauth2_issuer = "https://auth.example.com"
        mock_settings.jwks_cache_ttl = 3600
        mgr = JWKSManager()
        mgr._issuer_config = {}
        mgr._config_fetched_at = time.time()

        with pytest.raises(ValueError, match="JWKS URI not found"):
            await mgr.validate_token("some-token")

    @pytest.mark.asyncio
    @patch("backend.auth.jwks.settings")
    async def test_raises_on_signing_key_error(self, mock_settings):
        mock_settings.oauth2_issuer = "https://auth.example.com"
        mock_settings.jwks_cache_ttl = 3600
        mgr = JWKSManager()
        mgr._issuer_config = {"jwks_uri": "https://auth.example.com/jwks"}
        mgr._config_fetched_at = time.time()

        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt.side_effect = PyJWKClientError("key not found")
        mgr._jwks_client = mock_jwks_client

        with pytest.raises(pyjwt.InvalidTokenError, match="Failed to get signing key"):
            await mgr.validate_token("bad-token")

    @pytest.mark.asyncio
    @patch("backend.auth.jwks.settings")
    async def test_success_returns_claims(self, mock_settings):
        mock_settings.oauth2_issuer = "https://auth.example.com"
        mock_settings.oauth2_trusted_issuers = ""
        mock_settings.jwks_cache_ttl = 3600
        mgr = JWKSManager()
        mgr._issuer_config = {"jwks_uri": "https://auth.example.com/jwks"}
        mgr._config_fetched_at = time.time()

        mock_signing_key = MagicMock()
        mock_signing_key.key = "test-key"

        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key
        mgr._jwks_client = mock_jwks_client

        expected_claims = {"sub": "user1", "email": "user@test.com"}

        with patch("backend.auth.jwks.jwt.decode", return_value=expected_claims) as mock_decode:
            claims = await mgr.validate_token("valid-token")

        assert claims == expected_claims
        mock_decode.assert_called_once_with(
            "valid-token",
            "test-key",
            algorithms=["RS256", "ES256"],
            issuer=["https://auth.example.com"],
            options={
                "verify_aud": False,
                "verify_exp": True,
                "verify_iat": True,
                "verify_iss": True,
            },
        )

    @pytest.mark.asyncio
    @patch("backend.auth.jwks.settings")
    async def test_passes_accepted_issuers_to_decode(self, mock_settings):
        """Verify that trusted issuers are passed to jwt.decode."""
        mock_settings.oauth2_issuer = "https://auth.example.com"
        mock_settings.oauth2_trusted_issuers = "https://other.issuer.com"
        mock_settings.jwks_cache_ttl = 3600
        mgr = JWKSManager()
        mgr._issuer_config = {"jwks_uri": "https://auth.example.com/jwks"}
        mgr._config_fetched_at = time.time()

        mock_signing_key = MagicMock()
        mock_signing_key.key = "test-key"

        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key
        mgr._jwks_client = mock_jwks_client

        with patch("backend.auth.jwks.jwt.decode", return_value={"sub": "user1"}) as mock_decode:
            await mgr.validate_token("token")

        call_kwargs = mock_decode.call_args
        assert call_kwargs[1]["issuer"] == ["https://auth.example.com", "https://other.issuer.com"]


class TestJWKSManagerClose:
    """Tests for close()."""

    @pytest.mark.asyncio
    async def test_closes_http_client(self):
        mgr = JWKSManager()
        mock_client = AsyncMock()
        mgr._http_client = mock_client

        await mgr.close()
        mock_client.aclose.assert_awaited_once()
        assert mgr._http_client is None

    @pytest.mark.asyncio
    async def test_noop_when_no_client(self):
        mgr = JWKSManager()
        await mgr.close()
        assert mgr._http_client is None


class TestModuleLevelInstance:
    """Tests for module-level singleton."""

    def test_jwks_manager_exists(self):
        assert isinstance(jwks_manager, JWKSManager)
