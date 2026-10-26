# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.api.routes.auth.password — Password reset endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

MODULE = "auth.api.routes.auth.password"


def _mock_request(url="https://auth.example.com/auth/forgot-password"):
    request = MagicMock()
    request.cookies = {}
    request.headers = MagicMock()
    request.headers.get = MagicMock(side_effect=lambda k, d=None: {}.get(k, d))
    request.base_url = "https://auth.example.com/"
    request.url = MagicMock()
    request.url.__str__ = MagicMock(return_value=url)
    return request


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TestForgotPasswordRequest:
    def test_valid(self):
        from auth.api.routes.auth.password import ForgotPasswordRequest

        r = ForgotPasswordRequest(email="a@b.com")
        assert r.email == "a@b.com"
        assert r.reset_base_url is None

    def test_with_reset_base_url(self):
        from auth.api.routes.auth.password import ForgotPasswordRequest

        r = ForgotPasswordRequest(email="a@b.com", reset_base_url="https://app.example.com/")
        assert r.reset_base_url == "https://app.example.com"  # trailing slash stripped

    def test_reset_base_url_invalid_scheme(self):
        from auth.api.routes.auth.password import ForgotPasswordRequest

        with pytest.raises(ValidationError):
            ForgotPasswordRequest(email="a@b.com", reset_base_url="ftp://bad.com")

    def test_reset_base_url_too_long(self):
        from auth.api.routes.auth.password import ForgotPasswordRequest

        with pytest.raises(ValidationError):
            ForgotPasswordRequest(email="a@b.com", reset_base_url="https://x.com/" + "a" * 500)

    def test_reset_base_url_empty_string(self):
        from auth.api.routes.auth.password import ForgotPasswordRequest

        r = ForgotPasswordRequest(email="a@b.com", reset_base_url="  ")
        assert r.reset_base_url is None

    def test_reset_base_url_none(self):
        from auth.api.routes.auth.password import ForgotPasswordRequest

        r = ForgotPasswordRequest(email="a@b.com", reset_base_url=None)
        assert r.reset_base_url is None


class TestResetPasswordRequest:
    def test_valid(self):
        from auth.api.routes.auth.password import ResetPasswordRequest

        r = ResetPasswordRequest(token="abc", password="Str0ngPwd!")
        assert r.token == "abc"

    def test_short_password(self):
        from auth.api.routes.auth.password import ResetPasswordRequest

        with pytest.raises(ValidationError, match="at least 8"):
            ResetPasswordRequest(token="abc", password="Sh1!")

    def test_no_uppercase(self):
        from auth.api.routes.auth.password import ResetPasswordRequest

        with pytest.raises(ValidationError, match="uppercase"):
            ResetPasswordRequest(token="abc", password="nouppercase1!")

    def test_no_lowercase(self):
        from auth.api.routes.auth.password import ResetPasswordRequest

        with pytest.raises(ValidationError, match="lowercase"):
            ResetPasswordRequest(token="abc", password="NOLOWER1!!")

    def test_no_digit(self):
        from auth.api.routes.auth.password import ResetPasswordRequest

        with pytest.raises(ValidationError, match="digit"):
            ResetPasswordRequest(token="abc", password="NoDigitHere!")


# ---------------------------------------------------------------------------
# Helpers: get_tenant_prefix / get_current_tenant_id
# ---------------------------------------------------------------------------


class TestGetTenantPrefix:
    @patch(f"{MODULE}.get_tenant_context", return_value=None)
    def test_no_context(self, _):
        from auth.api.routes.auth.password import get_tenant_prefix

        assert get_tenant_prefix() == ""

    @patch(f"{MODULE}.get_tenant_context")
    def test_path_resolution(self, mock_ctx):
        from auth.api.routes.auth.password import get_tenant_prefix

        ctx = MagicMock()
        ctx.tenant_slug = "acme"
        ctx.resolution_method = "path"
        mock_ctx.return_value = ctx
        assert get_tenant_prefix() == "/t/acme"


# ---------------------------------------------------------------------------
# forgot_password_form
# ---------------------------------------------------------------------------


class TestForgotPasswordForm:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    async def test_renders_form(self, _pfx, _tid):
        from auth.api.routes.auth.password import forgot_password_form

        request = _mock_request()
        db = AsyncMock()
        branding = AsyncMock()
        branding.render_template = AsyncMock(return_value="<html>forgot</html>")

        result = await forgot_password_form(request, db, branding)

        assert result.status_code == 200
        assert result.body == b"<html>forgot</html>"


# ---------------------------------------------------------------------------
# forgot_password_submit
# ---------------------------------------------------------------------------


class TestForgotPasswordSubmit:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_email_renderer")
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.settings")
    async def test_user_found(self, mock_settings, _pfx, _tid, mock_get_renderer):
        from auth.api.routes.auth.password import forgot_password_submit

        mock_settings.issuer = "https://auth.example.com"
        mock_settings.password_reset_expiry_hours = 24

        request = _mock_request()
        db = AsyncMock()
        password_service = AsyncMock()
        password_service.create_reset_token = AsyncMock(return_value=("reset-tok", "uid-1"))
        email_service = AsyncMock()
        email_service.send_email = AsyncMock()
        branding = AsyncMock()
        branding.render_template = AsyncMock(return_value="<html>sent</html>")
        branding.get_branding = AsyncMock(return_value=MagicMock())

        renderer = AsyncMock()
        renderer.render_email_for_tenant = AsyncMock(return_value=("<html>email</html>", "text"))
        mock_get_renderer.return_value = renderer

        result = await forgot_password_submit(
            request, "a@b.com", db, password_service, email_service, branding
        )

        assert result.status_code == 200
        email_service.send_email.assert_awaited_once()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.settings")
    async def test_user_not_found_still_returns_success(self, mock_settings, _pfx, _tid):
        from auth.api.routes.auth.password import forgot_password_submit

        mock_settings.issuer = "https://auth.example.com"

        request = _mock_request()
        db = AsyncMock()
        password_service = AsyncMock()
        password_service.create_reset_token = AsyncMock(return_value=None)
        email_service = AsyncMock()
        branding = AsyncMock()
        branding.render_template = AsyncMock(return_value="<html>sent</html>")

        result = await forgot_password_submit(
            request, "a@b.com", db, password_service, email_service, branding
        )

        assert result.status_code == 200
        email_service.send_email.assert_not_awaited()


# ---------------------------------------------------------------------------
# forgot_password_api
# ---------------------------------------------------------------------------


class TestForgotPasswordApi:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_email_renderer")
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.settings")
    async def test_user_found(self, mock_settings, _tid, mock_get_renderer):
        from auth.api.routes.auth.password import ForgotPasswordRequest, forgot_password_api

        mock_settings.issuer = "https://auth.example.com"
        mock_settings.password_reset_expiry_hours = 24

        request = _mock_request()
        db = AsyncMock()
        password_service = AsyncMock()
        password_service.create_reset_token = AsyncMock(return_value=("reset-tok", "uid-1"))
        email_service = AsyncMock()
        email_service.send_email = AsyncMock()
        branding = AsyncMock()
        branding.get_branding = AsyncMock(return_value=MagicMock())

        renderer = AsyncMock()
        renderer.render_email_for_tenant = AsyncMock(return_value=("<html>email</html>", "text"))
        mock_get_renderer.return_value = renderer

        data = ForgotPasswordRequest(email="a@b.com")
        result = await forgot_password_api(
            request, data, db, password_service, email_service, branding
        )

        assert "password reset link" in result.message
        email_service.send_email.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_email_renderer")
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.settings")
    async def test_with_custom_reset_base_url(self, mock_settings, _tid, mock_get_renderer):
        from auth.api.routes.auth.password import ForgotPasswordRequest, forgot_password_api

        mock_settings.issuer = "https://auth.example.com"
        mock_settings.password_reset_expiry_hours = 24

        request = _mock_request()
        db = AsyncMock()
        password_service = AsyncMock()
        password_service.create_reset_token = AsyncMock(return_value=("reset-tok", "uid-1"))
        email_service = AsyncMock()
        email_service.send_email = AsyncMock()
        branding = AsyncMock()
        branding.get_branding = AsyncMock(return_value=MagicMock())

        renderer = AsyncMock()
        renderer.render_email_for_tenant = AsyncMock(return_value=("<html>email</html>", "text"))
        mock_get_renderer.return_value = renderer

        data = ForgotPasswordRequest(email="a@b.com", reset_base_url="https://custom.app.com")
        result = await forgot_password_api(
            request, data, db, password_service, email_service, branding
        )

        assert "password reset link" in result.message
        # Verify the reset URL uses the custom base
        render_call = renderer.render_email_for_tenant.call_args
        ctx = render_call[0][2]
        assert ctx["reset_url"].startswith("https://custom.app.com/auth/reset-password")

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.settings")
    async def test_user_not_found(self, mock_settings, _tid):
        from auth.api.routes.auth.password import ForgotPasswordRequest, forgot_password_api

        mock_settings.issuer = "https://auth.example.com"

        request = _mock_request()
        db = AsyncMock()
        password_service = AsyncMock()
        password_service.create_reset_token = AsyncMock(return_value=None)
        email_service = AsyncMock()
        branding = AsyncMock()

        data = ForgotPasswordRequest(email="a@b.com")
        result = await forgot_password_api(
            request, data, db, password_service, email_service, branding
        )

        assert "password reset link" in result.message
        email_service.send_email.assert_not_awaited()


# ---------------------------------------------------------------------------
# reset_password_form
# ---------------------------------------------------------------------------


class TestResetPasswordForm:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    async def test_no_token(self, _pfx, _tid):
        from auth.api.routes.auth.password import reset_password_form

        request = _mock_request()
        db = AsyncMock()
        password_service = AsyncMock()
        branding = AsyncMock()
        branding.render_template = AsyncMock(return_value="<html>error</html>")

        result = await reset_password_form(request, "", db, password_service, branding)

        assert result.status_code == 400
        ctx = branding.render_template.call_args[0][2]
        assert ctx["valid_token"] is False

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    async def test_invalid_token(self, _pfx, _tid):
        from auth.api.routes.auth.password import reset_password_form

        request = _mock_request()
        db = AsyncMock()
        password_service = AsyncMock()
        password_service.verify_reset_token = AsyncMock(return_value=None)
        branding = AsyncMock()
        branding.render_template = AsyncMock(return_value="<html>error</html>")

        result = await reset_password_form(request, "bad-token", db, password_service, branding)

        assert result.status_code == 400
        ctx = branding.render_template.call_args[0][2]
        assert ctx["valid_token"] is False

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    async def test_valid_token(self, _pfx, _tid):
        from auth.api.routes.auth.password import reset_password_form

        request = _mock_request()
        db = AsyncMock()
        password_service = AsyncMock()
        password_service.verify_reset_token = AsyncMock(return_value=MagicMock())
        branding = AsyncMock()
        branding.render_template = AsyncMock(return_value="<html>form</html>")

        result = await reset_password_form(request, "good-token", db, password_service, branding)

        assert result.status_code == 200
        ctx = branding.render_template.call_args[0][2]
        assert ctx["valid_token"] is True


# ---------------------------------------------------------------------------
# reset_password_submit
# ---------------------------------------------------------------------------


class TestResetPasswordSubmit:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    async def test_passwords_dont_match(self, _pfx, _tid):
        from auth.api.routes.auth.password import reset_password_submit

        request = _mock_request()
        db = AsyncMock()
        password_service = AsyncMock()
        branding = AsyncMock()
        branding.render_template = AsyncMock(return_value="<html>err</html>")

        result = await reset_password_submit(
            request, "tok", "Str0ngPwd!", "Different1!", db, password_service, branding
        )

        assert result.status_code == 400
        ctx = branding.render_template.call_args[0][2]
        assert "do not match" in ctx["error"]

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    async def test_weak_password(self, _pfx, _tid):
        from auth.api.routes.auth.password import reset_password_submit

        request = _mock_request()
        db = AsyncMock()
        password_service = AsyncMock()
        branding = AsyncMock()
        branding.render_template = AsyncMock(return_value="<html>err</html>")

        result = await reset_password_submit(
            request, "tok", "weak", "weak", db, password_service, branding
        )

        assert result.status_code == 400

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    async def test_success(self, _pfx, _tid):
        from auth.api.routes.auth.password import reset_password_submit

        request = _mock_request()
        db = AsyncMock()
        password_service = AsyncMock()
        password_service.reset_password = AsyncMock(return_value=True)
        branding = AsyncMock()

        result = await reset_password_submit(
            request, "tok", "Str0ngPwd!", "Str0ngPwd!", db, password_service, branding
        )

        assert result.status_code == 303
        assert "/auth/login?reset=1" in result.headers.get("location", "")

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    async def test_invalid_token(self, _pfx, _tid):
        from auth.api.routes.auth.password import reset_password_submit

        request = _mock_request()
        db = AsyncMock()
        password_service = AsyncMock()
        password_service.reset_password = AsyncMock(return_value=False)
        branding = AsyncMock()
        branding.render_template = AsyncMock(return_value="<html>err</html>")

        result = await reset_password_submit(
            request, "tok", "Str0ngPwd!", "Str0ngPwd!", db, password_service, branding
        )

        assert result.status_code == 400
        ctx = branding.render_template.call_args[0][2]
        assert "expired" in ctx["error"]

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="/t/acme")
    async def test_success_with_tenant_prefix(self, _pfx, _tid):
        from auth.api.routes.auth.password import reset_password_submit

        request = _mock_request()
        db = AsyncMock()
        password_service = AsyncMock()
        password_service.reset_password = AsyncMock(return_value=True)
        branding = AsyncMock()

        result = await reset_password_submit(
            request, "tok", "Str0ngPwd!", "Str0ngPwd!", db, password_service, branding
        )

        location = result.headers.get("location", "")
        assert location.startswith("/t/acme/auth/login")


# ---------------------------------------------------------------------------
# reset_password_api
# ---------------------------------------------------------------------------


class TestResetPasswordApi:
    @pytest.mark.asyncio
    async def test_success(self):
        from auth.api.routes.auth.password import ResetPasswordRequest, reset_password_api

        db = AsyncMock()
        password_service = AsyncMock()
        password_service.reset_password = AsyncMock(return_value=True)

        data = ResetPasswordRequest(token="tok", password="Str0ngPwd!")
        result = await reset_password_api(data, db, password_service)

        assert result.message == "Password reset successfully"

    @pytest.mark.asyncio
    async def test_invalid_token(self):
        from auth.api.routes.auth.password import ResetPasswordRequest, reset_password_api

        db = AsyncMock()
        password_service = AsyncMock()
        password_service.reset_password = AsyncMock(return_value=False)

        data = ResetPasswordRequest(token="tok", password="Str0ngPwd!")
        with pytest.raises(HTTPException) as exc:
            await reset_password_api(data, db, password_service)
        assert exc.value.status_code == 400


class TestResetPasswordSubmitNonPasswordValidationError:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    async def test_error_without_password_prefix_is_shown_verbatim(self, _pfx, _tid):
        """A validation error not phrased as "Password must ..." is rendered as-is."""
        from auth.api.routes.auth.password import reset_password_submit

        branding = AsyncMock()
        branding.render_template = AsyncMock(return_value="<html>err</html>")

        with patch(f"{MODULE}.ResetPasswordRequest", side_effect=ValueError("Token is required")):
            result = await reset_password_submit(
                _mock_request(),
                "tok",
                "P@ssw0rd!",
                "P@ssw0rd!",
                AsyncMock(),
                AsyncMock(),
                branding,
            )

        assert result.status_code == 400
        assert branding.render_template.await_args[0][2]["error"] == "Token is required"
