# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for app/routes/auth.py - OAuth2 authentication routes."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi import HTTPException
from fastapi.responses import RedirectResponse

USER_UUID = uuid.UUID("12345678-1234-5678-1234-567812345678")


def _make_request(**kwargs):
    req = MagicMock()
    req.query_params = kwargs.get("query_params", {})
    req.headers = kwargs.get("headers", {})
    req.form = AsyncMock(return_value=MagicMock())
    req.cookies = kwargs.get("cookies", {})
    return req


# =========================================================================
# Helper functions
# =========================================================================


class TestGeneratePkceVerifier:
    def test_returns_string(self):
        from internal.routes.auth import _generate_pkce_verifier

        result = _generate_pkce_verifier()
        assert isinstance(result, str)
        assert len(result) <= 128
        assert len(result) > 0

    def test_different_each_call(self):
        from internal.routes.auth import _generate_pkce_verifier

        v1 = _generate_pkce_verifier()
        v2 = _generate_pkce_verifier()
        assert v1 != v2


class TestGeneratePkceChallenge:
    def test_returns_string(self):
        from internal.routes.auth import _generate_pkce_challenge

        result = _generate_pkce_challenge("test-verifier")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_deterministic(self):
        from internal.routes.auth import _generate_pkce_challenge

        c1 = _generate_pkce_challenge("same-verifier")
        c2 = _generate_pkce_challenge("same-verifier")
        assert c1 == c2

    def test_different_verifiers_produce_different_challenges(self):
        from internal.routes.auth import _generate_pkce_challenge

        c1 = _generate_pkce_challenge("verifier-one")
        c2 = _generate_pkce_challenge("verifier-two")
        assert c1 != c2

    def test_no_padding(self):
        from internal.routes.auth import _generate_pkce_challenge

        result = _generate_pkce_challenge("test-verifier")
        assert "=" not in result


class TestIsPkceRelatedError:
    def test_no_error(self):
        from internal.routes.auth import _is_pkce_related_error

        assert _is_pkce_related_error(None, None) is False

    def test_pkce_in_error(self):
        from internal.routes.auth import _is_pkce_related_error

        assert _is_pkce_related_error("pkce_error", None) is True

    def test_code_challenge_in_description(self):
        from internal.routes.auth import _is_pkce_related_error

        assert _is_pkce_related_error(None, "Invalid code_challenge") is True

    def test_code_verifier_in_description(self):
        from internal.routes.auth import _is_pkce_related_error

        assert _is_pkce_related_error("error", "bad code_verifier") is True

    def test_non_pkce_error(self):
        from internal.routes.auth import _is_pkce_related_error

        assert _is_pkce_related_error("access_denied", "User denied access") is False

    def test_empty_strings(self):
        from internal.routes.auth import _is_pkce_related_error

        assert _is_pkce_related_error("", "") is False


# =========================================================================
# Login
# =========================================================================


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_redirects(self):
        from internal.routes.auth import login

        req = _make_request()
        with patch("internal.routes.auth.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_frontend_client_id = "frontend-client"
            mock_settings.app_base_url = "https://app.example.com"
            mock_settings.cookie_secure = False

            result = await login(req, redirect="/dashboard")

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        location = result.headers.get("location", "")
        assert "auth.example.com" in location
        assert "oauth2/authorize" in location
        assert "frontend-client" in location
        assert "S256" in location

    @pytest.mark.asyncio
    async def test_login_sets_cookies(self):
        from internal.routes.auth import login

        req = _make_request()
        with patch("internal.routes.auth.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_frontend_client_id = "frontend-client"
            mock_settings.app_base_url = "https://app.example.com"
            mock_settings.cookie_secure = False

            result = await login(req, redirect="/")

        # Check cookies are set (headers contain set-cookie)
        cookie_headers = [h for h in result.raw_headers if h[0] == b"set-cookie"]
        cookie_str = b" ".join(v for _, v in cookie_headers).decode()
        assert "oauth_state" in cookie_str
        assert "oauth_redirect" in cookie_str
        assert "oauth_code_verifier" in cookie_str

    @pytest.mark.asyncio
    async def test_login_default_redirect(self):
        from internal.routes.auth import login

        req = _make_request()
        with patch("internal.routes.auth.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com/"
            mock_settings.oauth2_frontend_client_id = "frontend-client"
            mock_settings.app_base_url = "https://app.example.com"
            mock_settings.cookie_secure = True

            result = await login(req)

        assert isinstance(result, RedirectResponse)


# =========================================================================
# Callback
# =========================================================================


class TestCallback:
    @pytest.mark.asyncio
    async def test_error_response_non_pkce(self):
        from internal.routes.auth import callback

        req = _make_request()
        with patch("internal.routes.auth.templates") as mock_templates:
            mock_templates.TemplateResponse.return_value = MagicMock()
            await callback(
                request=req,
                code=None,
                state=None,
                error="access_denied",
                error_description="User denied consent",
                oauth_state=None,
                oauth_redirect=None,
                oauth_code_verifier=None,
            )
            mock_templates.TemplateResponse.assert_called_once()
            call_kwargs = mock_templates.TemplateResponse.call_args
            assert call_kwargs.kwargs["name"] == "auth/error.html"
            assert call_kwargs.kwargs["context"]["error"] == "access_denied"

    @pytest.mark.asyncio
    async def test_error_response_pkce_redirects_to_login(self):
        from internal.routes.auth import callback

        req = _make_request()
        result = await callback(
            request=req,
            code=None,
            state=None,
            error="invalid_request",
            error_description="Invalid code_challenge",
            oauth_state=None,
            oauth_redirect="/dashboard",
            oauth_code_verifier=None,
        )
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        location = result.headers.get("location", "")
        assert "/auth/login" in location

    @pytest.mark.asyncio
    async def test_error_response_pkce_default_redirect(self):
        from internal.routes.auth import callback

        req = _make_request()
        result = await callback(
            request=req,
            code=None,
            state=None,
            error="pkce_error",
            error_description=None,
            oauth_state=None,
            oauth_redirect=None,
            oauth_code_verifier=None,
        )
        assert isinstance(result, RedirectResponse)
        location = result.headers.get("location", "")
        assert "/auth/login?redirect=/" in location

    @pytest.mark.asyncio
    async def test_error_response_pkce_keeps_the_query_of_the_page(self):
        from internal.routes.auth import callback

        req = _make_request()
        result = await callback(
            request=req,
            code=None,
            state=None,
            error="pkce_error",
            error_description=None,
            oauth_state=None,
            oauth_redirect="http://admin.test/contacts?page=2&search=ada",
            oauth_code_verifier=None,
        )
        location = result.headers.get("location", "")
        # The whole address is one value of the redirect parameter
        assert location.count("&") == 0
        assert parse_qs(urlparse(location).query)["redirect"] == [
            "http://admin.test/contacts?page=2&search=ada"
        ]

    @pytest.mark.asyncio
    async def test_missing_code(self):
        from internal.routes.auth import callback

        req = _make_request()
        with patch("internal.routes.auth.templates") as mock_templates:
            mock_templates.TemplateResponse.return_value = MagicMock()
            await callback(
                request=req,
                code=None,
                state="some-state",
                error=None,
                error_description=None,
                oauth_state="some-state",
                oauth_redirect=None,
                oauth_code_verifier="verifier",
            )
            call_kwargs = mock_templates.TemplateResponse.call_args
            assert call_kwargs.kwargs["context"]["error"] == "invalid_request"

    @pytest.mark.asyncio
    async def test_missing_state(self):
        from internal.routes.auth import callback

        req = _make_request()
        with patch("internal.routes.auth.templates") as mock_templates:
            mock_templates.TemplateResponse.return_value = MagicMock()
            await callback(
                request=req,
                code="auth-code",
                state=None,
                error=None,
                error_description=None,
                oauth_state="some-state",
                oauth_redirect=None,
                oauth_code_verifier="verifier",
            )
            call_kwargs = mock_templates.TemplateResponse.call_args
            assert call_kwargs.kwargs["context"]["error"] == "invalid_request"

    @pytest.mark.asyncio
    async def test_oauth_state_cookie_missing_redirects(self):
        from internal.routes.auth import callback

        req = _make_request()
        result = await callback(
            request=req,
            code="auth-code",
            state="some-state",
            error=None,
            error_description=None,
            oauth_state=None,
            oauth_redirect="/dashboard",
            oauth_code_verifier="verifier",
        )
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302

    @pytest.mark.asyncio
    async def test_oauth_state_cookie_missing_default_redirect(self):
        from internal.routes.auth import callback

        req = _make_request()
        result = await callback(
            request=req,
            code="auth-code",
            state="some-state",
            error=None,
            error_description=None,
            oauth_state=None,
            oauth_redirect=None,
            oauth_code_verifier="verifier",
        )
        assert isinstance(result, RedirectResponse)
        location = result.headers.get("location", "")
        assert "/auth/login?redirect=/" in location

    @pytest.mark.asyncio
    async def test_state_mismatch(self):
        from internal.routes.auth import callback

        req = _make_request()
        with patch("internal.routes.auth.templates") as mock_templates:
            mock_templates.TemplateResponse.return_value = MagicMock()
            await callback(
                request=req,
                code="auth-code",
                state="wrong-state",
                error=None,
                error_description=None,
                oauth_state="correct-state",
                oauth_redirect=None,
                oauth_code_verifier="verifier",
            )
            call_kwargs = mock_templates.TemplateResponse.call_args
            assert call_kwargs.kwargs["context"]["error"] == "invalid_state"

    @pytest.mark.asyncio
    async def test_missing_code_verifier_redirects(self):
        from internal.routes.auth import callback

        req = _make_request()
        result = await callback(
            request=req,
            code="auth-code",
            state="good-state",
            error=None,
            error_description=None,
            oauth_state="good-state",
            oauth_redirect="/page",
            oauth_code_verifier=None,
        )
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302

    @pytest.mark.asyncio
    async def test_missing_code_verifier_default_redirect(self):
        from internal.routes.auth import callback

        req = _make_request()
        result = await callback(
            request=req,
            code="auth-code",
            state="good-state",
            error=None,
            error_description=None,
            oauth_state="good-state",
            oauth_redirect=None,
            oauth_code_verifier=None,
        )
        assert isinstance(result, RedirectResponse)
        location = result.headers.get("location", "")
        assert "/auth/login?redirect=/" in location

    @pytest.mark.asyncio
    async def test_missing_code_verifier_empty_string(self):
        from internal.routes.auth import callback

        req = _make_request()
        result = await callback(
            request=req,
            code="auth-code",
            state="good-state",
            error=None,
            error_description=None,
            oauth_state="good-state",
            oauth_redirect=None,
            oauth_code_verifier="",
        )
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_token_exchange_failure(self):
        from internal.routes.auth import callback

        req = _make_request()
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad request"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp

        with (
            patch("internal.routes.auth.settings") as mock_settings,
            patch("internal.routes.auth.httpx.AsyncClient") as MockClient,
            patch("internal.routes.auth.templates") as mock_templates,
        ):
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_frontend_client_id = "frontend"
            mock_settings.app_base_url = "https://app.example.com"
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_templates.TemplateResponse.return_value = MagicMock()

            await callback(
                request=req,
                code="auth-code",
                state="good-state",
                error=None,
                error_description=None,
                oauth_state="good-state",
                oauth_redirect=None,
                oauth_code_verifier="verifier",
            )
            call_kwargs = mock_templates.TemplateResponse.call_args
            assert call_kwargs.kwargs["context"]["error"] == "token_exchange_failed"

    @pytest.mark.asyncio
    async def test_httpx_request_error(self):
        from internal.routes.auth import callback

        req = _make_request()
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.RequestError("Connection refused")

        with (
            patch("internal.routes.auth.settings") as mock_settings,
            patch("internal.routes.auth.httpx.AsyncClient") as MockClient,
            patch("internal.routes.auth.templates") as mock_templates,
        ):
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_frontend_client_id = "frontend"
            mock_settings.app_base_url = "https://app.example.com"
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_templates.TemplateResponse.return_value = MagicMock()

            await callback(
                request=req,
                code="auth-code",
                state="good-state",
                error=None,
                error_description=None,
                oauth_state="good-state",
                oauth_redirect=None,
                oauth_code_verifier="verifier",
            )
            call_kwargs = mock_templates.TemplateResponse.call_args
            assert call_kwargs.kwargs["context"]["error"] == "server_error"

    @pytest.mark.asyncio
    async def test_no_access_token_in_response(self):
        from internal.routes.auth import callback

        req = _make_request()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"token_type": "bearer"}  # no access_token

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp

        with (
            patch("internal.routes.auth.settings") as mock_settings,
            patch("internal.routes.auth.httpx.AsyncClient") as MockClient,
            patch("internal.routes.auth.templates") as mock_templates,
        ):
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_frontend_client_id = "frontend"
            mock_settings.app_base_url = "https://app.example.com"
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_templates.TemplateResponse.return_value = MagicMock()

            await callback(
                request=req,
                code="auth-code",
                state="good-state",
                error=None,
                error_description=None,
                oauth_state="good-state",
                oauth_redirect=None,
                oauth_code_verifier="verifier",
            )
            call_kwargs = mock_templates.TemplateResponse.call_args
            assert call_kwargs.kwargs["context"]["error"] == "no_token"

    @pytest.mark.asyncio
    async def test_success_with_user_info_and_refresh_token(self):
        from internal.routes.auth import callback

        req = _make_request()
        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.json.return_value = {
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "expires_in": 3600,
        }

        userinfo_resp = MagicMock()
        userinfo_resp.status_code = 200
        userinfo_resp.json.return_value = {
            "name": "Test User",
            "email": "test@example.com",
            "picture": "https://example.com/pic.jpg",
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = token_resp
        mock_client.get.return_value = userinfo_resp

        with (
            patch("internal.routes.auth.settings") as mock_settings,
            patch("internal.routes.auth.httpx.AsyncClient") as MockClient,
        ):
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_frontend_client_id = "frontend"
            mock_settings.app_base_url = "https://app.example.com"
            mock_settings.cookie_secure = False
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await callback(
                request=req,
                code="auth-code",
                state="good-state",
                error=None,
                error_description=None,
                oauth_state="good-state",
                oauth_redirect="/dashboard",
                oauth_code_verifier="verifier",
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        location = result.headers.get("location", "")
        assert location == "/dashboard"

    @pytest.mark.asyncio
    async def test_success_without_user_info(self):
        from internal.routes.auth import callback

        req = _make_request()
        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.json.return_value = {
            "access_token": "new-access-token",
            "expires_in": 3600,
        }

        userinfo_resp = MagicMock()
        userinfo_resp.status_code = 500  # userinfo fails

        mock_client = AsyncMock()
        mock_client.post.return_value = token_resp
        mock_client.get.return_value = userinfo_resp

        with (
            patch("internal.routes.auth.settings") as mock_settings,
            patch("internal.routes.auth.httpx.AsyncClient") as MockClient,
        ):
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_frontend_client_id = "frontend"
            mock_settings.app_base_url = "https://app.example.com"
            mock_settings.cookie_secure = False
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await callback(
                request=req,
                code="auth-code",
                state="good-state",
                error=None,
                error_description=None,
                oauth_state="good-state",
                oauth_redirect=None,
                oauth_code_verifier="verifier",
            )

        assert isinstance(result, RedirectResponse)
        location = result.headers.get("location", "")
        assert location == "/"

    @pytest.mark.asyncio
    async def test_success_without_refresh_token(self):
        from internal.routes.auth import callback

        req = _make_request()
        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.json.return_value = {
            "access_token": "new-access-token",
            "expires_in": 7200,
        }

        userinfo_resp = MagicMock()
        userinfo_resp.status_code = 200
        userinfo_resp.json.return_value = {
            "name": "Test",
            "email": "t@t.com",
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = token_resp
        mock_client.get.return_value = userinfo_resp

        with (
            patch("internal.routes.auth.settings") as mock_settings,
            patch("internal.routes.auth.httpx.AsyncClient") as MockClient,
        ):
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_frontend_client_id = "frontend"
            mock_settings.app_base_url = "https://app.example.com"
            mock_settings.cookie_secure = False
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await callback(
                request=req,
                code="auth-code",
                state="good-state",
                error=None,
                error_description=None,
                oauth_state="good-state",
                oauth_redirect=None,
                oauth_code_verifier="verifier",
            )

        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_userinfo_exception(self):
        from internal.routes.auth import callback

        req = _make_request()
        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.json.return_value = {
            "access_token": "access-tok",
            "expires_in": 3600,
        }

        # First call (token exchange) succeeds, second call (userinfo) raises
        mock_client_token = AsyncMock()
        mock_client_token.post.return_value = token_resp

        mock_client_userinfo = AsyncMock()
        mock_client_userinfo.get.side_effect = Exception("Network error")

        with (
            patch("internal.routes.auth.settings") as mock_settings,
            patch("internal.routes.auth.httpx.AsyncClient") as MockClient,
        ):
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_frontend_client_id = "frontend"
            mock_settings.app_base_url = "https://app.example.com"
            mock_settings.cookie_secure = False

            # First context manager call returns token client, second returns userinfo client
            cm1 = AsyncMock()
            cm1.__aenter__ = AsyncMock(return_value=mock_client_token)
            cm1.__aexit__ = AsyncMock(return_value=False)

            cm2 = AsyncMock()
            cm2.__aenter__ = AsyncMock(return_value=mock_client_userinfo)
            cm2.__aexit__ = AsyncMock(return_value=False)

            MockClient.side_effect = [cm1, cm2]

            result = await callback(
                request=req,
                code="auth-code",
                state="good-state",
                error=None,
                error_description=None,
                oauth_state="good-state",
                oauth_redirect=None,
                oauth_code_verifier="verifier",
            )

        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_success_default_expires_in(self):
        from internal.routes.auth import callback

        req = _make_request()
        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.json.return_value = {
            "access_token": "access-tok",
            # no expires_in => defaults to 3600
        }

        userinfo_resp = MagicMock()
        userinfo_resp.status_code = 404

        mock_client = AsyncMock()
        mock_client.post.return_value = token_resp
        mock_client.get.return_value = userinfo_resp

        with (
            patch("internal.routes.auth.settings") as mock_settings,
            patch("internal.routes.auth.httpx.AsyncClient") as MockClient,
        ):
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_frontend_client_id = "frontend"
            mock_settings.app_base_url = "https://app.example.com"
            mock_settings.cookie_secure = False
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await callback(
                request=req,
                code="auth-code",
                state="good-state",
                error=None,
                error_description=None,
                oauth_state="good-state",
                oauth_redirect=None,
                oauth_code_verifier="verifier",
            )

        assert isinstance(result, RedirectResponse)


# =========================================================================
# Logout
# =========================================================================


class TestLogout:
    @pytest.mark.asyncio
    async def test_logout_redirects(self):
        from internal.routes.auth import logout

        with patch("internal.routes.auth.settings") as mock_settings:
            mock_settings.oauth2_frontend_client_id = "frontend"
            result = await logout(redirect="/auth/login")

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        assert result.headers.get("location") == "/auth/login"

    @pytest.mark.asyncio
    async def test_logout_custom_redirect(self):
        from internal.routes.auth import logout

        with patch("internal.routes.auth.settings") as mock_settings:
            mock_settings.oauth2_frontend_client_id = "frontend"
            result = await logout(redirect="/custom")

        assert isinstance(result, RedirectResponse)
        assert result.headers.get("location") == "/custom"

    @pytest.mark.asyncio
    async def test_logout_clears_cookies(self):
        from internal.routes.auth import logout

        with patch("internal.routes.auth.settings") as mock_settings:
            mock_settings.oauth2_frontend_client_id = "frontend"
            result = await logout()

        cookie_headers = [h for h in result.raw_headers if h[0] == b"set-cookie"]
        cookie_str = b" ".join(v for _, v in cookie_headers).decode()
        assert "access_token" in cookie_str
        assert "refresh_token" in cookie_str
        assert "user_info" in cookie_str
        assert "oauth_state" in cookie_str


# =========================================================================
# Refresh Token
# =========================================================================


class TestRefreshToken:
    @pytest.mark.asyncio
    async def test_no_refresh_token_raises_401(self):
        from internal.routes.auth import refresh_token

        req = _make_request()
        with pytest.raises(HTTPException) as exc_info:
            await refresh_token(request=req, refresh_token=None)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_success(self):
        from internal.routes.auth import refresh_token

        req = _make_request(headers={"referer": "/dashboard"})
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "new-at",
            "refresh_token": "new-rt",
            "expires_in": 3600,
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp

        with (
            patch("internal.routes.auth.settings") as mock_settings,
            patch("internal.routes.auth.httpx.AsyncClient") as MockClient,
        ):
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_frontend_client_id = "frontend"
            mock_settings.cookie_secure = False
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await refresh_token(request=req, refresh_token="old-rt")

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        assert result.headers.get("location") == "/dashboard"

    @pytest.mark.asyncio
    async def test_refresh_success_without_new_refresh_token(self):
        from internal.routes.auth import refresh_token

        req = _make_request(headers={})
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "new-at",
            "expires_in": 3600,
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp

        with (
            patch("internal.routes.auth.settings") as mock_settings,
            patch("internal.routes.auth.httpx.AsyncClient") as MockClient,
        ):
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_frontend_client_id = "frontend"
            mock_settings.cookie_secure = False
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await refresh_token(request=req, refresh_token="old-rt")

        assert isinstance(result, RedirectResponse)
        assert result.headers.get("location") == "/"

    @pytest.mark.asyncio
    async def test_refresh_token_exchange_fails(self):
        from internal.routes.auth import refresh_token

        req = _make_request()
        mock_resp = MagicMock()
        mock_resp.status_code = 400

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp

        with (
            patch("internal.routes.auth.settings") as mock_settings,
            patch("internal.routes.auth.httpx.AsyncClient") as MockClient,
        ):
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_frontend_client_id = "frontend"
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await refresh_token(request=req, refresh_token="old-rt")

        assert isinstance(result, RedirectResponse)
        assert result.headers.get("location") == "/auth/login"

    @pytest.mark.asyncio
    async def test_refresh_httpx_error(self):
        from internal.routes.auth import refresh_token

        req = _make_request()
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.RequestError("Connection refused")

        with (
            patch("internal.routes.auth.settings") as mock_settings,
            patch("internal.routes.auth.httpx.AsyncClient") as MockClient,
        ):
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_frontend_client_id = "frontend"
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(HTTPException) as exc_info:
                await refresh_token(request=req, refresh_token="old-rt")
            assert exc_info.value.status_code == 502

    @pytest.mark.asyncio
    async def test_refresh_default_expires_in(self):
        from internal.routes.auth import refresh_token

        req = _make_request()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "new-at",
            # no expires_in => defaults to 3600
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp

        with (
            patch("internal.routes.auth.settings") as mock_settings,
            patch("internal.routes.auth.httpx.AsyncClient") as MockClient,
        ):
            mock_settings.oauth2_issuer = "https://auth.example.com/"
            mock_settings.oauth2_frontend_client_id = "frontend"
            mock_settings.cookie_secure = False
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await refresh_token(request=req, refresh_token="old-rt")

        assert isinstance(result, RedirectResponse)


# =========================================================================
# Constants
# =========================================================================


class TestConstants:
    def test_user_info_cookie(self):
        from internal.routes.auth import USER_INFO_COOKIE

        assert USER_INFO_COOKIE == "user_info"

    def test_pkce_error_keywords(self):
        from internal.routes.auth import PKCE_ERROR_KEYWORDS

        assert "pkce" in PKCE_ERROR_KEYWORDS
        assert "code_challenge" in PKCE_ERROR_KEYWORDS
        assert "code_verifier" in PKCE_ERROR_KEYWORDS
