# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for health, discovery, and JWKS routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class TestHealth:
    @pytest.mark.asyncio
    async def test_health_returns_healthy(self):
        from auth.api.routes.health import health

        result = await health()
        assert result.status == "healthy"


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


class TestOpenIDConfiguration:
    @pytest.mark.asyncio
    @patch("auth.api.routes.discovery.get_issuer_from_context", new_callable=AsyncMock)
    async def test_returns_configuration(self, mock_issuer):
        from auth.api.routes.discovery import openid_configuration

        mock_issuer.return_value = "https://auth.example.com"
        request = MagicMock()
        db = AsyncMock()

        result = (await openid_configuration(request, db)).model_dump()

        assert result["issuer"] == "https://auth.example.com"
        assert result["authorization_endpoint"] == "https://auth.example.com/oauth2/authorize"
        assert result["token_endpoint"] == "https://auth.example.com/oauth2/token"
        assert result["userinfo_endpoint"] == "https://auth.example.com/userinfo"
        assert result["jwks_uri"] == "https://auth.example.com/.well-known/jwks.json"
        assert result["revocation_endpoint"] == "https://auth.example.com/oauth2/revoke"
        assert result["introspection_endpoint"] == "https://auth.example.com/oauth2/introspect"
        assert result["device_authorization_endpoint"] == "https://auth.example.com/oauth2/device"
        assert (
            result["pushed_authorization_request_endpoint"] == "https://auth.example.com/oauth2/par"
        )
        assert result["registration_endpoint"] == "https://auth.example.com/auth/register"
        assert "openid" in result["scopes_supported"]
        assert "code" in result["response_types_supported"]
        assert "authorization_code" in result["grant_types_supported"]
        assert result["id_token_signing_alg_values_supported"] == ["RS256"]
        assert result["request_parameter_supported"] is True


# ---------------------------------------------------------------------------
# JWKS
# ---------------------------------------------------------------------------


class TestJWKS:
    @pytest.mark.asyncio
    async def test_returns_keys(self):
        from auth.api.routes.jwks import jwks

        db = AsyncMock()
        jwks_service = MagicMock()

        key1 = MagicMock()
        key2 = MagicMock()
        jwks_service.get_all_public_keys = AsyncMock(return_value=[key1, key2])
        jwks_service.to_jwk_public.side_effect = [
            {"kty": "RSA", "kid": "k1"},
            {"kty": "RSA", "kid": "k2"},
        ]

        result = (await jwks(db, jwks_service)).model_dump()

        assert len(result["keys"]) == 2
        assert result["keys"][0]["kid"] == "k1"
        assert result["keys"][1]["kid"] == "k2"

    @pytest.mark.asyncio
    async def test_returns_empty_keys(self):
        from auth.api.routes.jwks import jwks

        db = AsyncMock()
        jwks_service = MagicMock()
        jwks_service.get_all_public_keys = AsyncMock(return_value=[])

        result = (await jwks(db, jwks_service)).model_dump()

        assert result["keys"] == []
