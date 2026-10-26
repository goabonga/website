# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the token exchange path of reachy_mini_api/auth/dependencies.py."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from reachy_mini_api.auth.dependencies import require_scopes
from reachy_mini_api.auth.token_exchange import TokenExchangeError


class TestRequireScopesTokenExchangePath:
    @pytest.mark.asyncio
    async def test_exchange_success_with_claims(self):
        uid = str(uuid4())
        dep = require_scopes("resource:read")
        exchange_result = {
            "access_token": "new",
            "scope": "resource:read resource:write",
            "claims": {"sub": uid, "scope": "resource:read resource:write", "client_id": "c"},
        }
        with (
            patch("reachy_mini_api.auth.dependencies.settings") as mock_settings,
            patch("reachy_mini_api.auth.dependencies.jwks_manager") as mock_jwks,
            patch("reachy_mini_api.auth.dependencies.token_exchange_client") as mock_tex,
            patch("reachy_mini_api.auth.dependencies.set_request_context"),
        ):
            mock_settings.oauth2_client_id = "client"
            mock_jwks.is_configured = True
            mock_tex.is_configured = True
            mock_tex.validate_token_scopes = AsyncMock(return_value=exchange_result)
            auth = await dep(request=MagicMock(), token="header.payload.signature")
            assert auth.user.scopes == ["resource:read", "resource:write"]

    @pytest.mark.asyncio
    async def test_exchange_success_without_claims_fallback_to_introspection(self):
        uid = str(uuid4())
        dep = require_scopes("resource:read")
        exchange_result = {"access_token": "new", "scope": "resource:read"}
        claims = {"sub": uid, "scope": "resource:read", "client_id": "c"}
        with (
            patch("reachy_mini_api.auth.dependencies.settings") as mock_settings,
            patch("reachy_mini_api.auth.dependencies.jwks_manager") as mock_jwks,
            patch("reachy_mini_api.auth.dependencies.token_exchange_client") as mock_tex,
            patch("reachy_mini_api.auth.dependencies.introspection_client") as mock_intro,
            patch("reachy_mini_api.auth.dependencies.set_request_context"),
        ):
            mock_settings.oauth2_client_id = "client"
            mock_jwks.is_configured = True
            mock_tex.is_configured = True
            mock_tex.validate_token_scopes = AsyncMock(return_value=exchange_result)
            mock_intro.validate_token_with_introspection = AsyncMock(return_value=claims)
            auth = await dep(request=MagicMock(), token="header.payload.signature")
            assert auth.user.scopes == ["resource:read"]

    @pytest.mark.asyncio
    async def test_exchange_success_introspection_fallback_fails(self):
        dep = require_scopes("resource:read")
        exchange_result = {"access_token": "new", "scope": "resource:read"}
        with (
            patch("reachy_mini_api.auth.dependencies.settings") as mock_settings,
            patch("reachy_mini_api.auth.dependencies.jwks_manager") as mock_jwks,
            patch("reachy_mini_api.auth.dependencies.token_exchange_client") as mock_tex,
            patch("reachy_mini_api.auth.dependencies.introspection_client") as mock_intro,
        ):
            mock_settings.oauth2_client_id = "client"
            mock_jwks.is_configured = True
            mock_tex.is_configured = True
            mock_tex.validate_token_scopes = AsyncMock(return_value=exchange_result)
            mock_intro.validate_token_with_introspection = AsyncMock(
                side_effect=Exception("validation failed")
            )
            with pytest.raises(HTTPException) as exc_info:
                await dep(request=MagicMock(), token="header.payload.signature")
            assert exc_info.value.status_code == 401
            assert "Token validation failed" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_exchange_error_insufficient_scope(self):
        dep = require_scopes("resource:read")
        with (
            patch("reachy_mini_api.auth.dependencies.jwks_manager") as mock_jwks,
            patch("reachy_mini_api.auth.dependencies.token_exchange_client") as mock_tex,
        ):
            mock_jwks.is_configured = True
            mock_tex.is_configured = True
            mock_tex.validate_token_scopes = AsyncMock(
                side_effect=TokenExchangeError("insufficient", error_code="insufficient_scope")
            )
            with pytest.raises(HTTPException) as exc_info:
                await dep(request=MagicMock(), token="header.payload.signature")
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_exchange_error_invalid_grant(self):
        dep = require_scopes("resource:read")
        with (
            patch("reachy_mini_api.auth.dependencies.jwks_manager") as mock_jwks,
            patch("reachy_mini_api.auth.dependencies.token_exchange_client") as mock_tex,
        ):
            mock_jwks.is_configured = True
            mock_tex.is_configured = True
            mock_tex.validate_token_scopes = AsyncMock(
                side_effect=TokenExchangeError("expired", error_code="invalid_grant")
            )
            with pytest.raises(HTTPException) as exc_info:
                await dep(request=MagicMock(), token="header.payload.signature")
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_exchange_error_generic(self):
        dep = require_scopes("resource:read")
        with (
            patch("reachy_mini_api.auth.dependencies.jwks_manager") as mock_jwks,
            patch("reachy_mini_api.auth.dependencies.token_exchange_client") as mock_tex,
        ):
            mock_jwks.is_configured = True
            mock_tex.is_configured = True
            mock_tex.validate_token_scopes = AsyncMock(
                side_effect=TokenExchangeError("unknown", error_code="exchange_error")
            )
            with pytest.raises(HTTPException) as exc_info:
                await dep(request=MagicMock(), token="header.payload.signature")
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_sets_request_context_on_success(self):
        uid = str(uuid4())
        dep = require_scopes("resource:read")
        exchange_result = {
            "access_token": "new",
            "scope": "resource:read",
            "claims": {"sub": uid, "scope": "resource:read", "client_id": "my-client"},
        }
        request = MagicMock()
        with (
            patch("reachy_mini_api.auth.dependencies.settings") as mock_settings,
            patch("reachy_mini_api.auth.dependencies.jwks_manager") as mock_jwks,
            patch("reachy_mini_api.auth.dependencies.token_exchange_client") as mock_tex,
            patch("reachy_mini_api.auth.dependencies.set_request_context") as mock_set_ctx,
        ):
            mock_settings.oauth2_client_id = "fallback"
            mock_jwks.is_configured = True
            mock_tex.is_configured = True
            mock_tex.validate_token_scopes = AsyncMock(return_value=exchange_result)
            await dep(request=request, token="header.payload.signature")
            mock_set_ctx.assert_called_once()
            assert request.state.client_id == "my-client"


# ---------------------------------------------------------------------------
# require_scopes — direct validation (JWT, no exchange)
# ---------------------------------------------------------------------------


class TestExchangeSkipped:
    @pytest.mark.asyncio
    async def test_exchange_not_called_for_opaque(self):
        """Token exchange is skipped for opaque tokens even when configured."""
        uid = str(uuid4())
        dep = require_scopes("resource:read")
        claims = {"sub": uid, "scope": "resource:read", "client_id": "svc"}
        with (
            patch("reachy_mini_api.auth.dependencies.settings") as mock_settings,
            patch("reachy_mini_api.auth.dependencies.jwks_manager") as mock_jwks,
            patch("reachy_mini_api.auth.dependencies.token_exchange_client") as mock_tex,
            patch("reachy_mini_api.auth.dependencies.introspection_client") as mock_intro,
            patch("reachy_mini_api.auth.dependencies.set_request_context"),
        ):
            mock_settings.oauth2_client_id = "client"
            mock_jwks.is_configured = True
            mock_tex.is_configured = True
            mock_intro.validate_opaque_token = AsyncMock(return_value=claims)
            await dep(request=MagicMock(), token="ory_pat_abc123")
            mock_tex.validate_token_scopes.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_scopes_skips_exchange(self):
        """When require_scopes() is called with no arguments, exchange is skipped."""
        uid = str(uuid4())
        dep = require_scopes()
        claims = {"sub": uid, "scope": "resource:read", "client_id": "c"}
        with (
            patch("reachy_mini_api.auth.dependencies.settings") as mock_settings,
            patch("reachy_mini_api.auth.dependencies.jwks_manager") as mock_jwks,
            patch("reachy_mini_api.auth.dependencies.token_exchange_client") as mock_tex,
            patch("reachy_mini_api.auth.dependencies.introspection_client") as mock_intro,
            patch("reachy_mini_api.auth.dependencies.set_request_context"),
        ):
            mock_settings.oauth2_client_id = "client"
            mock_jwks.is_configured = True
            mock_tex.is_configured = True
            mock_intro.validate_token_with_introspection = AsyncMock(return_value=claims)
            auth = await dep(request=MagicMock(), token="header.payload.signature")
            assert auth is not None
            mock_tex.validate_token_scopes.assert_not_called()

    @pytest.mark.asyncio
    async def test_direct_validation_when_exchange_not_configured(self):
        """Without a confidential client the scopes of the token itself are checked."""
        claims = {"sub": str(uuid4()), "scope": "other:read"}
        dep = require_scopes("resource:read")
        with (
            patch("reachy_mini_api.auth.dependencies.jwks_manager") as mock_jwks,
            patch("reachy_mini_api.auth.dependencies.token_exchange_client") as mock_tex,
            patch("reachy_mini_api.auth.dependencies.introspection_client") as mock_intro,
        ):
            mock_jwks.is_configured = True
            mock_tex.is_configured = False
            mock_intro.validate_token_with_introspection = AsyncMock(return_value=claims)
            with pytest.raises(HTTPException) as exc_info:
                await dep(request=MagicMock(), token="header.payload.signature")
            assert exc_info.value.status_code == 403
