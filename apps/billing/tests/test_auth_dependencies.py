# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for billing/auth/dependencies.py — unit tests only (no project-specific endpoints)."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from billing.auth.dependencies import (
    AuthContext,
    _extract_bearer_token,
    _get_oauth2_scheme,
    _is_jwt_token,
    get_auth_context,
    get_current_user,
    require_scopes,
)
from billing.auth.introspection import TokenRevokedError
from billing.auth.models import User
from billing.auth.token_exchange import TokenExchangeError
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# _is_jwt_token
# ---------------------------------------------------------------------------


class TestIsJwtToken:
    def test_three_non_empty_parts_returns_true(self):
        assert _is_jwt_token("header.payload.signature") is True

    def test_real_jwt_format_returns_true(self):
        assert _is_jwt_token("eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.sig") is True

    def test_opaque_token_returns_false(self):
        assert _is_jwt_token("ory_pat_abc123def456") is False

    def test_two_parts_returns_false(self):
        assert _is_jwt_token("header.payload") is False

    def test_four_parts_returns_false(self):
        assert _is_jwt_token("a.b.c.d") is False

    def test_empty_part_returns_false(self):
        assert _is_jwt_token("header..signature") is False

    def test_plain_string_returns_false(self):
        assert _is_jwt_token("simple-token") is False

    def test_empty_string_returns_false(self):
        assert _is_jwt_token("") is False


# ---------------------------------------------------------------------------
# _extract_bearer_token
# ---------------------------------------------------------------------------


class TestExtractBearerToken:
    @pytest.mark.asyncio
    async def test_extracts_bearer_token(self):
        request = MagicMock()
        request.headers = {"Authorization": "Bearer my-token"}
        result = await _extract_bearer_token(request)
        assert result == "my-token"

    @pytest.mark.asyncio
    async def test_returns_none_no_authorization_header(self):
        request = MagicMock()
        request.headers.get.return_value = ""
        result = await _extract_bearer_token(request)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_non_bearer_scheme(self):
        request = MagicMock()
        request.headers = {"Authorization": "Basic abc123"}
        result = await _extract_bearer_token(request)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_empty_authorization(self):
        request = MagicMock()
        request.headers = {"Authorization": ""}
        result = await _extract_bearer_token(request)
        assert result is None


# ---------------------------------------------------------------------------
# _get_oauth2_scheme
# ---------------------------------------------------------------------------


class TestGetOAuth2Scheme:
    def test_returns_none_when_not_configured(self):
        with patch("billing.auth.dependencies.settings") as mock_settings:
            mock_settings.oauth2_issuer = None
            result = _get_oauth2_scheme()
            assert result is None

    def test_returns_scheme_when_configured(self):
        with patch("billing.auth.dependencies.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            result = _get_oauth2_scheme()
            assert result is not None


# ---------------------------------------------------------------------------
# AuthContext
# ---------------------------------------------------------------------------


@pytest.fixture
def test_user():
    return User(
        id=uuid4(),
        email="test@example.com",
        name="Test User",
        scopes=["resource:read", "resource:write"],
        is_machine_client=False,
        client_id="test-client",
    )


class TestAuthContext:
    def test_user_property(self, test_user):
        ctx = AuthContext(user=test_user)
        assert ctx.user is test_user

    def test_user_id(self, test_user):
        ctx = AuthContext(user=test_user)
        assert ctx.user_id == str(test_user.id)

    def test_scopes(self, test_user):
        ctx = AuthContext(user=test_user)
        assert ctx.scopes == ["resource:read", "resource:write"]

    def test_has_scope_true(self, test_user):
        ctx = AuthContext(user=test_user)
        assert ctx.has_scope("resource:read") is True

    def test_has_scope_false(self, test_user):
        ctx = AuthContext(user=test_user)
        assert ctx.has_scope("admin:all") is False

    def test_require_scope_passes(self, test_user):
        ctx = AuthContext(user=test_user)
        ctx.require_scope("resource:read")  # should not raise

    def test_require_scope_fails_with_403(self, test_user):
        ctx = AuthContext(user=test_user)
        with pytest.raises(HTTPException) as exc_info:
            ctx.require_scope("admin:all")
        assert exc_info.value.status_code == 403
        assert "Missing required scope" in exc_info.value.detail


# ---------------------------------------------------------------------------
# get_current_user
# ---------------------------------------------------------------------------


class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_returns_user_from_context(self, test_user):
        ctx = AuthContext(user=test_user)
        result = await get_current_user(auth=ctx)
        assert result is test_user


# ---------------------------------------------------------------------------
# get_auth_context
# ---------------------------------------------------------------------------


class TestGetAuthContext:
    @pytest.mark.asyncio
    async def test_missing_token_raises_401(self):
        request = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            await get_auth_context(request=request, token=None)
        assert exc_info.value.status_code == 401
        assert "Missing authorization token" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_not_configured_raises_503(self):
        with patch("billing.auth.dependencies.jwks_manager") as mock_jwks:
            mock_jwks.is_configured = False
            with pytest.raises(HTTPException) as exc_info:
                await get_auth_context(request=MagicMock(), token="some-token")
            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_valid_jwt_token(self):
        uid = str(uuid4())
        claims = {
            "sub": uid,
            "email": "test@example.com",
            "scope": "resource:read",
            "client_id": "client",
        }
        with (
            patch("billing.auth.dependencies.settings") as mock_settings,
            patch("billing.auth.dependencies.jwks_manager") as mock_jwks,
            patch("billing.auth.dependencies.introspection_client") as mock_intro,
            patch("billing.auth.dependencies.set_request_context"),
        ):
            mock_settings.oauth2_client_id = "client"
            mock_jwks.is_configured = True
            mock_intro.validate_token_with_introspection = AsyncMock(return_value=claims)
            auth = await get_auth_context(request=MagicMock(), token="header.payload.signature")
            assert auth.user.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_valid_opaque_token(self):
        uid = str(uuid4())
        claims = {
            "sub": uid,
            "email": "service@example.com",
            "scope": "resource:read",
            "client_id": "svc",
        }
        with (
            patch("billing.auth.dependencies.settings") as mock_settings,
            patch("billing.auth.dependencies.jwks_manager") as mock_jwks,
            patch("billing.auth.dependencies.introspection_client") as mock_intro,
            patch("billing.auth.dependencies.set_request_context"),
        ):
            mock_settings.oauth2_client_id = "client"
            mock_jwks.is_configured = True
            mock_intro.validate_opaque_token = AsyncMock(return_value=claims)
            auth = await get_auth_context(request=MagicMock(), token="ory_pat_abc123")
            assert auth.user.email == "service@example.com"
            mock_intro.validate_opaque_token.assert_awaited_once_with("ory_pat_abc123")

    @pytest.mark.asyncio
    async def test_jwt_revoked_raises_401(self):
        with (
            patch("billing.auth.dependencies.jwks_manager") as mock_jwks,
            patch("billing.auth.dependencies.introspection_client") as mock_intro,
        ):
            mock_jwks.is_configured = True
            mock_intro.validate_token_with_introspection = AsyncMock(
                side_effect=TokenRevokedError("revoked")
            )
            with pytest.raises(HTTPException) as exc_info:
                await get_auth_context(request=MagicMock(), token="header.payload.signature")
            assert exc_info.value.status_code == 401
            assert "revoked" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_opaque_revoked_raises_401(self):
        with (
            patch("billing.auth.dependencies.jwks_manager") as mock_jwks,
            patch("billing.auth.dependencies.introspection_client") as mock_intro,
        ):
            mock_jwks.is_configured = True
            mock_intro.validate_opaque_token = AsyncMock(
                side_effect=TokenRevokedError("not active")
            )
            with pytest.raises(HTTPException) as exc_info:
                await get_auth_context(request=MagicMock(), token="ory_pat_revoked")
            assert exc_info.value.status_code == 401
            assert "revoked" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_invalid_jwt_raises_401(self):
        with (
            patch("billing.auth.dependencies.jwks_manager") as mock_jwks,
            patch("billing.auth.dependencies.introspection_client") as mock_intro,
        ):
            mock_jwks.is_configured = True
            mock_intro.validate_token_with_introspection = AsyncMock(
                side_effect=Exception("bad token")
            )
            with pytest.raises(HTTPException) as exc_info:
                await get_auth_context(request=MagicMock(), token="bad.jwt.token")
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_sets_request_context(self):
        uid = str(uuid4())
        claims = {"sub": uid, "scope": "resource:read", "client_id": "my-client"}
        request = MagicMock()
        with (
            patch("billing.auth.dependencies.settings") as mock_settings,
            patch("billing.auth.dependencies.jwks_manager") as mock_jwks,
            patch("billing.auth.dependencies.introspection_client") as mock_intro,
            patch("billing.auth.dependencies.set_request_context") as mock_set_ctx,
        ):
            mock_settings.oauth2_client_id = "fallback"
            mock_jwks.is_configured = True
            mock_intro.validate_token_with_introspection = AsyncMock(return_value=claims)
            await get_auth_context(request=request, token="header.payload.signature")
            mock_set_ctx.assert_called_once()
            assert request.state.client_id == "my-client"

    @pytest.mark.asyncio
    async def test_client_id_fallback_to_azp(self):
        uid = str(uuid4())
        claims = {"sub": uid, "scope": "resource:read", "azp": "azp-client"}
        request = MagicMock()
        with (
            patch("billing.auth.dependencies.settings") as mock_settings,
            patch("billing.auth.dependencies.jwks_manager") as mock_jwks,
            patch("billing.auth.dependencies.introspection_client") as mock_intro,
            patch("billing.auth.dependencies.set_request_context"),
        ):
            mock_settings.oauth2_client_id = "fallback"
            mock_jwks.is_configured = True
            mock_intro.validate_token_with_introspection = AsyncMock(return_value=claims)
            await get_auth_context(request=request, token="header.payload.signature")
            assert request.state.client_id == "azp-client"

    @pytest.mark.asyncio
    async def test_client_id_fallback_to_settings(self):
        uid = str(uuid4())
        claims = {"sub": uid, "scope": "resource:read"}
        request = MagicMock()
        with (
            patch("billing.auth.dependencies.settings") as mock_settings,
            patch("billing.auth.dependencies.jwks_manager") as mock_jwks,
            patch("billing.auth.dependencies.introspection_client") as mock_intro,
            patch("billing.auth.dependencies.set_request_context"),
        ):
            mock_settings.oauth2_client_id = "fallback-client"
            mock_jwks.is_configured = True
            mock_intro.validate_token_with_introspection = AsyncMock(return_value=claims)
            await get_auth_context(request=request, token="header.payload.signature")
            assert request.state.client_id == "fallback-client"


# ---------------------------------------------------------------------------
# require_scopes — missing token and config
# ---------------------------------------------------------------------------


class TestRequireScopesMissingTokenAndConfig:
    @pytest.mark.asyncio
    async def test_missing_token_raises_401(self):
        dep = require_scopes("resource:read")
        with pytest.raises(HTTPException) as exc_info:
            await dep(request=MagicMock(), token=None)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_not_configured_raises_503(self):
        dep = require_scopes("resource:read")
        with patch("billing.auth.dependencies.jwks_manager") as mock_jwks:
            mock_jwks.is_configured = False
            with pytest.raises(HTTPException) as exc_info:
                await dep(request=MagicMock(), token="some-token")
            assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# require_scopes — token exchange path (JWT + exchange configured + scopes)
# ---------------------------------------------------------------------------


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
            patch("billing.auth.dependencies.settings") as mock_settings,
            patch("billing.auth.dependencies.jwks_manager") as mock_jwks,
            patch("billing.auth.dependencies.token_exchange_client") as mock_tex,
            patch("billing.auth.dependencies.introspection_client") as mock_intro,
            patch("billing.auth.dependencies.set_request_context"),
        ):
            mock_settings.oauth2_client_id = "client"
            mock_jwks.is_configured = True
            mock_tex.is_configured = True
            mock_tex.validate_token_scopes = AsyncMock(return_value=exchange_result)
            mock_intro.validate_token_with_introspection = AsyncMock(
                return_value={"sub": uid, "scope": "resource:read", "client_id": "caller"}
            )
            auth = await dep(request=MagicMock(), token="header.payload.signature")
            assert auth.user.scopes == ["resource:read", "resource:write"]

    @pytest.mark.asyncio
    async def test_exchange_success_without_claims_fallback_to_introspection(self):
        uid = str(uuid4())
        dep = require_scopes("resource:read")
        exchange_result = {"access_token": "new", "scope": "resource:read"}
        claims = {"sub": uid, "scope": "resource:read", "client_id": "c"}
        with (
            patch("billing.auth.dependencies.settings") as mock_settings,
            patch("billing.auth.dependencies.jwks_manager") as mock_jwks,
            patch("billing.auth.dependencies.token_exchange_client") as mock_tex,
            patch("billing.auth.dependencies.introspection_client") as mock_intro,
            patch("billing.auth.dependencies.set_request_context"),
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
            patch("billing.auth.dependencies.settings") as mock_settings,
            patch("billing.auth.dependencies.jwks_manager") as mock_jwks,
            patch("billing.auth.dependencies.token_exchange_client") as mock_tex,
            patch("billing.auth.dependencies.introspection_client") as mock_intro,
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
            patch("billing.auth.dependencies.jwks_manager") as mock_jwks,
            patch("billing.auth.dependencies.token_exchange_client") as mock_tex,
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
            patch("billing.auth.dependencies.jwks_manager") as mock_jwks,
            patch("billing.auth.dependencies.token_exchange_client") as mock_tex,
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
            patch("billing.auth.dependencies.jwks_manager") as mock_jwks,
            patch("billing.auth.dependencies.token_exchange_client") as mock_tex,
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
            patch("billing.auth.dependencies.settings") as mock_settings,
            patch("billing.auth.dependencies.jwks_manager") as mock_jwks,
            patch("billing.auth.dependencies.token_exchange_client") as mock_tex,
            patch("billing.auth.dependencies.introspection_client") as mock_intro,
            patch("billing.auth.dependencies.set_request_context") as mock_set_ctx,
        ):
            mock_settings.oauth2_client_id = "fallback"
            mock_jwks.is_configured = True
            mock_tex.is_configured = True
            mock_tex.validate_token_scopes = AsyncMock(return_value=exchange_result)
            mock_intro.validate_token_with_introspection = AsyncMock(
                return_value={"sub": uid, "scope": "resource:read", "client_id": "my-client"}
            )
            await dep(request=request, token="header.payload.signature")
            mock_set_ctx.assert_called_once()
            assert request.state.client_id == "my-client"


# ---------------------------------------------------------------------------
# require_scopes — direct validation (JWT, no exchange)
# ---------------------------------------------------------------------------


class TestRequireScopesDirectValidationJWT:
    @pytest.mark.asyncio
    async def test_sufficient_scopes(self):
        uid = str(uuid4())
        dep = require_scopes("resource:read")
        claims = {"sub": uid, "scope": "resource:read resource:write", "client_id": "c"}
        with (
            patch("billing.auth.dependencies.settings") as mock_settings,
            patch("billing.auth.dependencies.jwks_manager") as mock_jwks,
            patch("billing.auth.dependencies.token_exchange_client") as mock_tex,
            patch("billing.auth.dependencies.introspection_client") as mock_intro,
            patch("billing.auth.dependencies.set_request_context"),
        ):
            mock_settings.oauth2_client_id = "client"
            mock_jwks.is_configured = True
            mock_tex.is_configured = False
            mock_intro.validate_token_with_introspection = AsyncMock(return_value=claims)
            auth = await dep(request=MagicMock(), token="header.payload.signature")
            assert auth.user.scopes == ["resource:read", "resource:write"]

    @pytest.mark.asyncio
    async def test_insufficient_scopes_raises_403(self):
        uid = str(uuid4())
        dep = require_scopes("resource:read")
        claims = {"sub": uid, "scope": "openid profile", "client_id": "c"}
        with (
            patch("billing.auth.dependencies.settings") as mock_settings,
            patch("billing.auth.dependencies.jwks_manager") as mock_jwks,
            patch("billing.auth.dependencies.token_exchange_client") as mock_tex,
            patch("billing.auth.dependencies.introspection_client") as mock_intro,
        ):
            mock_settings.oauth2_client_id = "client"
            mock_jwks.is_configured = True
            mock_tex.is_configured = False
            mock_intro.validate_token_with_introspection = AsyncMock(return_value=claims)
            with pytest.raises(HTTPException) as exc_info:
                await dep(request=MagicMock(), token="header.payload.signature")
            assert exc_info.value.status_code == 403
            assert "resource:read" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_wildcard_scopes_match(self):
        uid = str(uuid4())
        dep = require_scopes("resource:read")
        claims = {"sub": uid, "scope": "resource:*", "client_id": "c"}
        with (
            patch("billing.auth.dependencies.settings") as mock_settings,
            patch("billing.auth.dependencies.jwks_manager") as mock_jwks,
            patch("billing.auth.dependencies.token_exchange_client") as mock_tex,
            patch("billing.auth.dependencies.introspection_client") as mock_intro,
            patch("billing.auth.dependencies.set_request_context"),
        ):
            mock_settings.oauth2_client_id = "client"
            mock_jwks.is_configured = True
            mock_tex.is_configured = False
            mock_intro.validate_token_with_introspection = AsyncMock(return_value=claims)
            auth = await dep(request=MagicMock(), token="header.payload.signature")
            assert auth is not None

    @pytest.mark.asyncio
    async def test_revoked_raises_401(self):
        dep = require_scopes("resource:read")
        with (
            patch("billing.auth.dependencies.jwks_manager") as mock_jwks,
            patch("billing.auth.dependencies.token_exchange_client") as mock_tex,
            patch("billing.auth.dependencies.introspection_client") as mock_intro,
        ):
            mock_jwks.is_configured = True
            mock_tex.is_configured = False
            mock_intro.validate_token_with_introspection = AsyncMock(
                side_effect=TokenRevokedError("revoked")
            )
            with pytest.raises(HTTPException) as exc_info:
                await dep(request=MagicMock(), token="header.payload.signature")
            assert exc_info.value.status_code == 401
            assert "revoked" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_invalid_raises_401(self):
        dep = require_scopes("resource:read")
        with (
            patch("billing.auth.dependencies.jwks_manager") as mock_jwks,
            patch("billing.auth.dependencies.token_exchange_client") as mock_tex,
            patch("billing.auth.dependencies.introspection_client") as mock_intro,
        ):
            mock_jwks.is_configured = True
            mock_tex.is_configured = False
            mock_intro.validate_token_with_introspection = AsyncMock(
                side_effect=Exception("bad token")
            )
            with pytest.raises(HTTPException) as exc_info:
                await dep(request=MagicMock(), token="header.payload.signature")
            assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# require_scopes — direct validation (opaque token)
# ---------------------------------------------------------------------------


class TestRequireScopesDirectValidationOpaque:
    @pytest.mark.asyncio
    async def test_sufficient_scopes(self):
        uid = str(uuid4())
        dep = require_scopes("resource:read")
        claims = {"sub": uid, "scope": "resource:read resource:write", "client_id": "svc"}
        with (
            patch("billing.auth.dependencies.settings") as mock_settings,
            patch("billing.auth.dependencies.jwks_manager") as mock_jwks,
            patch("billing.auth.dependencies.token_exchange_client") as mock_tex,
            patch("billing.auth.dependencies.introspection_client") as mock_intro,
            patch("billing.auth.dependencies.set_request_context"),
        ):
            mock_settings.oauth2_client_id = "client"
            mock_jwks.is_configured = True
            mock_tex.is_configured = True  # exchange configured, but skipped for opaque
            mock_intro.validate_opaque_token = AsyncMock(return_value=claims)
            auth = await dep(request=MagicMock(), token="ory_pat_abc123")
            assert auth.user.scopes == ["resource:read", "resource:write"]

    @pytest.mark.asyncio
    async def test_insufficient_scopes_raises_403(self):
        uid = str(uuid4())
        dep = require_scopes("resource:read")
        claims = {"sub": uid, "scope": "openid", "client_id": "svc"}
        with (
            patch("billing.auth.dependencies.settings") as mock_settings,
            patch("billing.auth.dependencies.jwks_manager") as mock_jwks,
            patch("billing.auth.dependencies.token_exchange_client") as mock_tex,
            patch("billing.auth.dependencies.introspection_client") as mock_intro,
        ):
            mock_settings.oauth2_client_id = "client"
            mock_jwks.is_configured = True
            mock_tex.is_configured = True
            mock_intro.validate_opaque_token = AsyncMock(return_value=claims)
            with pytest.raises(HTTPException) as exc_info:
                await dep(request=MagicMock(), token="ory_pat_abc123")
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_revoked_raises_401(self):
        dep = require_scopes("resource:read")
        with (
            patch("billing.auth.dependencies.jwks_manager") as mock_jwks,
            patch("billing.auth.dependencies.token_exchange_client") as mock_tex,
            patch("billing.auth.dependencies.introspection_client") as mock_intro,
        ):
            mock_jwks.is_configured = True
            mock_tex.is_configured = True
            mock_intro.validate_opaque_token = AsyncMock(
                side_effect=TokenRevokedError("not active")
            )
            with pytest.raises(HTTPException) as exc_info:
                await dep(request=MagicMock(), token="ory_pat_revoked")
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_raises_401(self):
        dep = require_scopes("resource:read")
        with (
            patch("billing.auth.dependencies.jwks_manager") as mock_jwks,
            patch("billing.auth.dependencies.token_exchange_client") as mock_tex,
            patch("billing.auth.dependencies.introspection_client") as mock_intro,
        ):
            mock_jwks.is_configured = True
            mock_tex.is_configured = True
            mock_intro.validate_opaque_token = AsyncMock(
                side_effect=Exception("introspection failed")
            )
            with pytest.raises(HTTPException) as exc_info:
                await dep(request=MagicMock(), token="ory_pat_bad")
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_exchange_not_called_for_opaque(self):
        """Token exchange is skipped for opaque tokens even when configured."""
        uid = str(uuid4())
        dep = require_scopes("resource:read")
        claims = {"sub": uid, "scope": "resource:read", "client_id": "svc"}
        with (
            patch("billing.auth.dependencies.settings") as mock_settings,
            patch("billing.auth.dependencies.jwks_manager") as mock_jwks,
            patch("billing.auth.dependencies.token_exchange_client") as mock_tex,
            patch("billing.auth.dependencies.introspection_client") as mock_intro,
            patch("billing.auth.dependencies.set_request_context"),
        ):
            mock_settings.oauth2_client_id = "client"
            mock_jwks.is_configured = True
            mock_tex.is_configured = True
            mock_intro.validate_opaque_token = AsyncMock(return_value=claims)
            await dep(request=MagicMock(), token="ory_pat_abc123")
            mock_tex.validate_token_scopes.assert_not_called()


# ---------------------------------------------------------------------------
# require_scopes — empty scopes list
# ---------------------------------------------------------------------------


class TestRequireScopesEmptyScopesList:
    @pytest.mark.asyncio
    async def test_empty_scopes_skips_exchange(self):
        """When require_scopes() is called with no arguments, exchange is skipped."""
        uid = str(uuid4())
        dep = require_scopes()
        claims = {"sub": uid, "scope": "resource:read", "client_id": "c"}
        with (
            patch("billing.auth.dependencies.settings") as mock_settings,
            patch("billing.auth.dependencies.jwks_manager") as mock_jwks,
            patch("billing.auth.dependencies.token_exchange_client") as mock_tex,
            patch("billing.auth.dependencies.introspection_client") as mock_intro,
            patch("billing.auth.dependencies.set_request_context"),
        ):
            mock_settings.oauth2_client_id = "client"
            mock_jwks.is_configured = True
            mock_tex.is_configured = True
            mock_intro.validate_token_with_introspection = AsyncMock(return_value=claims)
            auth = await dep(request=MagicMock(), token="header.payload.signature")
            assert auth is not None
            mock_tex.validate_token_scopes.assert_not_called()


# ---------------------------------------------------------------------------
# Module-level oauth2_scheme
# ---------------------------------------------------------------------------


class TestModuleLevelOAuth2Scheme:
    def test_oauth2_scheme_is_callable(self):
        from billing.auth.dependencies import oauth2_scheme

        assert callable(oauth2_scheme)


# ---------------------------------------------------------------------------
# Identity of the caller (used by the partitioning of the API)
# ---------------------------------------------------------------------------


class TestCallerIdentity:
    """The OAuth client of the caller is read from the token it presented."""

    @pytest.mark.asyncio
    async def test_exchange_path_uses_the_presented_token_not_the_exchanged_one(self):
        """The exchanged token belongs to this service's own client."""
        uid = str(uuid4())
        dep = require_scopes("resource:read")
        exchange_result = {
            "access_token": "new",
            "scope": "resource:read",
            "claims": {"sub": uid, "scope": "resource:read", "client_id": "billing-own-client"},
        }
        presented = {
            "sub": uid,
            "scope": "resource:read billing:admin",
            "client_id": "caller-client",
        }
        with (
            patch("billing.auth.dependencies.settings") as mock_settings,
            patch("billing.auth.dependencies.jwks_manager") as mock_jwks,
            patch("billing.auth.dependencies.token_exchange_client") as mock_tex,
            patch("billing.auth.dependencies.introspection_client") as mock_intro,
            patch("billing.auth.dependencies.set_request_context"),
        ):
            mock_settings.oauth2_client_id = "billing-own-client"
            mock_jwks.is_configured = True
            mock_tex.is_configured = True
            mock_tex.validate_token_scopes = AsyncMock(return_value=exchange_result)
            mock_intro.validate_token_with_introspection = AsyncMock(return_value=presented)

            auth = await dep(request=MagicMock(), token="header.payload.signature")

        assert auth.client_id == "caller-client"
        assert auth.user.scopes == ["resource:read"]
        assert auth.token_scopes == ["resource:read", "billing:admin"]
        assert auth.has_token_scope("billing:admin") is True

    @pytest.mark.asyncio
    async def test_exchange_path_refuses_a_token_that_cannot_be_introspected(self):
        dep = require_scopes("resource:read")
        exchange_result = {"access_token": "new", "scope": "resource:read", "claims": {"sub": "u"}}
        with (
            patch("billing.auth.dependencies.settings"),
            patch("billing.auth.dependencies.jwks_manager") as mock_jwks,
            patch("billing.auth.dependencies.token_exchange_client") as mock_tex,
            patch("billing.auth.dependencies.introspection_client") as mock_intro,
        ):
            mock_jwks.is_configured = True
            mock_tex.is_configured = True
            mock_tex.validate_token_scopes = AsyncMock(return_value=exchange_result)
            mock_intro.validate_token_with_introspection = AsyncMock(side_effect=Exception("down"))

            with pytest.raises(HTTPException) as exc_info:
                await dep(request=MagicMock(), token="header.payload.signature")

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_direct_validation_reads_client_id_then_azp(self):
        uid = str(uuid4())
        dep = require_scopes("resource:read")
        for claims, expected in (
            ({"sub": uid, "scope": "resource:read", "client_id": "machine"}, "machine"),
            ({"sub": uid, "scope": "resource:read", "azp": "web-app"}, "web-app"),
            ({"sub": uid, "scope": "resource:read"}, None),
        ):
            with (
                patch("billing.auth.dependencies.jwks_manager") as mock_jwks,
                patch("billing.auth.dependencies.token_exchange_client") as mock_tex,
                patch("billing.auth.dependencies.introspection_client") as mock_intro,
                patch("billing.auth.dependencies.set_request_context"),
            ):
                mock_jwks.is_configured = True
                mock_tex.is_configured = False
                mock_intro.validate_token_with_introspection = AsyncMock(return_value=claims)

                auth = await dep(request=MagicMock(), token="header.payload.signature")

            assert auth.client_id == expected

    @pytest.mark.asyncio
    async def test_client_id_never_falls_back_to_this_services_own_client(self):
        """A token without client claim stays anonymous even if a client id is configured."""
        dep = require_scopes("resource:read")
        claims = {"sub": str(uuid4()), "scope": "resource:read"}
        with (
            patch("billing.auth.dependencies.settings") as mock_settings,
            patch("billing.auth.dependencies.jwks_manager") as mock_jwks,
            patch("billing.auth.dependencies.token_exchange_client") as mock_tex,
            patch("billing.auth.dependencies.introspection_client") as mock_intro,
            patch("billing.auth.dependencies.set_request_context"),
        ):
            mock_settings.oauth2_client_id = "billing-own-client"
            mock_jwks.is_configured = True
            mock_tex.is_configured = False
            mock_intro.validate_token_with_introspection = AsyncMock(return_value=claims)

            auth = await dep(request=MagicMock(), token="header.payload.signature")

        assert auth.client_id is None

    def test_auth_context_defaults_to_the_user(self):
        user = User(id="u", scopes=["a", "b:*"], client_id="c")

        context = AuthContext(user=user)

        assert context.client_id == "c"
        assert context.token_scopes == ["a", "b:*"]
        assert context.has_token_scope("b:read") is True
        assert context.has_token_scope("x") is False
