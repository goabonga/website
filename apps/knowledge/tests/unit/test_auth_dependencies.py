# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for knowledge/auth/dependencies.py — 100% coverage with only mocks."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi import HTTPException

from knowledge.auth.dependencies import (
    AuthContext,
    _get_oauth2_scheme,
    _get_token_from_oauth2_or_bearer,
    get_auth_context,
    get_current_user,
    get_oauth2_scheme,
    get_optional_auth_context,
    get_optional_user,
    require_scopes,
)
from knowledge.auth.models import User

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
    req.url = url
    req.state = MagicMock()
    return req


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
