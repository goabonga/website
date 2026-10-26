# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.api.routes.discovery — OIDC Discovery endpoint."""

from unittest.mock import AsyncMock, patch

import pytest

MODULE = "auth.api.routes.discovery"


class TestOpenidConfiguration:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_issuer_from_context", new_callable=AsyncMock)
    async def test_returns_discovery_document(self, mock_issuer):
        from auth.api.routes.discovery import openid_configuration

        mock_issuer.return_value = "https://auth.example.com"
        request = AsyncMock()
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
        mock_issuer.assert_awaited_once_with(db)

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_issuer_from_context", new_callable=AsyncMock)
    async def test_scopes_supported(self, mock_issuer):
        from auth.api.routes.discovery import openid_configuration

        mock_issuer.return_value = "https://auth.example.com"

        result = (await openid_configuration(AsyncMock(), AsyncMock())).model_dump()

        assert "openid" in result["scopes_supported"]
        assert "profile" in result["scopes_supported"]
        assert "email" in result["scopes_supported"]
        assert "offline_access" in result["scopes_supported"]

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_issuer_from_context", new_callable=AsyncMock)
    async def test_response_types_supported(self, mock_issuer):
        from auth.api.routes.discovery import openid_configuration

        mock_issuer.return_value = "https://auth.example.com"

        result = (await openid_configuration(AsyncMock(), AsyncMock())).model_dump()

        assert "code" in result["response_types_supported"]
        assert "token" in result["response_types_supported"]
        assert "id_token" in result["response_types_supported"]

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_issuer_from_context", new_callable=AsyncMock)
    async def test_grant_types_supported(self, mock_issuer):
        from auth.api.routes.discovery import openid_configuration

        mock_issuer.return_value = "https://auth.example.com"

        result = (await openid_configuration(AsyncMock(), AsyncMock())).model_dump()

        grants = result["grant_types_supported"]
        assert "authorization_code" in grants
        assert "refresh_token" in grants
        assert "client_credentials" in grants
        assert "urn:ietf:params:oauth:grant-type:device_code" in grants
        assert "urn:ietf:params:oauth:grant-type:token-exchange" in grants

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_issuer_from_context", new_callable=AsyncMock)
    async def test_static_fields(self, mock_issuer):
        from auth.api.routes.discovery import openid_configuration

        mock_issuer.return_value = "https://auth.example.com"

        result = (await openid_configuration(AsyncMock(), AsyncMock())).model_dump()

        assert result["subject_types_supported"] == ["pairwise"]
        assert result["id_token_signing_alg_values_supported"] == ["RS256"]
        assert "client_secret_basic" in result["token_endpoint_auth_methods_supported"]
        assert "client_secret_post" in result["token_endpoint_auth_methods_supported"]
        assert "none" in result["token_endpoint_auth_methods_supported"]
        assert result["code_challenge_methods_supported"] == ["S256", "plain"]
        assert result["request_parameter_supported"] is True
        assert result["request_uri_parameter_supported"] is True
        assert result["require_request_uri_registration"] is True

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_issuer_from_context", new_callable=AsyncMock)
    async def test_subject_types_always_pairwise(self, mock_issuer):
        from auth.api.routes.discovery import openid_configuration

        mock_issuer.return_value = "https://auth.example.com"

        result = (await openid_configuration(AsyncMock(), AsyncMock())).model_dump()

        assert result["subject_types_supported"] == ["pairwise"]

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_issuer_from_context", new_callable=AsyncMock)
    async def test_claims_supported(self, mock_issuer):
        from auth.api.routes.discovery import openid_configuration

        mock_issuer.return_value = "https://auth.example.com"

        result = (await openid_configuration(AsyncMock(), AsyncMock())).model_dump()

        expected_claims = [
            "sub",
            "iss",
            "aud",
            "exp",
            "iat",
            "auth_time",
            "nonce",
            "name",
            "email",
            "email_verified",
        ]
        assert result["claims_supported"] == expected_claims

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_issuer_from_context", new_callable=AsyncMock)
    async def test_response_modes_supported(self, mock_issuer):
        from auth.api.routes.discovery import openid_configuration

        mock_issuer.return_value = "https://auth.example.com"

        result = (await openid_configuration(AsyncMock(), AsyncMock())).model_dump()

        assert result["response_modes_supported"] == ["query", "fragment", "form_post"]

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_issuer_from_context", new_callable=AsyncMock)
    async def test_different_issuer(self, mock_issuer):
        from auth.api.routes.discovery import openid_configuration

        mock_issuer.return_value = "https://id.acme.corp"

        result = (await openid_configuration(AsyncMock(), AsyncMock())).model_dump()

        assert result["issuer"] == "https://id.acme.corp"
        assert result["authorization_endpoint"] == "https://id.acme.corp/oauth2/authorize"
        assert result["jwks_uri"] == "https://id.acme.corp/.well-known/jwks.json"
