# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.api.routes.auth.login — Login endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from tests.conftest import make_user

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MODULE = "auth.api.routes.auth.login"


def _mock_request(
    cookies=None, headers=None, host="10.0.0.1", url="https://auth.example.com/login"
):
    request = MagicMock()
    request.cookies = cookies or {}
    request.headers = MagicMock()
    request.headers.get = MagicMock(side_effect=lambda k, d=None: (headers or {}).get(k, d))
    request.client = MagicMock()
    request.client.host = host
    request.url = MagicMock()
    request.url.hostname = "auth.example.com"
    request.url.__str__ = MagicMock(return_value=url)
    request.base_url = "https://auth.example.com/"
    return request


# ---------------------------------------------------------------------------
# get_tenant_prefix / get_current_tenant_id
# ---------------------------------------------------------------------------


class TestGetTenantPrefix:
    @patch(f"{MODULE}.get_tenant_context", return_value=None)
    def test_no_context(self, _):
        from auth.api.routes.auth.login import get_tenant_prefix

        assert get_tenant_prefix() == ""

    @patch(f"{MODULE}.get_tenant_context")
    def test_path_resolution(self, mock_ctx):
        from auth.api.routes.auth.login import get_tenant_prefix

        ctx = MagicMock()
        ctx.tenant_slug = "knowledge"
        ctx.resolution_method = "path"
        mock_ctx.return_value = ctx
        assert get_tenant_prefix() == "/t/knowledge"

    @patch(f"{MODULE}.get_tenant_context")
    def test_subdomain_resolution(self, mock_ctx):
        from auth.api.routes.auth.login import get_tenant_prefix

        ctx = MagicMock()
        ctx.tenant_slug = "knowledge"
        ctx.resolution_method = "subdomain"
        mock_ctx.return_value = ctx
        assert get_tenant_prefix() == ""


class TestGetCurrentTenantId:
    @patch(f"{MODULE}.get_tenant_context", return_value=None)
    def test_no_context(self, _):
        from auth.api.routes.auth.login import get_current_tenant_id

        assert get_current_tenant_id() is None

    @patch(f"{MODULE}.get_tenant_context")
    def test_with_context(self, mock_ctx):
        from auth.api.routes.auth.login import get_current_tenant_id

        ctx = MagicMock()
        ctx.tenant_id = "t-123"
        mock_ctx.return_value = ctx
        assert get_current_tenant_id() == "t-123"


# ---------------------------------------------------------------------------
# _get_client_ip
# ---------------------------------------------------------------------------


class TestGetClientIp:
    def test_from_x_forwarded_for(self):
        from auth.api.routes.auth.login import _get_client_ip

        request = MagicMock()
        request.headers.get.return_value = "1.2.3.4, 5.6.7.8"
        assert _get_client_ip(request) == "1.2.3.4"

    def test_from_client_host(self):
        from auth.api.routes.auth.login import _get_client_ip

        request = MagicMock()
        request.headers.get.return_value = None
        request.client.host = "10.0.0.1"
        assert _get_client_ip(request) == "10.0.0.1"

    def test_no_client(self):
        from auth.api.routes.auth.login import _get_client_ip

        request = MagicMock()
        request.headers.get.return_value = None
        request.client = None
        assert _get_client_ip(request) is None


# ---------------------------------------------------------------------------
# _set_session_cookie
# ---------------------------------------------------------------------------


class TestSetSessionCookie:
    @patch(f"{MODULE}.get_session_cookie_domain", return_value=".example.com")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session_id")
    @patch(f"{MODULE}.settings")
    def test_sets_cookie(self, mock_settings, mock_name, mock_domain):
        from auth.api.routes.auth.login import _set_session_cookie

        mock_settings.session_expiry_days = 7
        mock_settings.session_cookie_secure = True
        response = MagicMock()

        _set_session_cookie(response, "token_abc")

        response.set_cookie.assert_called_once()
        kwargs = response.set_cookie.call_args.kwargs
        assert kwargs["key"] == "session_id"
        assert kwargs["value"] == "token_abc"
        assert kwargs["httponly"] is True
        assert kwargs["secure"] is True
        assert kwargs["domain"] == ".example.com"


# ---------------------------------------------------------------------------
# login_form
# ---------------------------------------------------------------------------


class TestSafeNextUrl:
    @pytest.mark.parametrize(
        ("next_url", "expected"),
        [
            ("/dashboard", "/dashboard"),
            ("/oauth2/authorize?client_id=abc&state=x", "/oauth2/authorize?client_id=abc&state=x"),
            ("https://auth.example.com/page", "https://auth.example.com/page"),
            ("", None),
            ("//other.invalid/landing", None),
            ("/\\other.invalid/landing", None),
            ("/\t/other.invalid/landing", None),
            ("https://other.invalid/landing", None),
            ("javascript:alert(1)", None),
            ("page", None),
        ],
    )
    def test_only_destinations_on_this_server_are_kept(self, next_url, expected):
        from auth.api.routes.auth.login import _safe_next_url

        assert _safe_next_url(next_url, "auth.example.com") == expected


class TestLoginForm:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session_id")
    async def test_no_session_renders_form(self, mock_cookie, mock_prefix, mock_tid):
        from auth.api.routes.auth.login import login_form

        request = _mock_request()
        db = AsyncMock()
        session_svc = MagicMock()
        branding_svc = MagicMock()
        branding_svc.render_template = AsyncMock(return_value="<html>login</html>")

        result = await login_form(request, db, session_svc, branding_svc)

        assert result.status_code == 200
        assert "login" in result.body.decode()

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session_id")
    async def test_already_authenticated_redirects(self, mock_cookie, mock_prefix, mock_tid):
        from auth.api.routes.auth.login import login_form

        user = make_user()
        request = _mock_request(cookies={"session_id": "valid_token"})
        db = AsyncMock()
        session_svc = MagicMock()
        session_svc.get_user_by_session_token = AsyncMock(return_value=user)
        branding_svc = MagicMock()

        result = await login_form(request, db, session_svc, branding_svc)

        assert result.status_code == 302
        assert "/auth/settings" in result.headers.get("location", "")

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session_id")
    async def test_already_authenticated_redirects_to_next(
        self, mock_cookie, mock_prefix, mock_tid
    ):
        from auth.api.routes.auth.login import login_form

        user = make_user()
        request = _mock_request(cookies={"session_id": "valid_token"})
        db = AsyncMock()
        session_svc = MagicMock()
        session_svc.get_user_by_session_token = AsyncMock(return_value=user)
        branding_svc = MagicMock()

        result = await login_form(request, db, session_svc, branding_svc, next="/dashboard")

        assert result.status_code == 302
        assert "/dashboard" in result.headers.get("location", "")

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session_id")
    async def test_verified_success_message(self, mock_cookie, mock_prefix, mock_tid):
        from auth.api.routes.auth.login import login_form

        request = _mock_request()
        db = AsyncMock()
        session_svc = MagicMock()
        branding_svc = MagicMock()
        branding_svc.render_template = AsyncMock(return_value="<html>verified</html>")

        await login_form(request, db, session_svc, branding_svc, verified="1")

        call_args = branding_svc.render_template.call_args
        ctx = call_args[0][2]
        assert "verified" in ctx["success"].lower()

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session_id")
    async def test_reset_success_message(self, mock_cookie, mock_prefix, mock_tid):
        from auth.api.routes.auth.login import login_form

        request = _mock_request()
        db = AsyncMock()
        session_svc = MagicMock()
        branding_svc = MagicMock()
        branding_svc.render_template = AsyncMock(return_value="<html></html>")

        await login_form(request, db, session_svc, branding_svc, reset="1")

        ctx = branding_svc.render_template.call_args[0][2]
        assert "reset" in ctx["success"].lower()

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session_id")
    async def test_registered_success_message(self, mock_cookie, mock_prefix, mock_tid):
        from auth.api.routes.auth.login import login_form

        request = _mock_request()
        db = AsyncMock()
        session_svc = MagicMock()
        branding_svc = MagicMock()
        branding_svc.render_template = AsyncMock(return_value="<html></html>")

        await login_form(request, db, session_svc, branding_svc, registered="1")

        ctx = branding_svc.render_template.call_args[0][2]
        assert "registration" in ctx["success"].lower()


# ---------------------------------------------------------------------------
# login_submit
# ---------------------------------------------------------------------------


class TestLoginSubmit:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}._get_client_ip", return_value="10.0.0.1")
    @patch(f"{MODULE}._set_session_cookie")
    @patch(f"{MODULE}.get_csrf_cookie_name", return_value="csrf_token")
    @patch(f"{MODULE}.get_session_cookie_domain", return_value=".example.com")
    @patch(f"{MODULE}.settings")
    async def test_success_redirect(
        self,
        mock_settings,
        mock_domain,
        mock_csrf_name,
        mock_set_cookie,
        mock_ip,
        mock_prefix,
        mock_tid,
    ):
        from auth.api.routes.auth.login import login_submit

        mock_settings.session_expiry_days = 7
        mock_settings.session_cookie_secure = True

        user = make_user()
        request = _mock_request()
        db = AsyncMock()
        auth_svc = MagicMock()
        auth_svc.authenticate = AsyncMock(return_value=user)
        mfa_svc = MagicMock()
        mfa_svc.get_user_mfa = AsyncMock(return_value=None)
        session_svc = MagicMock()
        session_svc.create_session = AsyncMock(return_value=("sess_tok", "csrf_tok"))
        branding_svc = MagicMock()
        trust_svc = MagicMock()

        result = await login_submit(
            request,
            "test@example.com",
            "password",
            None,
            "",
            db,
            auth_svc,
            mfa_svc,
            session_svc,
            branding_svc,
            trust_svc,
        )

        assert result.status_code == 303
        mock_set_cookie.assert_called_once()

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}._get_client_ip", return_value="10.0.0.1")
    async def test_invalid_credentials(self, mock_ip, mock_prefix, mock_tid):
        from auth.api.routes.auth.login import login_submit

        request = _mock_request()
        db = AsyncMock()
        auth_svc = MagicMock()
        auth_svc.authenticate = AsyncMock(return_value=None)
        mfa_svc = MagicMock()
        session_svc = MagicMock()
        branding_svc = MagicMock()
        branding_svc.render_template = AsyncMock(return_value="<html>error</html>")
        trust_svc = MagicMock()

        result = await login_submit(
            request,
            "test@example.com",
            "wrong",
            None,
            "",
            db,
            auth_svc,
            mfa_svc,
            session_svc,
            branding_svc,
            trust_svc,
        )

        assert result.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value="t-123")
    @patch(f"{MODULE}.get_tenant_prefix", return_value="/t/test")
    @patch(f"{MODULE}._get_client_ip", return_value="10.0.0.1")
    async def test_trust_policy_denied(self, mock_ip, mock_prefix, mock_tid):
        from auth.api.routes.auth.login import login_submit

        user = make_user()
        request = _mock_request()
        db = AsyncMock()
        auth_svc = MagicMock()
        auth_svc.authenticate = AsyncMock(return_value=user)
        mfa_svc = MagicMock()
        mfa_svc.get_user_mfa = AsyncMock(return_value=None)
        session_svc = MagicMock()
        branding_svc = MagicMock()
        branding_svc.render_template = AsyncMock(return_value="<html>denied</html>")
        trust_svc = MagicMock()
        trust_svc.can_user_access_tenant = AsyncMock(return_value=(False, "Not allowed"))

        result = await login_submit(
            request,
            "test@example.com",
            "password",
            None,
            "",
            db,
            auth_svc,
            mfa_svc,
            session_svc,
            branding_svc,
            trust_svc,
        )

        assert result.status_code == 403

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}._get_client_ip", return_value="10.0.0.1")
    @patch(f"{MODULE}._set_session_cookie")
    @patch(f"{MODULE}.get_csrf_cookie_name", return_value="csrf_token")
    @patch(f"{MODULE}.get_session_cookie_domain", return_value=".example.com")
    @patch(f"{MODULE}.settings")
    async def test_redirect_to_next_relative(
        self,
        mock_settings,
        mock_domain,
        mock_csrf_name,
        mock_set_cookie,
        mock_ip,
        mock_prefix,
        mock_tid,
    ):
        from auth.api.routes.auth.login import login_submit

        mock_settings.session_expiry_days = 7
        mock_settings.session_cookie_secure = True

        user = make_user()
        request = _mock_request()
        db = AsyncMock()
        auth_svc = MagicMock()
        auth_svc.authenticate = AsyncMock(return_value=user)
        mfa_svc = MagicMock()
        mfa_svc.get_user_mfa = AsyncMock(return_value=None)
        session_svc = MagicMock()
        session_svc.create_session = AsyncMock(return_value=("s", "c"))
        branding_svc = MagicMock()
        trust_svc = MagicMock()

        result = await login_submit(
            request,
            "test@example.com",
            "password",
            None,
            "/dashboard",
            db,
            auth_svc,
            mfa_svc,
            session_svc,
            branding_svc,
            trust_svc,
        )

        assert result.status_code == 303
        assert "/dashboard" in result.headers.get("location", "")

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}._get_client_ip", return_value="10.0.0.1")
    @patch(f"{MODULE}._set_session_cookie")
    @patch(f"{MODULE}.get_csrf_cookie_name", return_value="csrf_token")
    @patch(f"{MODULE}.get_session_cookie_domain", return_value=".example.com")
    @patch(f"{MODULE}.settings")
    async def test_redirect_to_next_absolute_same_domain(
        self,
        mock_settings,
        mock_domain,
        mock_csrf_name,
        mock_set_cookie,
        mock_ip,
        mock_prefix,
        mock_tid,
    ):
        from auth.api.routes.auth.login import login_submit

        mock_settings.session_expiry_days = 7
        mock_settings.session_cookie_secure = True

        user = make_user()
        request = _mock_request()
        db = AsyncMock()
        auth_svc = MagicMock()
        auth_svc.authenticate = AsyncMock(return_value=user)
        mfa_svc = MagicMock()
        mfa_svc.get_user_mfa = AsyncMock(return_value=None)
        session_svc = MagicMock()
        session_svc.create_session = AsyncMock(return_value=("s", "c"))
        branding_svc = MagicMock()
        trust_svc = MagicMock()

        result = await login_submit(
            request,
            "test@example.com",
            "password",
            None,
            "https://auth.example.com/page",
            db,
            auth_svc,
            mfa_svc,
            session_svc,
            branding_svc,
            trust_svc,
        )

        assert result.status_code == 303
        assert "/page" in result.headers.get("location", "")

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}._get_client_ip", return_value="10.0.0.1")
    @patch(f"{MODULE}._set_session_cookie")
    @patch(f"{MODULE}.get_csrf_cookie_name", return_value="csrf_token")
    @patch(f"{MODULE}.get_session_cookie_domain", return_value=".example.com")
    @patch(f"{MODULE}.settings")
    async def test_protocol_relative_next_is_ignored(
        self,
        mock_settings,
        mock_domain,
        mock_csrf_name,
        mock_set_cookie,
        mock_ip,
        mock_prefix,
        mock_tid,
    ):
        from auth.api.routes.auth.login import login_submit

        mock_settings.session_expiry_days = 7
        mock_settings.session_cookie_secure = True

        user = make_user()
        request = _mock_request()
        db = AsyncMock()
        auth_svc = MagicMock()
        auth_svc.authenticate = AsyncMock(return_value=user)
        mfa_svc = MagicMock()
        mfa_svc.get_user_mfa = AsyncMock(return_value=None)
        session_svc = MagicMock()
        session_svc.create_session = AsyncMock(return_value=("s", "c"))
        branding_svc = MagicMock()
        trust_svc = MagicMock()

        result = await login_submit(
            request,
            "test@example.com",
            "password",
            None,
            "//other.invalid/landing",
            db,
            auth_svc,
            mfa_svc,
            session_svc,
            branding_svc,
            trust_svc,
        )

        assert result.status_code == 303
        assert result.headers.get("location") == "/auth/settings"

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}._get_client_ip", return_value="10.0.0.1")
    async def test_mfa_required_without_otp(self, mock_ip, mock_prefix, mock_tid):
        from auth.api.routes.auth.login import login_submit

        user = make_user()
        request = _mock_request()
        db = AsyncMock()
        auth_svc = MagicMock()
        auth_svc.authenticate = AsyncMock(return_value=user)
        mfa_svc = MagicMock()
        mfa_svc.get_user_mfa = AsyncMock(return_value=MagicMock(totp_enabled=True))
        mfa_svc.verify_mfa_code_with_email = AsyncMock(return_value=False)
        session_svc = MagicMock()
        branding_svc = MagicMock()
        branding_svc.render_template = AsyncMock(return_value="<html>mfa</html>")
        trust_svc = MagicMock()

        result = await login_submit(
            request,
            "test@example.com",
            "password",
            None,
            "",
            db,
            auth_svc,
            mfa_svc,
            session_svc,
            branding_svc,
            trust_svc,
        )

        assert result.status_code == 200
        ctx = branding_svc.render_template.call_args[0][2]
        assert ctx["mfa_required"] is True
        assert "password verified" in ctx["success"].lower()

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}._get_client_ip", return_value="10.0.0.1")
    async def test_mfa_invalid_otp(self, mock_ip, mock_prefix, mock_tid):
        from auth.api.routes.auth.login import (
            MFA_LOGIN_CHALLENGE_COOKIE,
            _create_mfa_login_challenge,
            login_submit,
        )

        user = make_user()
        challenge = _create_mfa_login_challenge(str(user.id), "test@example.com", "", None)
        request = _mock_request(cookies={MFA_LOGIN_CHALLENGE_COOKIE: challenge})
        db = AsyncMock()
        auth_svc = MagicMock()
        mfa_svc = MagicMock()
        mfa_svc.get_user_mfa = AsyncMock(return_value=MagicMock(totp_enabled=True))
        mfa_svc.verify_mfa_code_with_email = AsyncMock(return_value=False)
        session_svc = MagicMock()
        branding_svc = MagicMock()
        branding_svc.render_template = AsyncMock(return_value="<html>mfa invalid</html>")
        trust_svc = MagicMock()
        user_svc = MagicMock()
        user_svc.get_by_id = AsyncMock(return_value=user)

        result = await login_submit(
            request,
            "test@example.com",
            "password",
            "000000",
            "",
            db,
            auth_svc,
            mfa_svc,
            session_svc,
            branding_svc,
            trust_svc,
            user_service=user_svc,
        )

        assert result.status_code == 400
        ctx = branding_svc.render_template.call_args[0][2]
        assert ctx["mfa_required"] is True
        assert "invalid verification code" in ctx["error"].lower()

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}._get_client_ip", return_value="10.0.0.1")
    @patch(f"{MODULE}._set_session_cookie")
    @patch(f"{MODULE}.get_csrf_cookie_name", return_value="csrf_token")
    @patch(f"{MODULE}.get_session_cookie_domain", return_value=".example.com")
    @patch(f"{MODULE}.settings")
    async def test_mfa_valid_otp_allows_login(
        self,
        mock_settings,
        mock_domain,
        mock_csrf_name,
        mock_set_cookie,
        mock_ip,
        mock_prefix,
        mock_tid,
    ):
        from auth.api.routes.auth.login import (
            MFA_LOGIN_CHALLENGE_COOKIE,
            _create_mfa_login_challenge,
            login_submit,
        )

        mock_settings.session_expiry_days = 7
        mock_settings.session_cookie_secure = True
        mock_settings.jwks_encryption_key = ""
        mock_settings.database_url = "postgresql://test"
        mock_settings.session_cookie_name = "session"

        user = make_user()
        challenge = _create_mfa_login_challenge(str(user.id), "test@example.com", "", None)
        request = _mock_request(cookies={MFA_LOGIN_CHALLENGE_COOKIE: challenge})
        db = AsyncMock()
        auth_svc = MagicMock()
        mfa_svc = MagicMock()
        mfa_svc.get_user_mfa = AsyncMock(return_value=MagicMock(totp_enabled=True))
        mfa_svc.verify_mfa_code_with_email = AsyncMock(return_value=True)
        session_svc = MagicMock()
        session_svc.create_session = AsyncMock(return_value=("sess_tok", "csrf_tok"))
        branding_svc = MagicMock()
        trust_svc = MagicMock()
        user_svc = MagicMock()
        user_svc.get_by_id = AsyncMock(return_value=user)

        result = await login_submit(
            request,
            "test@example.com",
            "password",
            "123456",
            "",
            db,
            auth_svc,
            mfa_svc,
            session_svc,
            branding_svc,
            trust_svc,
            user_service=user_svc,
        )

        assert result.status_code == 303
        mfa_svc.verify_mfa_code_with_email.assert_awaited_once()
        mock_set_cookie.assert_called_once()

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}._get_client_ip", return_value="10.0.0.1")
    async def test_mfa_send_email_code(self, mock_ip, mock_prefix, mock_tid):
        from auth.api.routes.auth.login import (
            MFA_LOGIN_CHALLENGE_COOKIE,
            _create_mfa_login_challenge,
            login_submit,
        )

        user = make_user()
        challenge = _create_mfa_login_challenge(str(user.id), "test@example.com", "", None)
        request = _mock_request(cookies={MFA_LOGIN_CHALLENGE_COOKIE: challenge})
        db = AsyncMock()
        auth_svc = MagicMock()
        auth_svc.get_user_primary_email = AsyncMock(return_value="test@example.com")
        mfa_svc = MagicMock()
        mfa_svc.send_mfa_email_code = AsyncMock(return_value="123456")
        session_svc = MagicMock()
        branding_svc = MagicMock()
        branding_svc.render_template = AsyncMock(return_value="<html>email sent</html>")
        branding_svc.get_branding = AsyncMock(return_value=MagicMock())
        trust_svc = MagicMock()
        email_svc = MagicMock()
        email_svc.send_email = AsyncMock(return_value=True)
        user_svc = MagicMock()
        user_svc.get_by_id = AsyncMock(return_value=user)

        with patch("auth.services.email_renderer.get_email_renderer") as mock_renderer:
            mock_renderer.return_value.render_email_for_tenant = AsyncMock(
                return_value=("<html>mfa code</html>", "mfa code")
            )
            result = await login_submit(
                request,
                "test@example.com",
                "password",
                None,
                "",
                db,
                auth_svc,
                mfa_svc,
                session_svc,
                branding_svc,
                trust_svc,
                email_svc,
                "1",
                user_service=user_svc,
            )

        assert result.status_code == 200
        mfa_svc.send_mfa_email_code.assert_awaited_once()
        email_svc.send_email.assert_awaited_once()
        ctx = branding_svc.render_template.call_args[0][2]
        assert ctx["mfa_required"] is True
        assert "verification code sent" in ctx["success"].lower()


# ---------------------------------------------------------------------------
# login_api
# ---------------------------------------------------------------------------


class TestLoginApi:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}._get_client_ip", return_value="10.0.0.1")
    @patch(f"{MODULE}._set_session_cookie")
    async def test_success(self, mock_set_cookie, mock_ip, mock_tid):
        from auth.api.routes.auth.login import LoginRequest, login_api

        user = make_user()
        request = _mock_request()
        db = AsyncMock()
        auth_svc = MagicMock()
        auth_svc.authenticate = AsyncMock(return_value=user)
        mfa_svc = MagicMock()
        mfa_svc.get_user_mfa = AsyncMock(return_value=None)
        session_svc = MagicMock()
        session_svc.create_session = AsyncMock(return_value=("sess_tok", "csrf_tok"))
        trust_svc = MagicMock()

        data = LoginRequest(email="test@example.com", password="password")
        result = await login_api(request, data, db, auth_svc, mfa_svc, session_svc, trust_svc)

        mock_set_cookie.assert_called_once()
        assert result is not None

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}._get_client_ip", return_value="10.0.0.1")
    async def test_invalid_credentials_raises(self, mock_ip, mock_tid):
        from auth.api.routes.auth.login import LoginRequest, login_api

        request = _mock_request()
        db = AsyncMock()
        auth_svc = MagicMock()
        auth_svc.authenticate = AsyncMock(return_value=None)
        mfa_svc = MagicMock()
        session_svc = MagicMock()
        trust_svc = MagicMock()

        data = LoginRequest(email="test@example.com", password="wrong")

        with pytest.raises(HTTPException) as exc_info:
            await login_api(request, data, db, auth_svc, mfa_svc, session_svc, trust_svc)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value="t-123")
    @patch(f"{MODULE}._get_client_ip", return_value="10.0.0.1")
    async def test_trust_policy_denied(self, mock_ip, mock_tid):
        from auth.api.routes.auth.login import LoginRequest, login_api

        user = make_user()
        request = _mock_request()
        db = AsyncMock()
        auth_svc = MagicMock()
        auth_svc.authenticate = AsyncMock(return_value=user)
        mfa_svc = MagicMock()
        mfa_svc.get_user_mfa = AsyncMock(return_value=None)
        session_svc = MagicMock()
        trust_svc = MagicMock()
        trust_svc.can_user_access_tenant = AsyncMock(return_value=(False, "Denied"))

        data = LoginRequest(email="test@example.com", password="password")

        with pytest.raises(HTTPException) as exc_info:
            await login_api(request, data, db, auth_svc, mfa_svc, session_svc, trust_svc)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}._get_client_ip", return_value="10.0.0.1")
    async def test_mfa_required_raises(self, mock_ip, mock_tid):
        from auth.api.routes.auth.login import LoginRequest, login_api

        user = make_user()
        request = _mock_request()
        db = AsyncMock()
        auth_svc = MagicMock()
        auth_svc.authenticate = AsyncMock(return_value=user)
        mfa_svc = MagicMock()
        mfa_svc.get_user_mfa = AsyncMock(return_value=MagicMock(totp_enabled=True))
        session_svc = MagicMock()
        trust_svc = MagicMock()

        data = LoginRequest(email="test@example.com", password="password")

        with pytest.raises(HTTPException) as exc_info:
            await login_api(request, data, db, auth_svc, mfa_svc, session_svc, trust_svc)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}._get_client_ip", return_value="10.0.0.1")
    async def test_mfa_invalid_otp_raises(self, mock_ip, mock_tid):
        from auth.api.routes.auth.login import LoginRequest, login_api

        user = make_user()
        request = _mock_request()
        db = AsyncMock()
        auth_svc = MagicMock()
        auth_svc.authenticate = AsyncMock(return_value=user)
        mfa_svc = MagicMock()
        mfa_svc.get_user_mfa = AsyncMock(return_value=MagicMock(totp_enabled=True))
        mfa_svc.verify_mfa_code_with_email = AsyncMock(return_value=False)
        session_svc = MagicMock()
        trust_svc = MagicMock()

        data = LoginRequest(email="test@example.com", password="password", otp="000000")

        with pytest.raises(HTTPException) as exc_info:
            await login_api(request, data, db, auth_svc, mfa_svc, session_svc, trust_svc)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}._get_client_ip", return_value="10.0.0.1")
    @patch(f"{MODULE}._set_session_cookie")
    async def test_mfa_valid_otp_success(self, mock_set_cookie, mock_ip, mock_tid):
        from auth.api.routes.auth.login import LoginRequest, login_api

        user = make_user()
        request = _mock_request()
        db = AsyncMock()
        auth_svc = MagicMock()
        auth_svc.authenticate = AsyncMock(return_value=user)
        mfa_svc = MagicMock()
        mfa_svc.get_user_mfa = AsyncMock(return_value=MagicMock(totp_enabled=True))
        mfa_svc.verify_mfa_code_with_email = AsyncMock(return_value=True)
        session_svc = MagicMock()
        session_svc.create_session = AsyncMock(return_value=("sess_tok", "csrf_tok"))
        trust_svc = MagicMock()

        data = LoginRequest(email="test@example.com", password="password", otp="123456")
        result = await login_api(request, data, db, auth_svc, mfa_svc, session_svc, trust_svc)

        assert result is not None
        mock_set_cookie.assert_called_once()


# ---------------------------------------------------------------------------
# MFA challenge cookie helpers
# ---------------------------------------------------------------------------


class TestMfaChallengeSecret:
    def test_prefers_the_jwks_encryption_key(self):
        from auth.api.routes.auth.login import _get_mfa_challenge_secret

        with patch(f"{MODULE}.settings") as mock_settings:
            mock_settings.jwks_encryption_key = "supersecret"

            assert _get_mfa_challenge_secret() == b"supersecret"

    def test_falls_back_to_database_url_and_cookie_name(self):
        from auth.api.routes.auth.login import _get_mfa_challenge_secret

        with patch(f"{MODULE}.settings") as mock_settings:
            mock_settings.jwks_encryption_key = None
            mock_settings.database_url = "postgresql://db"
            mock_settings.session_cookie_name = "session_id"

            assert _get_mfa_challenge_secret() == b"postgresql://dbsession_id"


class TestParseMfaLoginChallenge:
    def test_none_token(self):
        from auth.api.routes.auth.login import _parse_mfa_login_challenge

        assert _parse_mfa_login_challenge(None) is None

    def test_token_without_separator(self):
        from auth.api.routes.auth.login import _parse_mfa_login_challenge

        assert _parse_mfa_login_challenge("nodot") is None

    def test_tampered_signature(self):
        from auth.api.routes.auth.login import (
            _create_mfa_login_challenge,
            _parse_mfa_login_challenge,
        )

        token = _create_mfa_login_challenge("u1", "u@e.com", "", None)
        body, _sig = token.rsplit(".", 1)

        assert _parse_mfa_login_challenge(f"{body}.forged") is None

    def test_undecodable_body(self):
        import base64
        import hashlib
        import hmac

        from auth.api.routes.auth.login import (
            _get_mfa_challenge_secret,
            _parse_mfa_login_challenge,
        )

        body = base64.urlsafe_b64encode(b"not json").decode("ascii").rstrip("=")
        sig = hmac.new(_get_mfa_challenge_secret(), body.encode("ascii"), hashlib.sha256).digest()
        signature = base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")

        assert _parse_mfa_login_challenge(f"{body}.{signature}") is None

    def test_expired_challenge(self):
        from auth.api.routes.auth.login import (
            _create_mfa_login_challenge,
            _parse_mfa_login_challenge,
        )

        token = _create_mfa_login_challenge("u1", "u@e.com", "", None)

        with patch(f"{MODULE}.time.time", return_value=2**31):
            assert _parse_mfa_login_challenge(token) is None

    def test_valid_challenge_round_trips(self):
        from auth.api.routes.auth.login import (
            _create_mfa_login_challenge,
            _parse_mfa_login_challenge,
        )

        token = _create_mfa_login_challenge("u1", "u@e.com", "/next", "t1")
        payload = _parse_mfa_login_challenge(token)

        assert payload["uid"] == "u1"
        assert payload["email"] == "u@e.com"
        assert payload["next"] == "/next"
        assert payload["tenant_id"] == "t1"


class TestMaskEmail:
    def test_normal_email(self):
        from auth.api.routes.auth.login import _mask_email

        assert _mask_email("johndoe@example.com") == "j***e@example.com"

    def test_short_local_part(self):
        from auth.api.routes.auth.login import _mask_email

        assert _mask_email("jo@example.com") == "j***@example.com"

    def test_malformed_email(self):
        from auth.api.routes.auth.login import _mask_email

        assert _mask_email("not-an-email") == "***@***"


# ---------------------------------------------------------------------------
# login_form / login_submit remaining branches
# ---------------------------------------------------------------------------


class TestLoginFormStaleSession:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_unresolvable_cookie_renders_the_form(self, mock_cookie, mock_prefix, mock_tid):
        from auth.api.routes.auth.login import login_form

        session_svc = MagicMock()
        session_svc.get_user_by_session_token = AsyncMock(return_value=None)
        branding_svc = MagicMock()
        branding_svc.render_template = AsyncMock(return_value="<html>form</html>")

        result = await login_form(
            _mock_request(cookies={"session": "stale"}),
            AsyncMock(),
            session_svc,
            branding_svc,
        )

        assert result.status_code == 200


def _login_services(**overrides):
    """Build the service mocks ``login_submit`` needs, with sane defaults."""
    services = {
        "auth_svc": MagicMock(),
        "mfa_svc": MagicMock(),
        "session_svc": MagicMock(),
        "branding_svc": MagicMock(),
        "trust_svc": MagicMock(),
        "email_svc": MagicMock(),
        "user_svc": MagicMock(),
    }
    services["branding_svc"].render_template = AsyncMock(return_value="<html>x</html>")
    services.update(overrides)
    return services


async def _submit(
    request,
    services,
    *,
    email="test@example.com",
    password="password",
    otp=None,
    next_url="",
    send_email_code=None,
):
    from auth.api.routes.auth.login import login_submit

    return await login_submit(
        request,
        email,
        password,
        otp,
        next_url,
        AsyncMock(),
        services["auth_svc"],
        services["mfa_svc"],
        services["session_svc"],
        services["branding_svc"],
        services["trust_svc"],
        services["email_svc"],
        send_email_code,
        user_service=services["user_svc"],
    )


@patch(f"{MODULE}.get_current_tenant_id", return_value=None)
@patch(f"{MODULE}.get_tenant_prefix", return_value="")
@patch(f"{MODULE}._get_client_ip", return_value="10.0.0.1")
class TestLoginSubmitMfaChallengeErrors:
    @pytest.mark.asyncio
    async def test_missing_challenge_cookie(self, *_mocks):
        services = _login_services()

        result = await _submit(_mock_request(), services, otp="123456")

        assert result.status_code == 400
        ctx = services["branding_svc"].render_template.call_args[0][2]
        assert "MFA session expired" in ctx["error"]

    @pytest.mark.asyncio
    async def test_email_mismatch_against_challenge(self, *_mocks):
        from auth.api.routes.auth.login import (
            MFA_LOGIN_CHALLENGE_COOKIE,
            _create_mfa_login_challenge,
        )

        challenge = _create_mfa_login_challenge("u1", "owner@example.com", "", None)
        request = _mock_request(cookies={MFA_LOGIN_CHALLENGE_COOKIE: challenge})
        services = _login_services()

        result = await _submit(request, services, email="  attacker@example.com  ", otp="123456")

        assert result.status_code == 400
        ctx = services["branding_svc"].render_template.call_args[0][2]
        assert "MFA challenge mismatch" in ctx["error"]

    @pytest.mark.asyncio
    async def test_challenge_user_no_longer_exists(self, *_mocks):
        from auth.api.routes.auth.login import (
            MFA_LOGIN_CHALLENGE_COOKIE,
            _create_mfa_login_challenge,
        )

        user = make_user()
        challenge = _create_mfa_login_challenge(str(user.id), "u@e.com", "", None)
        request = _mock_request(cookies={MFA_LOGIN_CHALLENGE_COOKIE: challenge})
        services = _login_services()
        services["user_svc"].get_by_id = AsyncMock(return_value=None)

        result = await _submit(request, services, email="u@e.com", otp="123456")

        assert result.status_code == 401
        ctx = services["branding_svc"].render_template.call_args[0][2]
        assert "User not found" in ctx["error"]


@patch(f"{MODULE}.get_current_tenant_id", return_value=None)
@patch(f"{MODULE}.get_tenant_prefix", return_value="")
@patch(f"{MODULE}._get_client_ip", return_value="10.0.0.1")
class TestLoginSubmitEmailCodeFailures:
    def _challenged(self, email="u@e.com"):
        from auth.api.routes.auth.login import (
            MFA_LOGIN_CHALLENGE_COOKIE,
            _create_mfa_login_challenge,
        )

        user = make_user()
        challenge = _create_mfa_login_challenge(str(user.id), email, "", None)
        return user, _mock_request(cookies={MFA_LOGIN_CHALLENGE_COOKIE: challenge})

    @pytest.mark.asyncio
    async def test_no_email_available(self, *_mocks):
        user, request = self._challenged(email="")
        services = _login_services()
        services["user_svc"].get_by_id = AsyncMock(return_value=user)
        services["auth_svc"].get_user_primary_email = AsyncMock(return_value=None)

        result = await _submit(request, services, email="", send_email_code="1")

        assert result.status_code == 400
        ctx = services["branding_svc"].render_template.call_args[0][2]
        assert "No email available" in ctx["error"]

    @pytest.mark.asyncio
    async def test_code_generation_fails(self, *_mocks):
        user, request = self._challenged()
        services = _login_services()
        services["user_svc"].get_by_id = AsyncMock(return_value=user)
        services["auth_svc"].get_user_primary_email = AsyncMock(return_value="u@e.com")
        services["mfa_svc"].send_mfa_email_code = AsyncMock(return_value=None)

        result = await _submit(request, services, email="u@e.com", send_email_code="1")

        assert result.status_code == 500
        ctx = services["branding_svc"].render_template.call_args[0][2]
        assert "Failed to generate" in ctx["error"]

    @pytest.mark.asyncio
    async def test_email_delivery_fails(self, *_mocks):
        user, request = self._challenged()
        services = _login_services()
        services["user_svc"].get_by_id = AsyncMock(return_value=user)
        services["auth_svc"].get_user_primary_email = AsyncMock(return_value="u@e.com")
        services["mfa_svc"].send_mfa_email_code = AsyncMock(return_value="123456")
        services["branding_svc"].get_branding = AsyncMock(return_value=MagicMock())
        services["email_svc"].send_email = AsyncMock(return_value=False)

        with patch("auth.services.email_renderer.get_email_renderer") as mock_renderer:
            mock_renderer.return_value.render_email_for_tenant = AsyncMock(
                return_value=("<html>code</html>", "code")
            )
            result = await _submit(request, services, email="u@e.com", send_email_code="1")

        assert result.status_code == 500
        ctx = services["branding_svc"].render_template.call_args[0][2]
        assert "Failed to send MFA email" in ctx["error"]


@patch(f"{MODULE}.get_current_tenant_id", return_value=None)
@patch(f"{MODULE}.get_tenant_prefix", return_value="")
@patch(f"{MODULE}._get_client_ip", return_value="10.0.0.1")
class TestLoginSubmitMissingCredentials:
    @pytest.mark.asyncio
    async def test_blank_email_and_password(self, *_mocks):
        services = _login_services()

        result = await _submit(_mock_request(), services, email="   ", password="")

        assert result.status_code == 400
        ctx = services["branding_svc"].render_template.call_args[0][2]
        assert ctx["error"] == "Email and password are required"


@patch(f"{MODULE}.get_current_tenant_id", return_value="tenant-1")
@patch(f"{MODULE}.get_tenant_prefix", return_value="")
@patch(f"{MODULE}._get_client_ip", return_value="10.0.0.1")
@patch(f"{MODULE}._set_session_cookie")
@patch(f"{MODULE}.get_csrf_cookie_name", return_value="csrf_token")
@patch(f"{MODULE}.get_session_cookie_domain", return_value=".example.com")
@patch(f"{MODULE}.settings")
class TestLoginTrustPolicyAllows:
    @pytest.mark.asyncio
    async def test_form_login_proceeds_when_trust_allows(self, mock_settings, *_mocks):
        mock_settings.session_expiry_days = 7
        mock_settings.session_cookie_secure = True

        services = _login_services()
        services["auth_svc"].authenticate = AsyncMock(return_value=make_user())
        services["mfa_svc"].get_user_mfa = AsyncMock(return_value=None)
        services["session_svc"].create_session = AsyncMock(return_value=("s", "c"))
        services["trust_svc"].can_user_access_tenant = AsyncMock(return_value=(True, None))

        result = await _submit(_mock_request(), services)

        assert result.status_code == 303
        services["trust_svc"].can_user_access_tenant.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_api_login_proceeds_when_trust_allows(self, mock_settings, *_mocks):
        from auth.api.routes.auth.login import login_api
        from auth.api.schemas.auth import LoginRequest

        mock_settings.session_expiry_days = 7
        mock_settings.session_cookie_secure = True

        auth_svc = MagicMock()
        auth_svc.authenticate = AsyncMock(return_value=make_user())
        mfa_svc = MagicMock()
        mfa_svc.get_user_mfa = AsyncMock(return_value=None)
        session_svc = MagicMock()
        session_svc.create_session = AsyncMock(return_value=("s", "c"))
        trust_svc = MagicMock()
        trust_svc.can_user_access_tenant = AsyncMock(return_value=(True, None))

        result = await login_api(
            _mock_request(),
            LoginRequest(email="test@example.com", password="password"),
            AsyncMock(),
            auth_svc,
            mfa_svc,
            session_svc,
            trust_svc,
        )

        assert result is not None
        trust_svc.can_user_access_tenant.assert_awaited_once()


@patch(f"{MODULE}.get_current_tenant_id", return_value=None)
@patch(f"{MODULE}.get_tenant_prefix", return_value="")
@patch(f"{MODULE}._get_client_ip", return_value="10.0.0.1")
@patch(f"{MODULE}._set_session_cookie")
@patch(f"{MODULE}.get_csrf_cookie_name", return_value="csrf_token")
@patch(f"{MODULE}.get_session_cookie_domain", return_value=".example.com")
@patch(f"{MODULE}.settings")
class TestLoginNextUrlRejection:
    @pytest.mark.asyncio
    async def test_absolute_url_on_another_host_is_ignored(self, mock_settings, *_mocks):
        mock_settings.session_expiry_days = 7
        mock_settings.session_cookie_secure = True

        services = _login_services()
        services["auth_svc"].authenticate = AsyncMock(return_value=make_user())
        services["mfa_svc"].get_user_mfa = AsyncMock(return_value=None)
        services["session_svc"].create_session = AsyncMock(return_value=("s", "c"))

        result = await _submit(_mock_request(), services, next_url="https://evil.example.net/steal")

        assert result.status_code == 303
        assert "evil.example.net" not in result.headers["location"]
