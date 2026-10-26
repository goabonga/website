# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.jar — JARService (RFC 9101)."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from auth.services.jar import (
    JWKS_CACHE_TTL,
    SUPPORTED_ALGORITHMS,
    JARError,
    JARService,
    _jwks_clients,
)
from jwt import PyJWKClientError


@pytest.fixture(autouse=True)
def clear_jwks_cache():
    """Clear global JWKS client cache between tests."""
    _jwks_clients.clear()
    yield
    _jwks_clients.clear()


@pytest.fixture
def service():
    return JARService()


@pytest.fixture
def client():
    c = MagicMock()
    c.client_id = "test_client"
    c.jwks_uri = "https://client.example.com/.well-known/jwks.json"
    c.request_object_signing_alg = "RS256"
    return c


# ── JARError ────────────────────────────────────────────────────────────────


class TestJARError:
    def test_attributes(self):
        err = JARError("invalid_request", "bad JWT")
        assert err.error == "invalid_request"
        assert err.description == "bad JWT"
        assert str(err) == "bad JWT"


# ── _get_jwks_client ────────────────────────────────────────────────────────


class TestGetJwksClient:
    def test_creates_new_client(self, service):
        with patch("auth.services.jar.PyJWKClient") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance
            result = service._get_jwks_client("https://example.com/jwks")
        assert result is mock_instance

    def test_returns_cached(self, service):
        mock_client = MagicMock()
        _jwks_clients["https://example.com/jwks"] = (mock_client, time.time())
        result = service._get_jwks_client("https://example.com/jwks")
        assert result is mock_client

    def test_expired_cache_creates_new(self, service):
        old_client = MagicMock()
        _jwks_clients["https://example.com/jwks"] = (
            old_client,
            time.time() - JWKS_CACHE_TTL - 1,
        )
        with patch("auth.services.jar.PyJWKClient") as MockClient:
            new_client = MagicMock()
            MockClient.return_value = new_client
            result = service._get_jwks_client("https://example.com/jwks")
        assert result is new_client


# ── fetch_client_jwks ───────────────────────────────────────────────────────


class TestFetchClientJwks:
    @pytest.mark.asyncio
    async def test_success(self, service):
        jwks = {"keys": [{"kty": "RSA"}]}
        mock_response = MagicMock()
        mock_response.json.return_value = jwks
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get.return_value = mock_response

        with patch("auth.services.jar.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await service.fetch_client_jwks("https://example.com/jwks")
        assert result == jwks

    @pytest.mark.asyncio
    async def test_http_error(self, service):
        import httpx

        mock_http = AsyncMock()
        mock_http.get.side_effect = httpx.HTTPError("fail")

        with patch("auth.services.jar.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            with pytest.raises(JARError, match="Failed to fetch"):
                await service.fetch_client_jwks("https://example.com/jwks")

    @pytest.mark.asyncio
    async def test_parse_error(self, service):
        mock_http = AsyncMock()
        mock_http.get.side_effect = ValueError("bad json")

        with patch("auth.services.jar.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            with pytest.raises(JARError, match="Failed to parse"):
                await service.fetch_client_jwks("https://example.com/jwks")


# ── validate_request_object ─────────────────────────────────────────────────


class TestValidateRequestObject:
    def test_no_jwks_uri(self, service, client):
        client.jwks_uri = None
        with pytest.raises(JARError, match="no jwks_uri"):
            service.validate_request_object("jwt", client)

    def test_unsupported_algorithm(self, service, client):
        client.request_object_signing_alg = "HS256"
        with pytest.raises(JARError, match="Unsupported signing"):
            service.validate_request_object("jwt", client)

    def test_default_algorithm(self, service, client):
        client.request_object_signing_alg = None
        mock_key = MagicMock()
        mock_key.key = "fake_key"
        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_key

        with (
            patch.object(service, "_get_jwks_client", return_value=mock_jwks_client),
            patch("auth.services.jar.jwt.decode", return_value={"iss": "c", "aud": "a", "exp": 9}),
        ):
            result = service.validate_request_object("jwt", client)
        assert result == {"iss": "c", "aud": "a", "exp": 9}

    def test_success(self, service, client):
        mock_key = MagicMock()
        mock_key.key = "fake_key"
        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_key

        claims = {"iss": "test_client", "aud": "https://auth.example.com", "exp": 999}
        with (
            patch.object(service, "_get_jwks_client", return_value=mock_jwks_client),
            patch("auth.services.jar.jwt.decode", return_value=claims),
        ):
            result = service.validate_request_object(
                "jwt",
                client,
                expected_issuer="test_client",
                expected_audience="https://auth.example.com",
            )
        assert result == claims

    def test_jwks_client_error(self, service, client):
        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt.side_effect = PyJWKClientError("fail")

        with (
            patch.object(service, "_get_jwks_client", return_value=mock_jwks_client),
            pytest.raises(JARError, match="Failed to get signing key"),
        ):
            service.validate_request_object("jwt", client)

    def test_expired_signature(self, service, client):
        mock_key = MagicMock()
        mock_key.key = "fake_key"
        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_key

        with (
            patch.object(service, "_get_jwks_client", return_value=mock_jwks_client),
            patch("auth.services.jar.jwt.decode", side_effect=pyjwt.ExpiredSignatureError()),
            pytest.raises(JARError, match="expired"),
        ):
            service.validate_request_object("jwt", client)

    def test_invalid_issuer(self, service, client):
        mock_key = MagicMock()
        mock_key.key = "fake_key"
        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_key

        with (
            patch.object(service, "_get_jwks_client", return_value=mock_jwks_client),
            patch("auth.services.jar.jwt.decode", side_effect=pyjwt.InvalidIssuerError()),
            pytest.raises(JARError, match="Invalid issuer"),
        ):
            service.validate_request_object("jwt", client)

    def test_invalid_audience(self, service, client):
        mock_key = MagicMock()
        mock_key.key = "fake_key"
        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_key

        with (
            patch.object(service, "_get_jwks_client", return_value=mock_jwks_client),
            patch("auth.services.jar.jwt.decode", side_effect=pyjwt.InvalidAudienceError()),
            pytest.raises(JARError, match="Invalid audience"),
        ):
            service.validate_request_object("jwt", client)

    def test_invalid_signature(self, service, client):
        mock_key = MagicMock()
        mock_key.key = "fake_key"
        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_key

        with (
            patch.object(service, "_get_jwks_client", return_value=mock_jwks_client),
            patch("auth.services.jar.jwt.decode", side_effect=pyjwt.InvalidSignatureError()),
            pytest.raises(JARError, match="Invalid signature"),
        ):
            service.validate_request_object("jwt", client)

    def test_decode_error(self, service, client):
        mock_key = MagicMock()
        mock_key.key = "fake_key"
        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_key

        with (
            patch.object(service, "_get_jwks_client", return_value=mock_jwks_client),
            patch("auth.services.jar.jwt.decode", side_effect=pyjwt.DecodeError("bad")),
            pytest.raises(JARError, match="Failed to decode"),
        ):
            service.validate_request_object("jwt", client)

    def test_generic_exception(self, service, client):
        mock_key = MagicMock()
        mock_key.key = "fake_key"
        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_key

        with (
            patch.object(service, "_get_jwks_client", return_value=mock_jwks_client),
            patch("auth.services.jar.jwt.decode", side_effect=RuntimeError("unknown")),
            pytest.raises(JARError, match="validation failed"),
        ):
            service.validate_request_object("jwt", client)


# ── extract_authorization_params ────────────────────────────────────────────


class TestExtractAuthorizationParams:
    def test_success(self, service, client):
        claims = {
            "response_type": "code",
            "redirect_uri": "https://app.example.com/callback",
            "scope": "openid profile",
            "state": "abc",
            "nonce": "xyz",
            "code_challenge": "challenge",
            "code_challenge_method": "S256",
            "prompt": "consent",
        }
        result = service.extract_authorization_params(claims, client)
        assert result["response_type"] == "code"
        assert result["scopes"] == ["openid", "profile"]
        assert result["state"] == "abc"
        assert result["prompt"] == "consent"

    def test_no_scope_defaults_openid(self, service, client):
        claims = {
            "response_type": "code",
            "redirect_uri": "https://app.example.com/callback",
        }
        result = service.extract_authorization_params(claims, client)
        assert result["scopes"] == ["openid"]

    def test_missing_response_type(self, service, client):
        claims = {"redirect_uri": "https://app.example.com/callback"}
        with pytest.raises(JARError, match="response_type is required"):
            service.extract_authorization_params(claims, client)

    def test_missing_redirect_uri(self, service, client):
        claims = {"response_type": "code"}
        with pytest.raises(JARError, match="redirect_uri is required"):
            service.extract_authorization_params(claims, client)

    def test_client_id_mismatch(self, service, client):
        claims = {
            "response_type": "code",
            "redirect_uri": "https://app.example.com/callback",
            "client_id": "wrong_client",
        }
        with pytest.raises(JARError, match="client_id.*does not match"):
            service.extract_authorization_params(claims, client)

    def test_client_id_matches(self, service, client):
        claims = {
            "response_type": "code",
            "redirect_uri": "https://app.example.com/callback",
            "client_id": "test_client",
        }
        result = service.extract_authorization_params(claims, client)
        assert result["response_type"] == "code"


# ── constants ───────────────────────────────────────────────────────────────


class TestConstants:
    def test_supported_algorithms(self):
        assert "RS256" in SUPPORTED_ALGORITHMS
        assert "ES256" in SUPPORTED_ALGORITHMS
        assert "HS256" not in SUPPORTED_ALGORITHMS
