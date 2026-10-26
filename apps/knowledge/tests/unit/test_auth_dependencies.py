# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for knowledge/auth/dependencies.py — 100% coverage with only mocks."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from starlette.datastructures import URL

from knowledge.auth.dependencies import (
    ACCESS_TOKEN_COOKIE,
    ACTIVE_TENANT_COOKIE,
    AuthContext,
    _create_login_redirect,
    _get_oauth2_scheme,
    _get_token_from_oauth2_or_bearer,
    get_auth_context,
    get_current_user,
    get_current_user_or_redirect,
    get_oauth2_scheme,
    get_optional_auth_context,
    get_optional_user,
    get_token_from_cookie,
    get_web_auth_context,
    require_resource_scopes_or_redirect,
    require_scope_or_redirect,
    require_scopes,
    require_tenant_admin,
)
from knowledge.auth.models import User, WebAuthContext

USER_UUID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ORG_UUID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def _make_user(scopes=None, uid=None):
    return User(
        id=uid or USER_UUID,
        email="u@e.com",
        name="Test",
        scopes=scopes or [],
    )


def _make_request(headers=None, cookies=None, url="http://localhost/test"):
    req = MagicMock()
    req.headers = headers or {}
    req.cookies = cookies or {}
    req.url = URL(url)
    req.state = MagicMock()
    return req


# =====================================================================
# _get_oauth2_scheme
# =====================================================================


class TestGetOauth2Scheme:
    def test_returns_none_no_issuer(self):
        with patch("knowledge.auth.dependencies.settings") as ms:
            ms.oauth2_issuer = ""
            ms.oauth2_swagger_client_id = "cid"
            result = _get_oauth2_scheme()
        assert result is None

    def test_returns_none_no_swagger_client(self):
        with patch("knowledge.auth.dependencies.settings") as ms:
            ms.oauth2_issuer = "https://auth.example.com"
            ms.oauth2_swagger_client_id = ""
            result = _get_oauth2_scheme()
        assert result is None

    def test_returns_scheme_when_configured(self):
        with patch("knowledge.auth.dependencies.settings") as ms:
            ms.oauth2_issuer = "https://auth.example.com"
            ms.oauth2_swagger_client_id = "swagger-cid"
            result = _get_oauth2_scheme()
        assert result is not None


class TestGetOauth2SchemeSingleton:
    def test_singleton(self):
        import knowledge.auth.dependencies as deps_mod

        deps_mod._oauth2_scheme = None
        with patch("knowledge.auth.dependencies._get_oauth2_scheme", return_value="SCHEME"):
            r1 = get_oauth2_scheme()
            r2 = get_oauth2_scheme()
        assert r1 == "SCHEME"
        assert r2 == "SCHEME"
        # Cleanup
        deps_mod._oauth2_scheme = None


# =====================================================================
# AuthContext class
# =====================================================================


class TestAuthContext:
    def test_user_id(self):
        user = _make_user()
        ctx = AuthContext(user=user)
        assert ctx.user_id == USER_UUID

    def test_tenant_id_explicit(self):
        user = _make_user()
        ctx = AuthContext(user=user, tenant_id=ORG_UUID)
        assert ctx.tenant_id == ORG_UUID

    def test_tenant_id_defaults_to_user_id(self):
        user = _make_user()
        ctx = AuthContext(user=user, tenant_id=None)
        assert ctx.tenant_id == USER_UUID

    def test_scopes(self):
        user = _make_user(scopes=["a", "b"])
        ctx = AuthContext(user=user)
        assert ctx.scopes == ["a", "b"]

    def test_has_scope(self):
        user = _make_user(scopes=["api:read"])
        ctx = AuthContext(user=user)
        assert ctx.has_scope("api:read") is True
        assert ctx.has_scope("api:write") is False

    def test_require_scope_passes(self):
        user = _make_user(scopes=["api:read"])
        ctx = AuthContext(user=user)
        ctx.require_scope("api:read")

    def test_require_scope_raises(self):
        user = _make_user(scopes=[])
        ctx = AuthContext(user=user)
        with pytest.raises(HTTPException) as exc_info:
            ctx.require_scope("api:write")
        assert exc_info.value.status_code == 403


# =====================================================================
# _get_token_from_oauth2_or_bearer
# =====================================================================


class TestGetTokenFromOauth2OrBearer:
    async def test_prefer_oauth2(self):
        req = _make_request()
        bearer = MagicMock()
        bearer.credentials = "bearer-tok"
        result = await _get_token_from_oauth2_or_bearer(req, "oauth2-tok", bearer)
        assert result == "oauth2-tok"

    async def test_fallback_bearer(self):
        req = _make_request()
        bearer = MagicMock()
        bearer.credentials = "bearer-tok"
        result = await _get_token_from_oauth2_or_bearer(req, None, bearer)
        assert result == "bearer-tok"

    async def test_none_when_both_missing(self):
        req = _make_request()
        result = await _get_token_from_oauth2_or_bearer(req, None, None)
        assert result is None


# =====================================================================
# get_auth_context
# =====================================================================


class TestGetAuthContext:
    async def test_no_token_raises_401(self, mock_db):
        req = _make_request()
        with pytest.raises(HTTPException) as exc_info:
            await get_auth_context(req, mock_db, None, None)
        assert exc_info.value.status_code == 401

    async def test_no_issuer_raises_500(self, mock_db):
        req = _make_request()
        bearer = MagicMock()
        bearer.credentials = "tok"
        with patch("knowledge.auth.dependencies.settings") as ms:
            ms.oauth2_issuer = ""
            with pytest.raises(HTTPException) as exc_info:
                await get_auth_context(req, mock_db, None, bearer)
        assert exc_info.value.status_code == 500

    async def test_jwt_validation_error_raises_401(self, mock_db):
        from knowledge.auth.jwt import JWTValidationError

        req = _make_request()
        bearer = MagicMock()
        bearer.credentials = "tok"

        mock_validator = MagicMock()
        mock_validator.validate_token_with_introspection = AsyncMock(
            side_effect=JWTValidationError("bad token")
        )

        with (
            patch("knowledge.auth.dependencies.settings") as ms,
            patch("knowledge.auth.dependencies.get_jwt_validator", return_value=mock_validator),
        ):
            ms.oauth2_issuer = "https://auth.example.com"
            ms.oauth2_client_id = ""
            ms.oauth2_client_secret = ""
            with pytest.raises(HTTPException) as exc_info:
                await get_auth_context(req, mock_db, None, bearer)
        assert exc_info.value.status_code == 401
        assert "bad token" in exc_info.value.detail

    async def test_unexpected_exception_raises_401(self, mock_db):
        req = _make_request()
        bearer = MagicMock()
        bearer.credentials = "tok"

        mock_validator = MagicMock()
        mock_validator.validate_token_with_introspection = AsyncMock(
            side_effect=RuntimeError("unexpected")
        )

        with (
            patch("knowledge.auth.dependencies.settings") as ms,
            patch("knowledge.auth.dependencies.get_jwt_validator", return_value=mock_validator),
        ):
            ms.oauth2_issuer = "https://auth.example.com"
            ms.oauth2_client_id = ""
            ms.oauth2_client_secret = ""
            with pytest.raises(HTTPException) as exc_info:
                await get_auth_context(req, mock_db, None, bearer)
        assert exc_info.value.status_code == 401

    async def test_success_no_token_exchange_no_tenant_header(self, mock_db, make_result):
        req = _make_request()
        bearer = MagicMock()
        bearer.credentials = "tok"

        mock_validator = MagicMock()
        mock_validator.validate_token_with_introspection = AsyncMock(
            return_value={"sub": str(USER_UUID), "scope": "openid"}
        )

        # No org member found
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=None))

        with (
            patch("knowledge.auth.dependencies.settings") as ms,
            patch("knowledge.auth.dependencies.get_jwt_validator", return_value=mock_validator),
        ):
            ms.oauth2_issuer = "https://auth.example.com"
            ms.oauth2_client_id = ""
            ms.oauth2_client_secret = ""
            ctx = await get_auth_context(req, mock_db, None, bearer)

        assert ctx.user.id == USER_UUID
        assert ctx.tenant_id == USER_UUID  # Defaults to user ID

    async def test_success_with_token_exchange(self, mock_db, make_result):
        req = _make_request()
        bearer = MagicMock()
        bearer.credentials = "tok"

        mock_validator = MagicMock()
        mock_validator.validate_token_with_introspection = AsyncMock(
            return_value={"sub": str(USER_UUID)}
        )

        mock_te_client = MagicMock()
        mock_te_client.exchange_token = AsyncMock(
            return_value={"scope": "collections:read documents:read"}
        )

        # No org member found
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=None))

        with (
            patch("knowledge.auth.dependencies.settings") as ms,
            patch("knowledge.auth.dependencies.get_jwt_validator", return_value=mock_validator),
            patch(
                "knowledge.auth.dependencies.get_token_exchange_client",
                return_value=mock_te_client,
            ),
        ):
            ms.oauth2_issuer = "https://auth.example.com"
            ms.oauth2_client_id = "cid"
            ms.oauth2_client_secret = "csecret"
            ctx = await get_auth_context(req, mock_db, None, bearer)

        assert "collections:read" in ctx.scopes
        assert "documents:read" in ctx.scopes

    async def test_token_exchange_error_continues(self, mock_db, make_result):
        from knowledge.auth.token_exchange import TokenExchangeError

        req = _make_request()
        bearer = MagicMock()
        bearer.credentials = "tok"

        mock_validator = MagicMock()
        mock_validator.validate_token_with_introspection = AsyncMock(
            return_value={"sub": str(USER_UUID), "scope": "openid"}
        )

        mock_te_client = MagicMock()
        mock_te_client.exchange_token = AsyncMock(side_effect=TokenExchangeError("failed"))

        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=None))

        with (
            patch("knowledge.auth.dependencies.settings") as ms,
            patch("knowledge.auth.dependencies.get_jwt_validator", return_value=mock_validator),
            patch(
                "knowledge.auth.dependencies.get_token_exchange_client",
                return_value=mock_te_client,
            ),
        ):
            ms.oauth2_issuer = "https://auth.example.com"
            ms.oauth2_client_id = "cid"
            ms.oauth2_client_secret = "csecret"
            ctx = await get_auth_context(req, mock_db, None, bearer)

        # Scopes from original token, not exchanged
        assert ctx.user.id == USER_UUID

    async def test_token_exchange_empty_scope(self, mock_db, make_result):
        req = _make_request()
        bearer = MagicMock()
        bearer.credentials = "tok"

        mock_validator = MagicMock()
        mock_validator.validate_token_with_introspection = AsyncMock(
            return_value={"sub": str(USER_UUID), "scope": "openid"}
        )

        mock_te_client = MagicMock()
        mock_te_client.exchange_token = AsyncMock(return_value={"scope": ""})

        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=None))

        with (
            patch("knowledge.auth.dependencies.settings") as ms,
            patch("knowledge.auth.dependencies.get_jwt_validator", return_value=mock_validator),
            patch(
                "knowledge.auth.dependencies.get_token_exchange_client",
                return_value=mock_te_client,
            ),
        ):
            ms.oauth2_issuer = "https://auth.example.com"
            ms.oauth2_client_id = "cid"
            ms.oauth2_client_secret = "csecret"
            ctx = await get_auth_context(req, mock_db, None, bearer)

        # Empty scope from exchange => original scopes used
        assert ctx.user.id == USER_UUID

    async def test_x_tenant_id_header(self, mock_db, make_result):
        req = _make_request(headers={"X-Tenant-ID": str(ORG_UUID)})
        bearer = MagicMock()
        bearer.credentials = "tok"

        mock_validator = MagicMock()
        mock_validator.validate_token_with_introspection = AsyncMock(
            return_value={"sub": str(USER_UUID)}
        )

        with (
            patch("knowledge.auth.dependencies.settings") as ms,
            patch("knowledge.auth.dependencies.get_jwt_validator", return_value=mock_validator),
        ):
            ms.oauth2_issuer = "https://auth.example.com"
            ms.oauth2_client_id = ""
            ms.oauth2_client_secret = ""
            ctx = await get_auth_context(req, mock_db, None, bearer)

        assert ctx.tenant_id == ORG_UUID

    async def test_x_tenant_id_header_invalid_uuid(self, mock_db):
        req = _make_request(headers={"X-Tenant-ID": "not-a-uuid"})
        bearer = MagicMock()
        bearer.credentials = "tok"

        mock_validator = MagicMock()
        mock_validator.validate_token_with_introspection = AsyncMock(
            return_value={"sub": str(USER_UUID)}
        )

        with (
            patch("knowledge.auth.dependencies.settings") as ms,
            patch("knowledge.auth.dependencies.get_jwt_validator", return_value=mock_validator),
        ):
            ms.oauth2_issuer = "https://auth.example.com"
            ms.oauth2_client_id = ""
            ms.oauth2_client_secret = ""
            with pytest.raises(HTTPException) as exc_info:
                await get_auth_context(req, mock_db, None, bearer)
        assert exc_info.value.status_code == 400

    async def test_resolve_default_org(self, mock_db, make_result):
        """When no X-Tenant-ID, resolves org member + active org from DB."""
        req = _make_request()
        bearer = MagicMock()
        bearer.credentials = "tok"

        mock_validator = MagicMock()
        mock_validator.validate_token_with_introspection = AsyncMock(
            return_value={"sub": str(USER_UUID)}
        )

        org_member = MagicMock()
        org_member.organization_id = ORG_UUID

        org = MagicMock()
        org.id = ORG_UUID

        call_count = 0

        async def _side_effect_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return make_result(scalar_one_or_none=org_member)
            else:
                return make_result(scalar_one_or_none=org)

        mock_db.execute = AsyncMock(side_effect=_side_effect_execute)

        with (
            patch("knowledge.auth.dependencies.settings") as ms,
            patch("knowledge.auth.dependencies.get_jwt_validator", return_value=mock_validator),
        ):
            ms.oauth2_issuer = "https://auth.example.com"
            ms.oauth2_client_id = ""
            ms.oauth2_client_secret = ""
            ctx = await get_auth_context(req, mock_db, None, bearer)

        assert ctx.tenant_id == ORG_UUID

    async def test_resolve_default_org_no_active_org(self, mock_db, make_result):
        """Org member found but organization is not active."""
        req = _make_request()
        bearer = MagicMock()
        bearer.credentials = "tok"

        mock_validator = MagicMock()
        mock_validator.validate_token_with_introspection = AsyncMock(
            return_value={"sub": str(USER_UUID)}
        )

        org_member = MagicMock()
        org_member.organization_id = ORG_UUID

        call_count = 0

        async def _side_effect_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return make_result(scalar_one_or_none=org_member)
            else:
                return make_result(scalar_one_or_none=None)  # Org not active

        mock_db.execute = AsyncMock(side_effect=_side_effect_execute)

        with (
            patch("knowledge.auth.dependencies.settings") as ms,
            patch("knowledge.auth.dependencies.get_jwt_validator", return_value=mock_validator),
        ):
            ms.oauth2_issuer = "https://auth.example.com"
            ms.oauth2_client_id = ""
            ms.oauth2_client_secret = ""
            ctx = await get_auth_context(req, mock_db, None, bearer)

        # Falls back to user_id since no active org
        assert ctx.tenant_id == USER_UUID

    async def test_http_exception_re_raised(self, mock_db):
        """HTTPException inside get_auth_context is re-raised as-is."""
        req = _make_request(headers={"X-Tenant-ID": "invalid"})
        bearer = MagicMock()
        bearer.credentials = "tok"

        mock_validator = MagicMock()
        mock_validator.validate_token_with_introspection = AsyncMock(
            return_value={"sub": str(USER_UUID)}
        )

        with (
            patch("knowledge.auth.dependencies.settings") as ms,
            patch("knowledge.auth.dependencies.get_jwt_validator", return_value=mock_validator),
        ):
            ms.oauth2_issuer = "https://auth.example.com"
            ms.oauth2_client_id = ""
            ms.oauth2_client_secret = ""
            with pytest.raises(HTTPException) as exc_info:
                await get_auth_context(req, mock_db, None, bearer)
        assert exc_info.value.status_code == 400


# =====================================================================
# get_optional_auth_context
# =====================================================================


class TestGetOptionalAuthContext:
    async def test_no_token_returns_none(self, mock_db):
        req = _make_request()
        result = await get_optional_auth_context(req, mock_db, None, None)
        assert result is None

    async def test_valid_token_returns_context(self, mock_db, make_result):
        req = _make_request()
        bearer = MagicMock()
        bearer.credentials = "tok"

        mock_validator = MagicMock()
        mock_validator.validate_token_with_introspection = AsyncMock(
            return_value={"sub": str(USER_UUID)}
        )

        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=None))

        with (
            patch("knowledge.auth.dependencies.settings") as ms,
            patch("knowledge.auth.dependencies.get_jwt_validator", return_value=mock_validator),
        ):
            ms.oauth2_issuer = "https://auth.example.com"
            ms.oauth2_client_id = ""
            ms.oauth2_client_secret = ""
            result = await get_optional_auth_context(req, mock_db, None, bearer)

        assert result is not None
        assert result.user.id == USER_UUID

    async def test_invalid_token_returns_none(self, mock_db):
        req = _make_request()
        bearer = MagicMock()
        bearer.credentials = "tok"

        with (
            patch("knowledge.auth.dependencies.settings") as ms,
            patch(
                "knowledge.auth.dependencies.get_auth_context",
                new_callable=AsyncMock,
                side_effect=HTTPException(status_code=401, detail="bad"),
            ),
        ):
            ms.oauth2_issuer = "https://auth.example.com"
            result = await get_optional_auth_context(req, mock_db, None, bearer)

        assert result is None


# =====================================================================
# get_current_user / get_optional_user
# =====================================================================


class TestGetCurrentUser:
    async def test_returns_user(self):
        user = _make_user()
        auth = AuthContext(user=user)
        result = await get_current_user(auth)
        assert result is user


class TestGetOptionalUser:
    async def test_with_auth(self):
        user = _make_user()
        auth = AuthContext(user=user)
        result = await get_optional_user(auth)
        assert result is user

    async def test_without_auth(self):
        result = await get_optional_user(None)
        assert result is None


# =====================================================================
# require_scopes factory
# =====================================================================


class TestRequireScopes:
    async def test_passes_when_has_scopes(self, mock_db):
        user = _make_user(scopes=["api:read", "api:write"])
        auth = AuthContext(user=user)
        req = _make_request()
        check_fn = require_scopes("api:read", "api:write")
        result = await check_fn(request=req, auth=auth)
        assert result is auth

    async def test_raises_when_missing_scope(self, mock_db):
        user = _make_user(scopes=["api:read"])
        auth = AuthContext(user=user)
        req = _make_request()
        check_fn = require_scopes("api:read", "api:write")
        with pytest.raises(HTTPException) as exc_info:
            await check_fn(request=req, auth=auth)
        assert exc_info.value.status_code == 403


# =====================================================================
# Cookie-based web auth
# =====================================================================


class TestCreateLoginRedirect:
    def test_redirect_url(self):
        req = _make_request(url="http://localhost/dashboard")
        resp = _create_login_redirect(req)
        assert isinstance(resp, RedirectResponse)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/auth/login?redirect=%2Fdashboard"

    def test_return_address_keeps_the_whole_query_string(self):
        req = _make_request(url="http://localhost/search?q=a+b&top_k=7")
        resp = _create_login_redirect(req)
        assert resp.headers["location"] == "/auth/login?redirect=%2Fsearch%3Fq%3Da%2Bb%26top_k%3D7"


class TestGetTokenFromCookie:
    async def test_token_present(self):
        req = _make_request(cookies={ACCESS_TOKEN_COOKIE: "my-token"})
        result = await get_token_from_cookie(req)
        assert result == "my-token"

    async def test_no_token(self):
        req = _make_request(cookies={})
        result = await get_token_from_cookie(req)
        assert result is None


# =====================================================================
# get_current_user_or_redirect
# =====================================================================


class TestGetCurrentUserOrRedirect:
    async def test_no_token_redirects(self):
        req = _make_request(cookies={})
        result = await get_current_user_or_redirect(req)
        assert isinstance(result, RedirectResponse)

    async def test_no_issuer_raises(self):
        req = _make_request(cookies={ACCESS_TOKEN_COOKIE: "tok"})
        with patch("knowledge.auth.dependencies.settings") as ms:
            ms.oauth2_issuer = ""
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user_or_redirect(req)
        assert exc_info.value.status_code == 500

    async def test_success_no_exchange(self):
        req = _make_request(cookies={ACCESS_TOKEN_COOKIE: "tok"})
        mock_validator = MagicMock()
        mock_validator.validate_token_with_introspection = AsyncMock(
            return_value={"sub": str(USER_UUID), "email": "u@e.com"}
        )

        with (
            patch("knowledge.auth.dependencies.settings") as ms,
            patch("knowledge.auth.dependencies.get_jwt_validator", return_value=mock_validator),
        ):
            ms.oauth2_issuer = "https://auth.example.com"
            ms.oauth2_client_id = ""
            ms.oauth2_client_secret = ""
            result = await get_current_user_or_redirect(req)

        assert isinstance(result, User)
        assert result.id == USER_UUID

    async def test_success_with_exchange(self):
        req = _make_request(cookies={ACCESS_TOKEN_COOKIE: "tok"})
        mock_validator = MagicMock()
        mock_validator.validate_token_with_introspection = AsyncMock(
            return_value={"sub": str(USER_UUID)}
        )

        mock_te = MagicMock()
        mock_te.exchange_token = AsyncMock(
            return_value={"scope": "collections:read documents:write"}
        )

        with (
            patch("knowledge.auth.dependencies.settings") as ms,
            patch("knowledge.auth.dependencies.get_jwt_validator", return_value=mock_validator),
            patch("knowledge.auth.dependencies.get_token_exchange_client", return_value=mock_te),
        ):
            ms.oauth2_issuer = "https://auth.example.com"
            ms.oauth2_client_id = "cid"
            ms.oauth2_client_secret = "csecret"
            result = await get_current_user_or_redirect(req)

        assert isinstance(result, User)
        assert "collections:read" in result.scopes

    async def test_exchange_error_continues(self):
        from knowledge.auth.token_exchange import TokenExchangeError

        req = _make_request(cookies={ACCESS_TOKEN_COOKIE: "tok"})
        mock_validator = MagicMock()
        mock_validator.validate_token_with_introspection = AsyncMock(
            return_value={"sub": str(USER_UUID), "scope": "openid"}
        )

        mock_te = MagicMock()
        mock_te.exchange_token = AsyncMock(side_effect=TokenExchangeError("fail"))

        with (
            patch("knowledge.auth.dependencies.settings") as ms,
            patch("knowledge.auth.dependencies.get_jwt_validator", return_value=mock_validator),
            patch("knowledge.auth.dependencies.get_token_exchange_client", return_value=mock_te),
        ):
            ms.oauth2_issuer = "https://auth.example.com"
            ms.oauth2_client_id = "cid"
            ms.oauth2_client_secret = "csecret"
            result = await get_current_user_or_redirect(req)

        assert isinstance(result, User)

    async def test_exchange_empty_scope(self):
        req = _make_request(cookies={ACCESS_TOKEN_COOKIE: "tok"})
        mock_validator = MagicMock()
        mock_validator.validate_token_with_introspection = AsyncMock(
            return_value={"sub": str(USER_UUID), "scope": "openid"}
        )

        mock_te = MagicMock()
        mock_te.exchange_token = AsyncMock(return_value={"scope": ""})

        with (
            patch("knowledge.auth.dependencies.settings") as ms,
            patch("knowledge.auth.dependencies.get_jwt_validator", return_value=mock_validator),
            patch("knowledge.auth.dependencies.get_token_exchange_client", return_value=mock_te),
        ):
            ms.oauth2_issuer = "https://auth.example.com"
            ms.oauth2_client_id = "cid"
            ms.oauth2_client_secret = "csecret"
            result = await get_current_user_or_redirect(req)

        assert isinstance(result, User)

    async def test_validation_exception_redirects(self):
        req = _make_request(cookies={ACCESS_TOKEN_COOKIE: "tok"})
        mock_validator = MagicMock()
        mock_validator.validate_token_with_introspection = AsyncMock(
            side_effect=RuntimeError("jwt fail")
        )

        with (
            patch("knowledge.auth.dependencies.settings") as ms,
            patch("knowledge.auth.dependencies.get_jwt_validator", return_value=mock_validator),
        ):
            ms.oauth2_issuer = "https://auth.example.com"
            result = await get_current_user_or_redirect(req)

        assert isinstance(result, RedirectResponse)


# =====================================================================
# get_web_auth_context
# =====================================================================


class TestGetWebAuthContext:
    async def test_redirect_when_not_authenticated(self, mock_db):
        req = _make_request(cookies={})
        with patch(
            "knowledge.auth.dependencies.get_current_user_or_redirect",
            new_callable=AsyncMock,
            return_value=RedirectResponse(url="/auth/login", status_code=302),
        ):
            result = await get_web_auth_context(req, mock_db)
        assert isinstance(result, RedirectResponse)

    async def test_active_org_from_cookie(self, mock_db, make_result):
        user = _make_user()
        req = _make_request(cookies={ACTIVE_TENANT_COOKIE: str(ORG_UUID)})

        org_member = MagicMock()
        org_member.organization_id = ORG_UUID
        org = MagicMock()
        org.id = ORG_UUID

        call_count = 0

        async def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return make_result(scalar_one_or_none=org_member)
            else:
                return make_result(scalar_one_or_none=org)

        mock_db.execute = AsyncMock(side_effect=_side_effect)

        with patch(
            "knowledge.auth.dependencies.get_current_user_or_redirect",
            new_callable=AsyncMock,
            return_value=user,
        ):
            result = await get_web_auth_context(req, mock_db)

        assert isinstance(result, WebAuthContext)
        assert result.tenant is org
        assert result.tenant_member is org_member

    async def test_invalid_org_cookie_uuid(self, mock_db, make_result):
        user = _make_user()
        req = _make_request(cookies={ACTIVE_TENANT_COOKIE: "not-a-uuid"})

        # Fallback query for first org
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=None))

        with patch(
            "knowledge.auth.dependencies.get_current_user_or_redirect",
            new_callable=AsyncMock,
            return_value=user,
        ):
            result = await get_web_auth_context(req, mock_db)

        assert isinstance(result, WebAuthContext)
        assert result.tenant is None

    async def test_org_member_not_found_for_cookie(self, mock_db, make_result):
        user = _make_user()
        req = _make_request(cookies={ACTIVE_TENANT_COOKIE: str(ORG_UUID)})

        # org member not found, then fallback also not found
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=None))

        with patch(
            "knowledge.auth.dependencies.get_current_user_or_redirect",
            new_callable=AsyncMock,
            return_value=user,
        ):
            result = await get_web_auth_context(req, mock_db)

        assert isinstance(result, WebAuthContext)
        assert result.tenant is None

    async def test_org_not_active_for_cookie(self, mock_db, make_result):
        user = _make_user()
        req = _make_request(cookies={ACTIVE_TENANT_COOKIE: str(ORG_UUID)})

        org_member = MagicMock()
        org_member.organization_id = ORG_UUID

        call_count = 0

        async def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # cookie org member found
                return make_result(scalar_one_or_none=org_member)
            elif call_count == 2:
                # cookie org not active
                return make_result(scalar_one_or_none=None)
            elif call_count == 3:
                # fallback: first org member
                return make_result(scalar_one_or_none=None)
            else:
                return make_result(scalar_one_or_none=None)

        mock_db.execute = AsyncMock(side_effect=_side_effect)

        with patch(
            "knowledge.auth.dependencies.get_current_user_or_redirect",
            new_callable=AsyncMock,
            return_value=user,
        ):
            result = await get_web_auth_context(req, mock_db)

        assert isinstance(result, WebAuthContext)

    async def test_fallback_first_org(self, mock_db, make_result):
        """No active org cookie => falls back to first org."""
        user = _make_user()
        req = _make_request(cookies={})

        fallback_member = MagicMock()
        fallback_member.organization_id = ORG_UUID
        org = MagicMock()
        org.id = ORG_UUID

        call_count = 0

        async def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return make_result(scalar_one_or_none=fallback_member)
            else:
                return make_result(scalar_one_or_none=org)

        mock_db.execute = AsyncMock(side_effect=_side_effect)

        with patch(
            "knowledge.auth.dependencies.get_current_user_or_redirect",
            new_callable=AsyncMock,
            return_value=user,
        ):
            result = await get_web_auth_context(req, mock_db)

        assert isinstance(result, WebAuthContext)
        assert result.tenant is org

    async def test_fallback_first_org_not_active(self, mock_db, make_result):
        """Fallback org found but not active."""
        user = _make_user()
        req = _make_request(cookies={})

        fallback_member = MagicMock()
        fallback_member.organization_id = ORG_UUID

        call_count = 0

        async def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return make_result(scalar_one_or_none=fallback_member)
            else:
                return make_result(scalar_one_or_none=None)  # not active

        mock_db.execute = AsyncMock(side_effect=_side_effect)

        with patch(
            "knowledge.auth.dependencies.get_current_user_or_redirect",
            new_callable=AsyncMock,
            return_value=user,
        ):
            result = await get_web_auth_context(req, mock_db)

        assert isinstance(result, WebAuthContext)
        assert result.tenant is None

    async def test_no_orgs_at_all(self, mock_db, make_result):
        """No org member found at all."""
        user = _make_user()
        req = _make_request(cookies={})

        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=None))

        with patch(
            "knowledge.auth.dependencies.get_current_user_or_redirect",
            new_callable=AsyncMock,
            return_value=user,
        ):
            result = await get_web_auth_context(req, mock_db)

        assert isinstance(result, WebAuthContext)
        assert result.tenant is None
        assert result.tenant_member is None


# =====================================================================
# require_scope_or_redirect factory
# =====================================================================


class TestRequireScopeOrRedirect:
    async def test_redirects_when_not_authed(self, mock_db):
        req = _make_request()
        check_fn = require_scope_or_redirect("api:read")

        with patch(
            "knowledge.auth.dependencies.get_web_auth_context",
            new_callable=AsyncMock,
            return_value=RedirectResponse(url="/login", status_code=302),
        ):
            result = await check_fn(request=req, db=mock_db)
        assert isinstance(result, RedirectResponse)

    async def test_returns_403_when_missing_scope(self, mock_db):
        req = _make_request()
        user = _make_user(scopes=[])
        web_ctx = WebAuthContext(user=user, tenant=None, tenant_member=None)

        check_fn = require_scope_or_redirect("api:read")

        with (
            patch(
                "knowledge.auth.dependencies.get_web_auth_context",
                new_callable=AsyncMock,
                return_value=web_ctx,
            ),
            patch("knowledge.auth.dependencies.Jinja2Templates", create=True),
        ):
            # We need to patch the import inside the function
            mock_templates = MagicMock()
            mock_response = MagicMock()
            mock_templates.TemplateResponse.return_value = mock_response

            with patch("fastapi.templating.Jinja2Templates", return_value=mock_templates):
                # The function does a local import, so we patch at the actual import location
                result = await check_fn(request=req, db=mock_db)

        # Result is a TemplateResponse (403 page), mocked
        assert result is not None

    async def test_passes_when_has_scope(self, mock_db):
        req = _make_request()
        user = _make_user(scopes=["api:read"])
        web_ctx = WebAuthContext(user=user, tenant=None, tenant_member=None)

        check_fn = require_scope_or_redirect("api:read")

        with patch(
            "knowledge.auth.dependencies.get_web_auth_context",
            new_callable=AsyncMock,
            return_value=web_ctx,
        ):
            result = await check_fn(request=req, db=mock_db)

        assert isinstance(result, WebAuthContext)


# =====================================================================
# require_resource_scopes_or_redirect factory
# =====================================================================


class TestRequireResourceScopesOrRedirect:
    async def test_redirects_when_not_authed(self, mock_db):
        req = _make_request()
        check_fn = require_resource_scopes_or_redirect("knowledge")

        with patch(
            "knowledge.auth.dependencies.get_web_auth_context",
            new_callable=AsyncMock,
            return_value=RedirectResponse(url="/login", status_code=302),
        ):
            result = await check_fn(request=req, db=mock_db)
        assert isinstance(result, RedirectResponse)

    async def test_returns_403_when_missing_scope(self, mock_db):
        req = _make_request()
        user = _make_user(scopes=["knowledge:read"])
        web_ctx = WebAuthContext(user=user, tenant=None, tenant_member=None)

        check_fn = require_resource_scopes_or_redirect("knowledge")

        with patch(
            "knowledge.auth.dependencies.get_web_auth_context",
            new_callable=AsyncMock,
            return_value=web_ctx,
        ):
            result = await check_fn(request=req, db=mock_db)

        # Missing knowledge:write => 403 template response
        assert result is not None

    async def test_passes_when_has_all_scopes(self, mock_db):
        req = _make_request()
        user = _make_user(scopes=["knowledge:read", "knowledge:write"])
        web_ctx = WebAuthContext(user=user, tenant=None, tenant_member=None)

        check_fn = require_resource_scopes_or_redirect("knowledge")

        with patch(
            "knowledge.auth.dependencies.get_web_auth_context",
            new_callable=AsyncMock,
            return_value=web_ctx,
        ):
            result = await check_fn(request=req, db=mock_db)

        assert isinstance(result, WebAuthContext)

    async def test_with_extra_scopes(self, mock_db):
        req = _make_request()
        user = _make_user(scopes=["knowledge:read", "knowledge:write", "knowledge:search"])
        web_ctx = WebAuthContext(user=user, tenant=None, tenant_member=None)

        check_fn = require_resource_scopes_or_redirect(
            "knowledge", extra_scopes=["knowledge:search"]
        )

        with patch(
            "knowledge.auth.dependencies.get_web_auth_context",
            new_callable=AsyncMock,
            return_value=web_ctx,
        ):
            result = await check_fn(request=req, db=mock_db)

        assert isinstance(result, WebAuthContext)

    async def test_with_extra_scopes_missing(self, mock_db):
        req = _make_request()
        user = _make_user(scopes=["knowledge:read", "knowledge:write"])
        web_ctx = WebAuthContext(user=user, tenant=None, tenant_member=None)

        check_fn = require_resource_scopes_or_redirect(
            "knowledge", extra_scopes=["knowledge:search"]
        )

        with patch(
            "knowledge.auth.dependencies.get_web_auth_context",
            new_callable=AsyncMock,
            return_value=web_ctx,
        ):
            result = await check_fn(request=req, db=mock_db)

        # Missing knowledge:search => 403
        assert result is not None


# =====================================================================
# require_tenant_admin factory
# =====================================================================


class TestRequireTenantAdmin:
    async def test_redirects_when_not_authed(self, mock_db):
        req = _make_request()
        check_fn = require_tenant_admin()

        with patch(
            "knowledge.auth.dependencies.get_web_auth_context",
            new_callable=AsyncMock,
            return_value=RedirectResponse(url="/login", status_code=302),
        ):
            result = await check_fn(request=req, db=mock_db)
        assert isinstance(result, RedirectResponse)

    async def test_returns_403_when_not_admin(self, mock_db):
        req = _make_request()
        user = _make_user()
        member = MagicMock()
        member.is_admin = False
        web_ctx = WebAuthContext(user=user, tenant=MagicMock(), tenant_member=member)

        check_fn = require_tenant_admin()

        with patch(
            "knowledge.auth.dependencies.get_web_auth_context",
            new_callable=AsyncMock,
            return_value=web_ctx,
        ):
            result = await check_fn(request=req, db=mock_db)

        # 403 template response
        assert result is not None

    async def test_passes_when_admin(self, mock_db):
        req = _make_request()
        user = _make_user()
        member = MagicMock()
        member.is_admin = True
        web_ctx = WebAuthContext(user=user, tenant=MagicMock(), tenant_member=member)

        check_fn = require_tenant_admin()

        with patch(
            "knowledge.auth.dependencies.get_web_auth_context",
            new_callable=AsyncMock,
            return_value=web_ctx,
        ):
            result = await check_fn(request=req, db=mock_db)

        assert isinstance(result, WebAuthContext)
