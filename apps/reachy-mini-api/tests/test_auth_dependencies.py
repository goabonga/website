# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for reachy_mini_api/auth/dependencies.py (JWT validation and scope checks)."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import jwt
import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from reachy_mini_api.auth.dependencies import (
    AuthContext,
    _extract_bearer_token,
    _get_oauth2_scheme,
    get_auth_context,
    get_current_user,
    require_scopes,
)
from reachy_mini_api.auth.jwks import jwks_manager
from reachy_mini_api.auth.models import User

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


# ---------------------------------------------------------------------------
# _get_oauth2_scheme
# ---------------------------------------------------------------------------


class TestGetOAuth2Scheme:
    def test_returns_none_when_not_configured(self):
        with patch("reachy_mini_api.auth.dependencies.settings") as mock_settings:
            mock_settings.oauth2_issuer = None
            result = _get_oauth2_scheme()
            assert result is None

    def test_returns_scheme_when_configured(self):
        with patch("reachy_mini_api.auth.dependencies.settings") as mock_settings:
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


def _claims(scope="resource:read", **extra):
    return {"sub": str(uuid4()), "email": "test@example.com", "scope": scope, **extra}


class TestGetAuthContext:
    async def test_missing_token_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            await get_auth_context(request=MagicMock(), token=None)
        assert exc_info.value.status_code == 401
        assert "Missing authorization token" in exc_info.value.detail

    async def test_not_configured_raises_503(self):
        with patch("reachy_mini_api.auth.dependencies.jwks_manager") as mock_jwks:
            mock_jwks.is_configured = False
            with pytest.raises(HTTPException) as exc_info:
                await get_auth_context(request=MagicMock(), token="some-token")
        assert exc_info.value.status_code == 503

    async def test_valid_token(self):
        claims = _claims(client_id="client")
        with (
            patch.object(
                jwks_manager, "validate_token", AsyncMock(return_value=claims)
            ) as mock_validate,
            patch("reachy_mini_api.auth.dependencies.set_request_context") as mock_ctx,
        ):
            request = MagicMock()
            ctx = await get_auth_context(request=request, token="a.b.c")

        assert ctx.user_id == claims["sub"]
        assert ctx.scopes == ["resource:read"]
        mock_validate.assert_awaited_once_with("a.b.c")
        mock_ctx.assert_called_once_with(user_id=claims["sub"], client_id="client")
        assert request.state.user_id == claims["sub"]
        assert request.state.client_id == "client"

    async def test_invalid_token_raises_401(self):
        with (
            patch.object(
                jwks_manager, "validate_token", AsyncMock(side_effect=jwt.InvalidTokenError("bad"))
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await get_auth_context(request=MagicMock(), token="a.b.c")
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid token"
        assert "invalid_token" in exc_info.value.headers["WWW-Authenticate"]

    async def test_token_without_subject_raises_401(self):
        with (
            patch.object(jwks_manager, "validate_token", AsyncMock(return_value={"scope": "x"})),
            pytest.raises(HTTPException) as exc_info,
        ):
            await get_auth_context(request=MagicMock(), token="a.b.c")
        assert exc_info.value.status_code == 401

    async def test_client_id_fallback_to_azp(self):
        claims = _claims(azp="azp-client")
        with patch.object(jwks_manager, "validate_token", AsyncMock(return_value=claims)):
            request = MagicMock()
            await get_auth_context(request=request, token="a.b.c")
        assert request.state.client_id == "azp-client"


# ---------------------------------------------------------------------------
# require_scopes
# ---------------------------------------------------------------------------


class TestRequireScopes:
    async def _call(self, dependency, claims=None, token="a.b.c", validate=None):
        with patch.object(
            jwks_manager, "validate_token", validate or AsyncMock(return_value=claims)
        ):
            return await dependency(request=MagicMock(), token=token)

    async def test_missing_token_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            await self._call(require_scopes("resource:read"), token=None)
        assert exc_info.value.status_code == 401
        assert exc_info.value.headers["WWW-Authenticate"] == "Bearer"

    async def test_not_configured_raises_503(self):
        dependency = require_scopes("resource:read")
        with patch("reachy_mini_api.auth.dependencies.jwks_manager") as mock_jwks:
            mock_jwks.is_configured = False
            with pytest.raises(HTTPException) as exc_info:
                await dependency(request=MagicMock(), token="a.b.c")
        assert exc_info.value.status_code == 503

    async def test_sufficient_scopes(self):
        claims = _claims(scope="resource:read resource:write")
        ctx = await self._call(require_scopes("resource:read"), claims)
        assert isinstance(ctx, AuthContext)
        assert ctx.has_scope("resource:write")

    async def test_insufficient_scopes_raises_403(self):
        with pytest.raises(HTTPException) as exc_info:
            await self._call(require_scopes("admin:all"), _claims())
        assert exc_info.value.status_code == 403
        assert "Missing: admin:all" in exc_info.value.detail
        assert "insufficient_scope" in exc_info.value.headers["WWW-Authenticate"]

    async def test_every_scope_is_required(self):
        with pytest.raises(HTTPException) as exc_info:
            await self._call(require_scopes("resource:read", "resource:write"), _claims())
        assert exc_info.value.status_code == 403
        assert "resource:write" in exc_info.value.detail

    async def test_wildcard_scopes_match(self):
        ctx = await self._call(require_scopes("resource:read"), _claims(scope="resource:*"))
        assert ctx.has_scope("resource:read")

    async def test_super_wildcard_matches(self):
        ctx = await self._call(require_scopes("anything:at:all"), _claims(scope="*"))
        assert ctx.has_scope("anything:at:all")

    async def test_scopes_as_list_claim(self):
        claims = {"sub": str(uuid4()), "scp": ["resource:read"]}
        ctx = await self._call(require_scopes("resource:read"), claims)
        assert ctx.scopes == ["resource:read"]

    async def test_invalid_token_raises_401(self):
        validate = AsyncMock(side_effect=jwt.InvalidTokenError("expired"))
        with pytest.raises(HTTPException) as exc_info:
            await self._call(require_scopes("resource:read"), validate=validate)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid token"

    async def test_empty_scope_list_only_needs_a_valid_token(self):
        ctx = await self._call(require_scopes(), _claims(scope=""))
        assert ctx.scopes == []

    async def test_sets_request_context(self):
        claims = _claims(client_id="client")
        dependency = require_scopes("resource:read")
        with (
            patch.object(jwks_manager, "validate_token", AsyncMock(return_value=claims)),
            patch("reachy_mini_api.auth.dependencies.set_request_context") as mock_ctx,
        ):
            request = MagicMock()
            await dependency(request=request, token="a.b.c")
        mock_ctx.assert_called_once_with(user_id=claims["sub"], client_id="client")
        assert request.state.user_id == claims["sub"]


class TestProtectedRoute:
    """End-to-end behaviour of require_scopes inside a FastAPI application."""

    @pytest.fixture
    def client(self):
        app = FastAPI()

        @app.get("/protected")
        async def protected(auth: AuthContext = Depends(require_scopes("resource:read"))):
            return {"user": auth.user_id}

        return TestClient(app)

    def test_no_authorization_header(self, client):
        response = client.get("/protected")
        assert response.status_code == 401

    def test_valid_bearer_token(self, client):
        claims = _claims()
        with patch.object(jwks_manager, "validate_token", AsyncMock(return_value=claims)):
            response = client.get("/protected", headers={"Authorization": "Bearer a.b.c"})
        assert response.status_code == 200
        assert response.json() == {"user": claims["sub"]}

    def test_missing_scope(self, client):
        with patch.object(
            jwks_manager, "validate_token", AsyncMock(return_value=_claims(scope="other:read"))
        ):
            response = client.get("/protected", headers={"Authorization": "Bearer a.b.c"})
        assert response.status_code == 403


class TestModuleLevelOAuth2Scheme:
    def test_oauth2_scheme_is_callable(self):
        from reachy_mini_api.auth.dependencies import oauth2_scheme

        assert callable(oauth2_scheme)
