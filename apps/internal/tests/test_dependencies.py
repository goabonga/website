# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth dependencies module."""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from internal.auth.dependencies import (
    ACCESS_TOKEN_COOKIE,
    REFRESH_TOKEN_COOKIE,
    USER_INFO_COOKIE,
    _create_login_redirect,
    _get_user_info_from_cookie,
    _render_403_page,
    clear_pending_token_refresh,
    get_current_access_token,
    get_current_user,
    get_current_user_or_redirect,
    get_exchanged_token,
    get_pending_token_refresh,
    get_token_from_request,
    require_any_scope,
    require_exchanged_token,
    require_resource_scopes_or_redirect,
    require_scope,
    require_scope_or_redirect,
    require_scopes,
)
from internal.auth.models import User

USER_UUID = uuid.UUID("12345678-1234-5678-1234-567812345678")


def _make_request(cookies=None, headers=None, url="http://test/page"):
    """Create a mock Request."""
    req = MagicMock()
    req.cookies = cookies or {}
    req.headers = headers or {}
    req.url = url
    return req


def _make_user(**kwargs):
    defaults = {"id": USER_UUID, "scopes": ["knowledge:read"]}
    defaults.update(kwargs)
    return User(**defaults)


# =========================================================================
# Module-level helpers
# =========================================================================


class TestGetOauth2Scheme:
    def test_scheme_created_when_issuer_set(self):
        with patch("internal.auth.dependencies.settings") as s:
            s.oauth2_issuer = "https://auth.example.com"
            from internal.auth.dependencies import _get_oauth2_scheme

            scheme = _get_oauth2_scheme()
            assert scheme is not None

    def test_scheme_none_when_no_issuer(self):
        with patch("internal.auth.dependencies.settings") as s:
            s.oauth2_issuer = ""
            from internal.auth.dependencies import _get_oauth2_scheme

            result = _get_oauth2_scheme()
            assert result is None


class TestGetUserInfoFromCookie:
    def test_valid_json(self):
        req = _make_request(cookies={USER_INFO_COOKIE: '{"name":"Alice","email":"a@b.com"}'})
        result = _get_user_info_from_cookie(req)
        assert result == {"name": "Alice", "email": "a@b.com"}

    def test_invalid_json(self):
        req = _make_request(cookies={USER_INFO_COOKIE: "not-json"})
        assert _get_user_info_from_cookie(req) is None

    def test_no_cookie(self):
        req = _make_request(cookies={})
        assert _get_user_info_from_cookie(req) is None


class TestTryRefreshToken:
    @pytest.mark.asyncio
    async def test_no_issuer(self):
        from internal.auth.dependencies import _try_refresh_token

        with patch("internal.auth.dependencies.settings") as s:
            s.oauth2_issuer = ""
            result = await _try_refresh_token("refresh-tok")
            assert result is None

    @pytest.mark.asyncio
    async def test_success(self):
        from internal.auth.dependencies import _try_refresh_token

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": "new-at", "refresh_token": "new-rt"}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp

        with (
            patch("internal.auth.dependencies.settings") as s,
            patch("internal.auth.dependencies.httpx.AsyncClient") as MockClient,
        ):
            s.oauth2_issuer = "https://auth.example.com"
            s.oauth2_frontend_client_id = "frontend"
            s.app_base_url = "https://app.example.com"
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _try_refresh_token("old-refresh")
            assert result["access_token"] == "new-at"

    @pytest.mark.asyncio
    async def test_non_200(self):
        from internal.auth.dependencies import _try_refresh_token

        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp

        with (
            patch("internal.auth.dependencies.settings") as s,
            patch("internal.auth.dependencies.httpx.AsyncClient") as MockClient,
        ):
            s.oauth2_issuer = "https://auth.example.com"
            s.oauth2_frontend_client_id = "frontend"
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _try_refresh_token("old-refresh")
            assert result is None

    @pytest.mark.asyncio
    async def test_request_error(self):
        from internal.auth.dependencies import _try_refresh_token

        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.RequestError("conn error")

        with (
            patch("internal.auth.dependencies.settings") as s,
            patch("internal.auth.dependencies.httpx.AsyncClient") as MockClient,
        ):
            s.oauth2_issuer = "https://auth.example.com"
            s.oauth2_frontend_client_id = "frontend"
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _try_refresh_token("old-refresh")
            assert result is None


class TestGetTokenFromRequest:
    @pytest.mark.asyncio
    async def test_bearer_token(self):
        req = _make_request()
        result = await get_token_from_request(req, "bearer-tok")
        assert result == "bearer-tok"

    @pytest.mark.asyncio
    async def test_cookie_fallback(self):
        req = _make_request(cookies={ACCESS_TOKEN_COOKIE: "cookie-tok"})
        result = await get_token_from_request(req, None)
        assert result == "cookie-tok"

    @pytest.mark.asyncio
    async def test_no_token(self):
        req = _make_request()
        result = await get_token_from_request(req, None)
        assert result is None


class TestGetCurrentAccessToken:
    def test_pending_refresh(self):
        import internal.auth.dependencies as deps

        original = deps._pending_token_refresh
        try:
            deps._pending_token_refresh = {"access_token": "refreshed-tok"}
            req = _make_request()
            result = get_current_access_token(req, "old-tok")
            assert result == "refreshed-tok"
        finally:
            deps._pending_token_refresh = original

    def test_bearer_token(self):
        import internal.auth.dependencies as deps

        original = deps._pending_token_refresh
        try:
            deps._pending_token_refresh = None
            req = _make_request()
            result = get_current_access_token(req, "bearer-tok")
            assert result == "bearer-tok"
        finally:
            deps._pending_token_refresh = original

    def test_cookie_fallback(self):
        import internal.auth.dependencies as deps

        original = deps._pending_token_refresh
        try:
            deps._pending_token_refresh = None
            req = _make_request(cookies={ACCESS_TOKEN_COOKIE: "cookie-tok"})
            result = get_current_access_token(req, None)
            assert result == "cookie-tok"
        finally:
            deps._pending_token_refresh = original


class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_no_token_raises_401(self):
        req = _make_request()
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(req, None)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_no_oauth2_issuer_raises_503(self):
        req = _make_request(cookies={ACCESS_TOKEN_COOKIE: "tok"})
        with (
            patch("internal.auth.dependencies.settings") as s,
            patch(
                "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
            ) as mock_gtr,
        ):
            mock_gtr.return_value = "tok"
            s.oauth2_issuer = ""
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(req, None)
            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_valid_token(self):
        claims = {"sub": str(USER_UUID), "scope": "knowledge:read", "email": "a@b.com"}
        with (
            patch("internal.auth.dependencies.settings") as s,
            patch(
                "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
            ) as mock_gtr,
            patch("internal.auth.dependencies.jwt_validator") as mock_jwt,
        ):
            mock_gtr.return_value = "valid-tok"
            s.oauth2_issuer = "https://auth.example.com"
            mock_jwt.validate_token_with_introspection = AsyncMock(return_value=claims)
            user = await get_current_user(_make_request(), None)
            assert user.id == USER_UUID

    @pytest.mark.asyncio
    async def test_revoked_token(self):
        from internal.auth.jwt import TokenRevokedError

        with (
            patch("internal.auth.dependencies.settings") as s,
            patch(
                "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
            ) as mock_gtr,
            patch("internal.auth.dependencies.jwt_validator") as mock_jwt,
        ):
            mock_gtr.return_value = "revoked-tok"
            s.oauth2_issuer = "https://auth.example.com"
            mock_jwt.validate_token_with_introspection = AsyncMock(
                side_effect=TokenRevokedError("revoked")
            )
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(_make_request(), None)
            assert exc_info.value.status_code == 401
            assert "revoked" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_invalid_token(self):
        with (
            patch("internal.auth.dependencies.settings") as s,
            patch(
                "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
            ) as mock_gtr,
            patch("internal.auth.dependencies.jwt_validator") as mock_jwt,
        ):
            mock_gtr.return_value = "bad-tok"
            s.oauth2_issuer = "https://auth.example.com"
            mock_jwt.validate_token_with_introspection = AsyncMock(
                side_effect=Exception("bad token")
            )
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(_make_request(), None)
            assert exc_info.value.status_code == 401


class TestGetCurrentUserOrRedirect:
    @pytest.mark.asyncio
    async def test_no_token_no_refresh_redirects(self):
        import internal.auth.dependencies as deps

        original = deps._pending_token_refresh
        try:
            deps._pending_token_refresh = None
            req = _make_request(cookies={})
            with (
                patch(
                    "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
                ) as mock_gtr,
                patch("internal.auth.dependencies.settings") as s,
            ):
                mock_gtr.return_value = None
                s.oauth2_issuer = "https://auth.example.com"
                s.oauth2_frontend_client_id = "frontend"
                s.app_base_url = "https://app.example.com"
                s.cookie_secure = False
                result = await get_current_user_or_redirect(req, None)
                assert isinstance(result, RedirectResponse)
        finally:
            deps._pending_token_refresh = original

    @pytest.mark.asyncio
    async def test_no_token_with_refresh_success(self):
        import internal.auth.dependencies as deps

        original = deps._pending_token_refresh
        try:
            deps._pending_token_refresh = None
            claims = {"sub": str(USER_UUID), "scope": "knowledge:read"}
            req = _make_request(cookies={REFRESH_TOKEN_COOKIE: "refresh-tok"})
            with (
                patch(
                    "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
                ) as mock_gtr,
                patch(
                    "internal.auth.dependencies._try_refresh_token", new_callable=AsyncMock
                ) as mock_refresh,
                patch("internal.auth.dependencies.jwt_validator") as mock_jwt,
                patch("internal.auth.dependencies.settings") as s,
            ):
                mock_gtr.return_value = None
                mock_refresh.return_value = {"access_token": "new-at", "refresh_token": "new-rt"}
                s.oauth2_issuer = "https://auth.example.com"
                mock_jwt.validate_token_with_introspection = AsyncMock(return_value=claims)
                result = await get_current_user_or_redirect(req, None)
                assert isinstance(result, User)
        finally:
            deps._pending_token_refresh = original

    @pytest.mark.asyncio
    async def test_no_token_refresh_fails(self):
        import internal.auth.dependencies as deps

        original = deps._pending_token_refresh
        try:
            deps._pending_token_refresh = None
            req = _make_request(cookies={REFRESH_TOKEN_COOKIE: "refresh-tok"})
            with (
                patch(
                    "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
                ) as mock_gtr,
                patch(
                    "internal.auth.dependencies._try_refresh_token", new_callable=AsyncMock
                ) as mock_refresh,
                patch("internal.auth.dependencies.settings") as s,
            ):
                mock_gtr.return_value = None
                mock_refresh.return_value = None
                s.oauth2_issuer = "https://auth.example.com"
                s.oauth2_frontend_client_id = "frontend"
                s.app_base_url = "https://app.example.com"
                s.cookie_secure = False
                result = await get_current_user_or_redirect(req, None)
                assert isinstance(result, RedirectResponse)
        finally:
            deps._pending_token_refresh = original

    @pytest.mark.asyncio
    async def test_no_issuer_raises_500(self):
        import internal.auth.dependencies as deps

        original = deps._pending_token_refresh
        try:
            deps._pending_token_refresh = None
            req = _make_request()
            with (
                patch(
                    "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
                ) as mock_gtr,
                patch("internal.auth.dependencies.settings") as s,
            ):
                mock_gtr.return_value = "valid-tok"
                s.oauth2_issuer = ""
                with pytest.raises(HTTPException) as exc_info:
                    await get_current_user_or_redirect(req, None)
                assert exc_info.value.status_code == 500
        finally:
            deps._pending_token_refresh = original

    @pytest.mark.asyncio
    async def test_valid_token_with_user_info(self):
        import internal.auth.dependencies as deps

        original = deps._pending_token_refresh
        try:
            deps._pending_token_refresh = None
            claims = {"sub": str(USER_UUID), "scope": "knowledge:read"}
            user_info = {"name": "Alice", "email": "alice@example.com"}
            req = _make_request(cookies={USER_INFO_COOKIE: json.dumps(user_info)})
            with (
                patch(
                    "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
                ) as mock_gtr,
                patch("internal.auth.dependencies.jwt_validator") as mock_jwt,
                patch("internal.auth.dependencies.settings") as s,
            ):
                mock_gtr.return_value = "valid-tok"
                s.oauth2_issuer = "https://auth.example.com"
                mock_jwt.validate_token_with_introspection = AsyncMock(return_value=claims)
                result = await get_current_user_or_redirect(req, None)
                assert isinstance(result, User)
                assert result.name == "Alice"
                assert result.email == "alice@example.com"
        finally:
            deps._pending_token_refresh = original

    @pytest.mark.asyncio
    async def test_expired_token_refresh_success(self):
        import internal.auth.dependencies as deps

        original = deps._pending_token_refresh
        try:
            deps._pending_token_refresh = None
            claims = {"sub": str(USER_UUID), "scope": "knowledge:read"}
            req = _make_request(cookies={REFRESH_TOKEN_COOKIE: "refresh-tok"})
            with (
                patch(
                    "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
                ) as mock_gtr,
                patch(
                    "internal.auth.dependencies._try_refresh_token", new_callable=AsyncMock
                ) as mock_refresh,
                patch("internal.auth.dependencies.jwt_validator") as mock_jwt,
                patch("internal.auth.dependencies.settings") as s,
            ):
                mock_gtr.return_value = "expired-tok"
                s.oauth2_issuer = "https://auth.example.com"
                mock_refresh.return_value = {"access_token": "new-at"}
                # First validate fails, second succeeds with new token
                mock_jwt.validate_token_with_introspection = AsyncMock(
                    side_effect=[Exception("expired"), claims]
                )
                result = await get_current_user_or_redirect(req, None)
                assert isinstance(result, User)
        finally:
            deps._pending_token_refresh = original

    @pytest.mark.asyncio
    async def test_expired_token_refresh_success_with_user_info(self):
        """Covers lines 250-253: user_info enrichment in the refresh path."""
        import internal.auth.dependencies as deps

        original = deps._pending_token_refresh
        try:
            deps._pending_token_refresh = None
            # Claims without name/email
            claims = {"sub": str(USER_UUID), "scope": "knowledge:read"}
            user_info = json.dumps({"name": "Cookie Name", "email": "cookie@example.com"})
            req = _make_request(
                cookies={
                    REFRESH_TOKEN_COOKIE: "refresh-tok",
                    USER_INFO_COOKIE: user_info,
                }
            )
            with (
                patch(
                    "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
                ) as mock_gtr,
                patch(
                    "internal.auth.dependencies._try_refresh_token", new_callable=AsyncMock
                ) as mock_refresh,
                patch("internal.auth.dependencies.jwt_validator") as mock_jwt,
                patch("internal.auth.dependencies.settings") as s,
            ):
                mock_gtr.return_value = "expired-tok"
                s.oauth2_issuer = "https://auth.example.com"
                mock_jwt.validate_token_with_introspection = AsyncMock(
                    side_effect=[Exception("expired"), claims]
                )
                mock_refresh.return_value = {"access_token": "new-at"}
                result = await get_current_user_or_redirect(req, None)
                assert isinstance(result, User)
                assert result.name == "Cookie Name"
                assert result.email == "cookie@example.com"
        finally:
            deps._pending_token_refresh = original

    @pytest.mark.asyncio
    async def test_valid_token_user_already_has_name_and_email(self):
        """Covers branches 226->228, 228->231: user already has name+email from claims."""
        import internal.auth.dependencies as deps

        original = deps._pending_token_refresh
        try:
            deps._pending_token_refresh = None
            # Claims include name AND email so User already has them
            claims = {
                "sub": str(USER_UUID),
                "scope": "knowledge:read",
                "name": "Claims Name",
                "email": "claims@example.com",
            }
            # user_info also has name+email, but they should NOT overwrite
            user_info = {"name": "Cookie Name", "email": "cookie@example.com"}
            req = _make_request(cookies={USER_INFO_COOKIE: json.dumps(user_info)})
            with (
                patch(
                    "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
                ) as mock_gtr,
                patch("internal.auth.dependencies.jwt_validator") as mock_jwt,
                patch("internal.auth.dependencies.settings") as s,
            ):
                mock_gtr.return_value = "valid-tok"
                s.oauth2_issuer = "https://auth.example.com"
                mock_jwt.validate_token_with_introspection = AsyncMock(return_value=claims)
                result = await get_current_user_or_redirect(req, None)
                assert isinstance(result, User)
                # Name and email from claims, NOT overwritten by user_info cookie
                assert result.name == "Claims Name"
                assert result.email == "claims@example.com"
        finally:
            deps._pending_token_refresh = original

    @pytest.mark.asyncio
    async def test_expired_token_refresh_returns_no_access_token(self):
        """Covers branch 239->262: refresh returns tokens but no access_token."""
        import internal.auth.dependencies as deps

        original = deps._pending_token_refresh
        try:
            deps._pending_token_refresh = None
            req = _make_request(cookies={REFRESH_TOKEN_COOKIE: "refresh-tok"})
            with (
                patch(
                    "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
                ) as mock_gtr,
                patch(
                    "internal.auth.dependencies._try_refresh_token", new_callable=AsyncMock
                ) as mock_refresh,
                patch("internal.auth.dependencies.jwt_validator") as mock_jwt,
                patch("internal.auth.dependencies.settings") as s,
            ):
                mock_gtr.return_value = "expired-tok"
                s.oauth2_issuer = "https://auth.example.com"
                s.oauth2_frontend_client_id = "frontend"
                s.app_base_url = "https://app.example.com"
                s.cookie_secure = False
                mock_jwt.validate_token_with_introspection = AsyncMock(
                    side_effect=Exception("expired")
                )
                # Refresh returns tokens but WITHOUT access_token
                mock_refresh.return_value = {"refresh_token": "new-rt"}
                result = await get_current_user_or_redirect(req, None)
                assert isinstance(result, RedirectResponse)
        finally:
            deps._pending_token_refresh = original

    @pytest.mark.asyncio
    async def test_expired_token_refresh_user_already_has_name_email(self):
        """Covers branches 250->252, 252->256: user already has name+email in refresh path."""
        import internal.auth.dependencies as deps

        original = deps._pending_token_refresh
        try:
            deps._pending_token_refresh = None
            # Claims with name AND email already set
            claims = {
                "sub": str(USER_UUID),
                "scope": "knowledge:read",
                "name": "Claims Name",
                "email": "claims@example.com",
            }
            user_info = json.dumps({"name": "Cookie Name", "email": "cookie@example.com"})
            req = _make_request(
                cookies={
                    REFRESH_TOKEN_COOKIE: "refresh-tok",
                    USER_INFO_COOKIE: user_info,
                }
            )
            with (
                patch(
                    "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
                ) as mock_gtr,
                patch(
                    "internal.auth.dependencies._try_refresh_token", new_callable=AsyncMock
                ) as mock_refresh,
                patch("internal.auth.dependencies.jwt_validator") as mock_jwt,
                patch("internal.auth.dependencies.settings") as s,
            ):
                mock_gtr.return_value = "expired-tok"
                s.oauth2_issuer = "https://auth.example.com"
                mock_jwt.validate_token_with_introspection = AsyncMock(
                    side_effect=[Exception("expired"), claims]
                )
                mock_refresh.return_value = {"access_token": "new-at"}
                result = await get_current_user_or_redirect(req, None)
                assert isinstance(result, User)
                # Name and email from claims, NOT overwritten by cookie
                assert result.name == "Claims Name"
                assert result.email == "claims@example.com"
        finally:
            deps._pending_token_refresh = original

    @pytest.mark.asyncio
    async def test_expired_token_refresh_also_fails(self):
        import internal.auth.dependencies as deps

        original = deps._pending_token_refresh
        try:
            deps._pending_token_refresh = None
            req = _make_request(cookies={REFRESH_TOKEN_COOKIE: "refresh-tok"})
            with (
                patch(
                    "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
                ) as mock_gtr,
                patch(
                    "internal.auth.dependencies._try_refresh_token", new_callable=AsyncMock
                ) as mock_refresh,
                patch("internal.auth.dependencies.jwt_validator") as mock_jwt,
                patch("internal.auth.dependencies.settings") as s,
            ):
                mock_gtr.return_value = "expired-tok"
                s.oauth2_issuer = "https://auth.example.com"
                s.oauth2_frontend_client_id = "frontend"
                s.app_base_url = "https://app.example.com"
                s.cookie_secure = False
                mock_jwt.validate_token_with_introspection = AsyncMock(
                    side_effect=Exception("expired")
                )
                mock_refresh.return_value = {"access_token": "new-at"}
                result = await get_current_user_or_redirect(req, None)
                assert isinstance(result, RedirectResponse)
        finally:
            deps._pending_token_refresh = original

    @pytest.mark.asyncio
    async def test_expired_token_no_refresh_token(self):
        import internal.auth.dependencies as deps

        original = deps._pending_token_refresh
        try:
            deps._pending_token_refresh = None
            req = _make_request(cookies={})
            with (
                patch(
                    "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
                ) as mock_gtr,
                patch("internal.auth.dependencies.jwt_validator") as mock_jwt,
                patch("internal.auth.dependencies.settings") as s,
            ):
                mock_gtr.return_value = "expired-tok"
                s.oauth2_issuer = "https://auth.example.com"
                s.oauth2_frontend_client_id = "frontend"
                s.app_base_url = "https://app.example.com"
                s.cookie_secure = False
                mock_jwt.validate_token_with_introspection = AsyncMock(
                    side_effect=Exception("expired")
                )
                result = await get_current_user_or_redirect(req, None)
                assert isinstance(result, RedirectResponse)
        finally:
            deps._pending_token_refresh = original


class TestCreateLoginRedirect:
    def test_creates_redirect(self):
        req = _make_request(url="http://test/original-page")
        with patch("internal.auth.dependencies.settings") as s:
            s.oauth2_issuer = "https://auth.example.com"
            s.oauth2_frontend_client_id = "frontend"
            s.app_base_url = "https://app.example.com"
            s.cookie_secure = False
            result = _create_login_redirect(req)
            assert isinstance(result, RedirectResponse)
            assert result.status_code == 302


class TestRequireScope:
    @pytest.mark.asyncio
    async def test_has_scope(self):
        dep = require_scope("knowledge:read")
        user = _make_user(scopes=["knowledge:read"])
        result = await dep(user=user)
        assert result.id == USER_UUID

    @pytest.mark.asyncio
    async def test_missing_scope(self):
        dep = require_scope("admin:write")
        user = _make_user(scopes=["knowledge:read"])
        with pytest.raises(HTTPException) as exc_info:
            await dep(user=user)
        assert exc_info.value.status_code == 403


class TestRequireScopes:
    @pytest.mark.asyncio
    async def test_no_oauth2_issuer(self):
        dep = require_scopes("users:read")
        req = _make_request()
        with patch("internal.auth.dependencies.settings") as s:
            s.oauth2_issuer = ""
            with pytest.raises(HTTPException) as exc_info:
                await dep(request=req, token=None)
            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_no_token(self):
        dep = require_scopes("users:read")
        req = _make_request()
        with (
            patch("internal.auth.dependencies.settings") as s,
            patch(
                "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
            ) as mock_gtr,
        ):
            s.oauth2_issuer = "https://auth.example.com"
            mock_gtr.return_value = None
            with pytest.raises(HTTPException) as exc_info:
                await dep(request=req, token=None)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_token_exchange_success(self):
        dep = require_scopes("users:read")
        req = _make_request()
        claims = {"sub": str(USER_UUID), "scope": "users:read", "email": "a@b.com", "name": "A"}
        with (
            patch("internal.auth.dependencies.settings") as s,
            patch(
                "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
            ) as mock_gtr,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
            patch("internal.auth.dependencies.jwt_validator") as mock_jwt,
        ):
            s.oauth2_issuer = "https://auth.example.com"
            mock_gtr.return_value = "tok"
            mock_te.is_configured = True
            mock_te.validate_token_scopes = AsyncMock(
                return_value={"scope": "users:read users:write"}
            )
            mock_jwt.validate_token_with_introspection = AsyncMock(return_value=claims)
            user = await dep(request=req, token=None)
            assert isinstance(user, User)

    @pytest.mark.asyncio
    async def test_token_exchange_validation_fails(self):
        dep = require_scopes("users:read")
        req = _make_request()
        with (
            patch("internal.auth.dependencies.settings") as s,
            patch(
                "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
            ) as mock_gtr,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
            patch("internal.auth.dependencies.jwt_validator") as mock_jwt,
        ):
            s.oauth2_issuer = "https://auth.example.com"
            mock_gtr.return_value = "tok"
            mock_te.is_configured = True
            mock_te.validate_token_scopes = AsyncMock(return_value={"scope": "users:read"})
            # When introspection fails, code falls back to sub="" which is invalid UUID
            mock_jwt.validate_token_with_introspection = AsyncMock(side_effect=Exception("bad"))
            from pydantic import ValidationError

            with pytest.raises(ValidationError):
                await dep(request=req, token=None)

    @pytest.mark.asyncio
    async def test_token_exchange_invalid_grant(self):
        from internal.services.token_exchange import TokenExchangeError

        dep = require_scopes("users:read")
        req = _make_request()
        with (
            patch("internal.auth.dependencies.settings") as s,
            patch(
                "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
            ) as mock_gtr,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
        ):
            s.oauth2_issuer = "https://auth.example.com"
            mock_gtr.return_value = "tok"
            mock_te.is_configured = True
            err = TokenExchangeError("invalid grant")
            err.error_code = "invalid_grant"
            mock_te.validate_token_scopes = AsyncMock(side_effect=err)
            with pytest.raises(HTTPException) as exc_info:
                await dep(request=req, token=None)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_token_exchange_insufficient_scope(self):
        from internal.services.token_exchange import TokenExchangeError

        dep = require_scopes("users:read")
        req = _make_request()
        with (
            patch("internal.auth.dependencies.settings") as s,
            patch(
                "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
            ) as mock_gtr,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
        ):
            s.oauth2_issuer = "https://auth.example.com"
            mock_gtr.return_value = "tok"
            mock_te.is_configured = True
            err = TokenExchangeError("insufficient scope")
            err.error_code = "insufficient_scope"
            mock_te.validate_token_scopes = AsyncMock(side_effect=err)
            with pytest.raises(HTTPException) as exc_info:
                await dep(request=req, token=None)
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_token_exchange_other_error(self):
        from internal.services.token_exchange import TokenExchangeError

        dep = require_scopes("users:read")
        req = _make_request()
        with (
            patch("internal.auth.dependencies.settings") as s,
            patch(
                "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
            ) as mock_gtr,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
        ):
            s.oauth2_issuer = "https://auth.example.com"
            mock_gtr.return_value = "tok"
            mock_te.is_configured = True
            err = TokenExchangeError("other error")
            err.error_code = "server_error"
            mock_te.validate_token_scopes = AsyncMock(side_effect=err)
            with pytest.raises(HTTPException) as exc_info:
                await dep(request=req, token=None)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_fallback_no_exchange_valid(self):
        dep = require_scopes("knowledge:read")
        req = _make_request()
        claims = {"sub": str(USER_UUID), "scope": "knowledge:read"}
        with (
            patch("internal.auth.dependencies.settings") as s,
            patch(
                "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
            ) as mock_gtr,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
            patch("internal.auth.dependencies.jwt_validator") as mock_jwt,
        ):
            s.oauth2_issuer = "https://auth.example.com"
            mock_gtr.return_value = "tok"
            mock_te.is_configured = False
            mock_jwt.validate_token_with_introspection = AsyncMock(return_value=claims)
            user = await dep(request=req, token=None)
            assert isinstance(user, User)

    @pytest.mark.asyncio
    async def test_fallback_revoked_token(self):
        from internal.auth.jwt import TokenRevokedError

        dep = require_scopes("knowledge:read")
        req = _make_request()
        with (
            patch("internal.auth.dependencies.settings") as s,
            patch(
                "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
            ) as mock_gtr,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
            patch("internal.auth.dependencies.jwt_validator") as mock_jwt,
        ):
            s.oauth2_issuer = "https://auth.example.com"
            mock_gtr.return_value = "tok"
            mock_te.is_configured = False
            mock_jwt.validate_token_with_introspection = AsyncMock(
                side_effect=TokenRevokedError("revoked")
            )
            with pytest.raises(HTTPException) as exc_info:
                await dep(request=req, token=None)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_fallback_invalid_token(self):
        dep = require_scopes("knowledge:read")
        req = _make_request()
        with (
            patch("internal.auth.dependencies.settings") as s,
            patch(
                "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
            ) as mock_gtr,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
            patch("internal.auth.dependencies.jwt_validator") as mock_jwt,
        ):
            s.oauth2_issuer = "https://auth.example.com"
            mock_gtr.return_value = "tok"
            mock_te.is_configured = False
            mock_jwt.validate_token_with_introspection = AsyncMock(side_effect=Exception("bad"))
            with pytest.raises(HTTPException) as exc_info:
                await dep(request=req, token=None)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_fallback_missing_scopes(self):
        dep = require_scopes("admin:write")
        req = _make_request()
        claims = {"sub": str(USER_UUID), "scope": "knowledge:read"}
        with (
            patch("internal.auth.dependencies.settings") as s,
            patch(
                "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
            ) as mock_gtr,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
            patch("internal.auth.dependencies.jwt_validator") as mock_jwt,
        ):
            s.oauth2_issuer = "https://auth.example.com"
            mock_gtr.return_value = "tok"
            mock_te.is_configured = False
            mock_jwt.validate_token_with_introspection = AsyncMock(return_value=claims)
            with pytest.raises(HTTPException) as exc_info:
                await dep(request=req, token=None)
            assert exc_info.value.status_code == 403


class TestRender403Page:
    def test_renders(self):
        req = _make_request()
        with patch("internal.auth.dependencies.templates") as mock_templates:
            mock_templates.TemplateResponse.return_value = HTMLResponse(
                content="forbidden", status_code=403
            )
            _render_403_page(req, required_scope="admin:read", detail="no access")
            mock_templates.TemplateResponse.assert_called_once()


class TestRequireScopeOrRedirect:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        dep = require_scope_or_redirect("knowledge:read")
        req = _make_request()
        redirect = RedirectResponse(url="/login")
        with (
            patch(
                "internal.auth.dependencies.get_current_user_or_redirect", new_callable=AsyncMock
            ) as mock_gcuor,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
        ):
            mock_gcuor.return_value = redirect
            mock_te.is_configured = False
            result = await dep(request=req, token=None)
            assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_exchange_success(self):
        dep = require_scope_or_redirect("knowledge:read")
        req = _make_request()
        user = _make_user(scopes=["knowledge:read"])
        with (
            patch(
                "internal.auth.dependencies.get_current_user_or_redirect", new_callable=AsyncMock
            ) as mock_gcuor,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
            patch("internal.auth.dependencies.get_current_access_token") as mock_gcat,
        ):
            mock_gcuor.return_value = user
            mock_te.is_configured = True
            mock_gcat.return_value = "tok"
            mock_te.validate_token_scopes = AsyncMock(
                return_value={"scope": "knowledge:read knowledge:write"}
            )
            result = await dep(request=req, token=None)
            assert isinstance(result, User)

    @pytest.mark.asyncio
    async def test_exchange_no_access_token_fallback(self):
        """Covers branch 498->536: token exchange configured but no access token available."""
        dep = require_scope_or_redirect("knowledge:read")
        req = _make_request()
        user = _make_user(scopes=["knowledge:read"])
        with (
            patch(
                "internal.auth.dependencies.get_current_user_or_redirect", new_callable=AsyncMock
            ) as mock_gcuor,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
            patch("internal.auth.dependencies.get_current_access_token") as mock_gcat,
        ):
            mock_gcuor.return_value = user
            mock_te.is_configured = True
            mock_gcat.return_value = None  # No access token
            result = await dep(request=req, token=None)
            # Falls back to JWT scope check, user has the scope
            assert isinstance(result, User)

    @pytest.mark.asyncio
    async def test_exchange_insufficient_scope(self):
        from internal.services.token_exchange import TokenExchangeError

        dep = require_scope_or_redirect("admin:read")
        req = _make_request()
        user = _make_user(scopes=[])
        with (
            patch(
                "internal.auth.dependencies.get_current_user_or_redirect", new_callable=AsyncMock
            ) as mock_gcuor,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
            patch("internal.auth.dependencies.get_current_access_token") as mock_gcat,
            patch("internal.auth.dependencies.templates") as mock_templates,
        ):
            mock_gcuor.return_value = user
            mock_te.is_configured = True
            mock_gcat.return_value = "tok"
            err = TokenExchangeError("insufficient")
            err.error_code = "insufficient_scope"
            mock_te.validate_token_scopes = AsyncMock(side_effect=err)
            mock_templates.TemplateResponse.return_value = HTMLResponse(
                content="403", status_code=403
            )
            result = await dep(request=req, token=None)
            assert isinstance(result, HTMLResponse)

    @pytest.mark.asyncio
    async def test_exchange_other_error(self):
        from internal.services.token_exchange import TokenExchangeError

        dep = require_scope_or_redirect("knowledge:read")
        req = _make_request()
        user = _make_user(scopes=[])
        with (
            patch(
                "internal.auth.dependencies.get_current_user_or_redirect", new_callable=AsyncMock
            ) as mock_gcuor,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
            patch("internal.auth.dependencies.get_current_access_token") as mock_gcat,
            patch("internal.auth.dependencies.templates") as mock_templates,
        ):
            mock_gcuor.return_value = user
            mock_te.is_configured = True
            mock_gcat.return_value = "tok"
            err = TokenExchangeError("server error")
            err.error_code = "server_error"
            mock_te.validate_token_scopes = AsyncMock(side_effect=err)
            mock_templates.TemplateResponse.return_value = HTMLResponse(
                content="403", status_code=403
            )
            result = await dep(request=req, token=None)
            assert isinstance(result, HTMLResponse)

    @pytest.mark.asyncio
    async def test_fallback_has_scope(self):
        dep = require_scope_or_redirect("knowledge:read")
        req = _make_request()
        user = _make_user(scopes=["knowledge:read"])
        with (
            patch(
                "internal.auth.dependencies.get_current_user_or_redirect", new_callable=AsyncMock
            ) as mock_gcuor,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
        ):
            mock_gcuor.return_value = user
            mock_te.is_configured = False
            result = await dep(request=req, token=None)
            assert isinstance(result, User)

    @pytest.mark.asyncio
    async def test_fallback_missing_scope(self):
        dep = require_scope_or_redirect("admin:write")
        req = _make_request()
        user = _make_user(scopes=["knowledge:read"])
        with (
            patch(
                "internal.auth.dependencies.get_current_user_or_redirect", new_callable=AsyncMock
            ) as mock_gcuor,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
            patch("internal.auth.dependencies.templates") as mock_templates,
        ):
            mock_gcuor.return_value = user
            mock_te.is_configured = False
            mock_templates.TemplateResponse.return_value = HTMLResponse(
                content="403", status_code=403
            )
            result = await dep(request=req, token=None)
            assert isinstance(result, HTMLResponse)


class TestRequireResourceScopesOrRedirect:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        dep = require_resource_scopes_or_redirect("knowledge")
        req = _make_request()
        redirect = RedirectResponse(url="/login")
        with patch(
            "internal.auth.dependencies.get_current_user_or_redirect", new_callable=AsyncMock
        ) as mock_gcuor:
            mock_gcuor.return_value = redirect
            result = await dep(request=req, token=None)
            assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_exchange_no_access_token_fallback(self):
        """Covers branch 604->650: token exchange configured but no access token."""
        dep = require_resource_scopes_or_redirect("knowledge")
        req = _make_request()
        user = _make_user(scopes=["knowledge:read"])
        with (
            patch(
                "internal.auth.dependencies.get_current_user_or_redirect", new_callable=AsyncMock
            ) as mock_gcuor,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
            patch("internal.auth.dependencies.get_current_access_token") as mock_gcat,
        ):
            mock_gcuor.return_value = user
            mock_te.is_configured = True
            mock_gcat.return_value = None  # No access token
            result = await dep(request=req, token=None)
            # Falls back to JWT scope check, user has the scope
            assert isinstance(result, User)

    @pytest.mark.asyncio
    async def test_exchange_success_with_scope(self):
        dep = require_resource_scopes_or_redirect("knowledge")
        req = _make_request()
        user = _make_user(scopes=["knowledge:read"])
        with (
            patch(
                "internal.auth.dependencies.get_current_user_or_redirect", new_callable=AsyncMock
            ) as mock_gcuor,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
            patch("internal.auth.dependencies.get_current_access_token") as mock_gcat,
        ):
            mock_gcuor.return_value = user
            mock_te.is_configured = True
            mock_gcat.return_value = "tok"
            mock_te.validate_token_scopes = AsyncMock(
                return_value={"scope": "knowledge:read knowledge:write knowledge:delete"}
            )
            result = await dep(request=req, token=None)
            assert isinstance(result, User)

    @pytest.mark.asyncio
    async def test_exchange_success_missing_min_scope(self):
        dep = require_resource_scopes_or_redirect("admin")
        req = _make_request()
        user = _make_user(scopes=[])
        with (
            patch(
                "internal.auth.dependencies.get_current_user_or_redirect", new_callable=AsyncMock
            ) as mock_gcuor,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
            patch("internal.auth.dependencies.get_current_access_token") as mock_gcat,
            patch("internal.auth.dependencies.templates") as mock_templates,
        ):
            mock_gcuor.return_value = user
            mock_te.is_configured = True
            mock_gcat.return_value = "tok"
            mock_te.validate_token_scopes = AsyncMock(return_value={"scope": ""})
            mock_templates.TemplateResponse.return_value = HTMLResponse(
                content="403", status_code=403
            )
            result = await dep(request=req, token=None)
            assert isinstance(result, HTMLResponse)

    @pytest.mark.asyncio
    async def test_exchange_insufficient_scope_error(self):
        from internal.services.token_exchange import TokenExchangeError

        dep = require_resource_scopes_or_redirect("knowledge")
        req = _make_request()
        user = _make_user(scopes=[])
        with (
            patch(
                "internal.auth.dependencies.get_current_user_or_redirect", new_callable=AsyncMock
            ) as mock_gcuor,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
            patch("internal.auth.dependencies.get_current_access_token") as mock_gcat,
            patch("internal.auth.dependencies.templates") as mock_templates,
        ):
            mock_gcuor.return_value = user
            mock_te.is_configured = True
            mock_gcat.return_value = "tok"
            err = TokenExchangeError("insufficient")
            err.error_code = "insufficient_scope"
            mock_te.validate_token_scopes = AsyncMock(side_effect=err)
            mock_templates.TemplateResponse.return_value = HTMLResponse(
                content="403", status_code=403
            )
            result = await dep(request=req, token=None)
            assert isinstance(result, HTMLResponse)

    @pytest.mark.asyncio
    async def test_exchange_other_error(self):
        from internal.services.token_exchange import TokenExchangeError

        dep = require_resource_scopes_or_redirect("knowledge")
        req = _make_request()
        user = _make_user(scopes=[])
        with (
            patch(
                "internal.auth.dependencies.get_current_user_or_redirect", new_callable=AsyncMock
            ) as mock_gcuor,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
            patch("internal.auth.dependencies.get_current_access_token") as mock_gcat,
            patch("internal.auth.dependencies.templates") as mock_templates,
        ):
            mock_gcuor.return_value = user
            mock_te.is_configured = True
            mock_gcat.return_value = "tok"
            err = TokenExchangeError("server error")
            err.error_code = "server_error"
            mock_te.validate_token_scopes = AsyncMock(side_effect=err)
            mock_templates.TemplateResponse.return_value = HTMLResponse(
                content="403", status_code=403
            )
            result = await dep(request=req, token=None)
            assert isinstance(result, HTMLResponse)

    @pytest.mark.asyncio
    async def test_fallback_has_scope(self):
        dep = require_resource_scopes_or_redirect("knowledge")
        req = _make_request()
        user = _make_user(scopes=["knowledge:read"])
        with (
            patch(
                "internal.auth.dependencies.get_current_user_or_redirect", new_callable=AsyncMock
            ) as mock_gcuor,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
        ):
            mock_gcuor.return_value = user
            mock_te.is_configured = False
            result = await dep(request=req, token=None)
            assert isinstance(result, User)

    @pytest.mark.asyncio
    async def test_fallback_missing_scope(self):
        dep = require_resource_scopes_or_redirect("admin")
        req = _make_request()
        user = _make_user(scopes=["knowledge:read"])
        with (
            patch(
                "internal.auth.dependencies.get_current_user_or_redirect", new_callable=AsyncMock
            ) as mock_gcuor,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
            patch("internal.auth.dependencies.templates") as mock_templates,
        ):
            mock_gcuor.return_value = user
            mock_te.is_configured = False
            mock_templates.TemplateResponse.return_value = HTMLResponse(
                content="403", status_code=403
            )
            result = await dep(request=req, token=None)
            assert isinstance(result, HTMLResponse)

    @pytest.mark.asyncio
    async def test_extra_scopes(self):
        dep = require_resource_scopes_or_redirect("knowledge", extra_scopes=["analytics:read"])
        req = _make_request()
        user = _make_user(scopes=["knowledge:read"])
        with (
            patch(
                "internal.auth.dependencies.get_current_user_or_redirect", new_callable=AsyncMock
            ) as mock_gcuor,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
            patch("internal.auth.dependencies.get_current_access_token") as mock_gcat,
        ):
            mock_gcuor.return_value = user
            mock_te.is_configured = True
            mock_gcat.return_value = "tok"
            mock_te.validate_token_scopes = AsyncMock(
                return_value={"scope": "knowledge:read analytics:read"}
            )
            result = await dep(request=req, token=None)
            assert isinstance(result, User)

    @pytest.mark.asyncio
    async def test_custom_required_scope(self):
        dep = require_resource_scopes_or_redirect("knowledge", required_scope="knowledge:write")
        req = _make_request()
        user = _make_user(scopes=["knowledge:write"])
        with (
            patch(
                "internal.auth.dependencies.get_current_user_or_redirect", new_callable=AsyncMock
            ) as mock_gcuor,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
        ):
            mock_gcuor.return_value = user
            mock_te.is_configured = False
            result = await dep(request=req, token=None)
            assert isinstance(result, User)


class TestRequireAnyScope:
    @pytest.mark.asyncio
    async def test_has_one_scope(self):
        dep = require_any_scope("knowledge:read", "admin:read")
        user = _make_user(scopes=["knowledge:read"])
        result = await dep(user=user)
        assert result.id == USER_UUID

    @pytest.mark.asyncio
    async def test_missing_all_scopes(self):
        dep = require_any_scope("admin:read", "admin:write")
        user = _make_user(scopes=["knowledge:read"])
        with pytest.raises(HTTPException) as exc_info:
            await dep(user=user)
        assert exc_info.value.status_code == 403


class TestGetExchangedToken:
    @pytest.mark.asyncio
    async def test_no_token(self):
        req = _make_request()
        with patch(
            "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
        ) as mock_gtr:
            mock_gtr.return_value = None
            with pytest.raises(HTTPException) as exc_info:
                await get_exchanged_token(req, ["users:read"], None)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_success(self):
        req = _make_request()
        with (
            patch(
                "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
            ) as mock_gtr,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
        ):
            mock_gtr.return_value = "tok"
            mock_te.exchange_token = AsyncMock(return_value={"access_token": "exchanged-tok"})
            result = await get_exchanged_token(req, ["users:read"], None)
            assert result == "exchanged-tok"

    @pytest.mark.asyncio
    async def test_exchange_error(self):
        from internal.services.token_exchange import TokenExchangeError

        req = _make_request()
        with (
            patch(
                "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
            ) as mock_gtr,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
        ):
            mock_gtr.return_value = "tok"
            mock_te.exchange_token = AsyncMock(side_effect=TokenExchangeError("fail"))
            with pytest.raises(HTTPException) as exc_info:
                await get_exchanged_token(req, ["users:read"], None)
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_config_error(self):
        req = _make_request()
        with (
            patch(
                "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
            ) as mock_gtr,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
        ):
            mock_gtr.return_value = "tok"
            mock_te.exchange_token = AsyncMock(side_effect=Exception("not configured"))
            with pytest.raises(HTTPException) as exc_info:
                await get_exchanged_token(req, ["users:read"], None)
            assert exc_info.value.status_code == 500


class TestRequireExchangedToken:
    @pytest.mark.asyncio
    async def test_calls_get_exchanged_token(self):
        dep = require_exchanged_token("users:read", "users:write")
        req = _make_request()
        with (
            patch(
                "internal.auth.dependencies.get_token_from_request", new_callable=AsyncMock
            ) as mock_gtr,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
        ):
            mock_gtr.return_value = "tok"
            mock_te.exchange_token = AsyncMock(return_value={"access_token": "exchanged"})
            result = await dep(request=req, token=None)
            assert result == "exchanged"


class TestPendingTokenRefresh:
    def test_get_and_clear(self):
        import internal.auth.dependencies as deps

        original = deps._pending_token_refresh
        try:
            deps._pending_token_refresh = {"access_token": "tok"}
            assert get_pending_token_refresh() == {"access_token": "tok"}
            clear_pending_token_refresh()
            assert get_pending_token_refresh() is None
        finally:
            deps._pending_token_refresh = original


class TestCookieNames:
    def test_cookie_constants(self):
        assert ACCESS_TOKEN_COOKIE == "access_token"
        assert REFRESH_TOKEN_COOKIE == "refresh_token"
        assert USER_INFO_COOKIE == "user_info"


# =========================================================================
# Sidebar scopes
# =========================================================================


class TestSidebarScopes:
    def test_sidebar_scopes_are_appended_once(self):
        from internal.auth.dependencies import SIDEBAR_SCOPES, _with_sidebar_scopes

        assert SIDEBAR_SCOPES == ("vpn:admin", "billing:read")
        assert _with_sidebar_scopes(["knowledge:read"]) == [
            "knowledge:read",
            "vpn:admin",
            "billing:read",
        ]
        assert _with_sidebar_scopes(["billing:read", "x:read"]) == [
            "billing:read",
            "x:read",
            "vpn:admin",
        ]

    @pytest.mark.asyncio
    async def test_require_scope_or_redirect_requests_sidebar_scopes(self):
        dep = require_scope_or_redirect("knowledge:write")
        user = _make_user(scopes=[])
        with (
            patch(
                "internal.auth.dependencies.get_current_user_or_redirect", new_callable=AsyncMock
            ) as mock_gcuor,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
            patch("internal.auth.dependencies.get_current_access_token") as mock_gcat,
        ):
            mock_gcuor.return_value = user
            mock_te.is_configured = True
            mock_gcat.return_value = "tok"
            mock_te.validate_token_scopes = AsyncMock(
                return_value={"scope": "knowledge:write vpn:admin"}
            )
            result = await dep(request=_make_request(), token=None)
            assert isinstance(result, User)
            assert result.has_scope("vpn:admin")
            mock_te.validate_token_scopes.assert_awaited_once_with(
                "tok", ["knowledge:write", "vpn:admin", "billing:read"]
            )

    @pytest.mark.asyncio
    async def test_require_scope_or_redirect_rejects_a_grant_limited_to_sidebar_scopes(self):
        dep = require_scope_or_redirect("knowledge:write")
        user = _make_user(scopes=[])
        with (
            patch(
                "internal.auth.dependencies.get_current_user_or_redirect", new_callable=AsyncMock
            ) as mock_gcuor,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
            patch("internal.auth.dependencies.get_current_access_token") as mock_gcat,
            patch("internal.auth.dependencies.templates") as mock_templates,
        ):
            mock_gcuor.return_value = user
            mock_te.is_configured = True
            mock_gcat.return_value = "tok"
            mock_te.validate_token_scopes = AsyncMock(return_value={"scope": "vpn:admin"})
            mock_templates.TemplateResponse.return_value = HTMLResponse(
                content="403", status_code=403
            )
            result = await dep(request=_make_request(), token=None)
            assert isinstance(result, HTMLResponse)
            assert result.status_code == 403
            assert (
                mock_templates.TemplateResponse.call_args.kwargs["context"]["required_scope"]
                == "knowledge:write"
            )

    @pytest.mark.asyncio
    async def test_require_resource_scopes_or_redirect_requests_sidebar_scopes(self):
        dep = require_resource_scopes_or_redirect("knowledge", extra_scopes=["vpn:admin"])
        user = _make_user(scopes=[])
        with (
            patch(
                "internal.auth.dependencies.get_current_user_or_redirect", new_callable=AsyncMock
            ) as mock_gcuor,
            patch("internal.auth.dependencies.token_exchange_client") as mock_te,
            patch("internal.auth.dependencies.get_current_access_token") as mock_gcat,
        ):
            mock_gcuor.return_value = user
            mock_te.is_configured = True
            mock_gcat.return_value = "tok"
            mock_te.validate_token_scopes = AsyncMock(return_value={"scope": "knowledge:read"})
            result = await dep(request=_make_request(), token=None)
            assert isinstance(result, User)
            mock_te.validate_token_scopes.assert_awaited_once_with(
                "tok",
                [
                    "knowledge:read",
                    "knowledge:write",
                    "knowledge:delete",
                    "vpn:admin",
                    "billing:read",
                ],
            )
