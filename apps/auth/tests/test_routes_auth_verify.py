# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.api.routes.auth.verify — Email verification endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from tests.conftest import make_user

MODULE = "auth.api.routes.auth.verify"


def _mock_request(cookies=None, headers=None, url="https://auth.example.com/verify"):
    request = MagicMock()
    request.cookies = cookies or {}
    request.headers = MagicMock()
    request.headers.get = MagicMock(side_effect=lambda k, d=None: (headers or {}).get(k, d))
    request.base_url = "https://auth.example.com/"
    request.url = MagicMock()
    request.url.__str__ = MagicMock(return_value=url)
    return request


# ---------------------------------------------------------------------------
# Helpers: get_tenant_prefix / get_current_tenant_id
# ---------------------------------------------------------------------------


class TestGetTenantPrefix:
    @patch(f"{MODULE}.get_tenant_context", return_value=None)
    def test_no_context(self, _):
        from auth.api.routes.auth.verify import get_tenant_prefix

        assert get_tenant_prefix() == ""

    @patch(f"{MODULE}.get_tenant_context")
    def test_path_resolution(self, mock_ctx):
        from auth.api.routes.auth.verify import get_tenant_prefix

        ctx = MagicMock()
        ctx.tenant_slug = "acme"
        ctx.resolution_method = "path"
        mock_ctx.return_value = ctx
        assert get_tenant_prefix() == "/t/acme"


class TestGetCurrentTenantId:
    @patch(f"{MODULE}.get_tenant_context", return_value=None)
    def test_no_context(self, _):
        from auth.api.routes.auth.verify import get_current_tenant_id

        assert get_current_tenant_id() is None

    @patch(f"{MODULE}.get_tenant_context")
    def test_with_context(self, mock_ctx):
        from auth.api.routes.auth.verify import get_current_tenant_id

        ctx = MagicMock()
        ctx.tenant_id = "t-456"
        mock_ctx.return_value = ctx
        assert get_current_tenant_id() == "t-456"


# ---------------------------------------------------------------------------
# verify_email_form
# ---------------------------------------------------------------------------


class TestVerifyEmailForm:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    async def test_renders_form(self, _pfx, _tid):
        from auth.api.routes.auth.verify import verify_email_form

        request = _mock_request()
        db = AsyncMock()
        branding = AsyncMock()
        branding.render_template = AsyncMock(return_value="<html>verify</html>")

        result = await verify_email_form(request, db, branding, email="a@b.com", next="/next")

        assert result.status_code == 200
        assert result.body == b"<html>verify</html>"
        branding.render_template.assert_awaited_once()
        call_args = branding.render_template.call_args
        ctx = call_args[0][2]
        assert ctx["email"] == "a@b.com"
        assert ctx["next"] == "/next"


# ---------------------------------------------------------------------------
# verify_email_submit
# ---------------------------------------------------------------------------


class TestVerifyEmailSubmit:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    async def test_success(self, _pfx, _tid):
        from auth.api.routes.auth.verify import verify_email_submit

        request = _mock_request()
        db = AsyncMock()
        email_service = AsyncMock()
        email_service.verify_code = AsyncMock(return_value=True)
        branding = AsyncMock()

        result = await verify_email_submit(
            request, "a@b.com", "123456", "", db, email_service, branding
        )

        assert result.status_code == 303
        assert "/auth/login" in result.headers.get("location", "")
        assert "verified=1" in result.headers.get("location", "")

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    async def test_success_with_next(self, _pfx, _tid):
        from auth.api.routes.auth.verify import verify_email_submit

        request = _mock_request()
        db = AsyncMock()
        email_service = AsyncMock()
        email_service.verify_code = AsyncMock(return_value=True)
        branding = AsyncMock()

        result = await verify_email_submit(
            request, "a@b.com", "123456", "/dashboard", db, email_service, branding
        )

        location = result.headers.get("location", "")
        assert "verified=1" in location
        assert "next=" in location

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    async def test_invalid_code(self, _pfx, _tid):
        from auth.api.routes.auth.verify import verify_email_submit

        request = _mock_request()
        db = AsyncMock()
        email_service = AsyncMock()
        email_service.verify_code = AsyncMock(return_value=False)
        branding = AsyncMock()
        branding.render_template = AsyncMock(return_value="<html>error</html>")

        result = await verify_email_submit(
            request, "a@b.com", "wrong", "", db, email_service, branding
        )

        assert result.status_code == 400
        call_ctx = branding.render_template.call_args[0][2]
        assert "Invalid or expired" in call_ctx["error"]

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="/t/acme")
    async def test_success_with_tenant_prefix(self, _pfx, _tid):
        from auth.api.routes.auth.verify import verify_email_submit

        request = _mock_request()
        db = AsyncMock()
        email_service = AsyncMock()
        email_service.verify_code = AsyncMock(return_value=True)
        branding = AsyncMock()

        result = await verify_email_submit(
            request, "a@b.com", "123456", "", db, email_service, branding
        )

        location = result.headers.get("location", "")
        assert location.startswith("/t/acme/auth/login")


# ---------------------------------------------------------------------------
# verify_email_api
# ---------------------------------------------------------------------------


class TestVerifyEmailApi:
    @pytest.mark.asyncio
    async def test_success(self):
        from auth.api.routes.auth.verify import VerifyEmailRequest, verify_email_api

        db = AsyncMock()
        email_service = AsyncMock()
        email_service.verify_code = AsyncMock(return_value=True)

        data = VerifyEmailRequest(email="a@b.com", code="123456")
        result = await verify_email_api(data, db, email_service)

        assert result.message == "Email verified successfully"

    @pytest.mark.asyncio
    async def test_invalid_code(self):
        from auth.api.routes.auth.verify import VerifyEmailRequest, verify_email_api

        db = AsyncMock()
        email_service = AsyncMock()
        email_service.verify_code = AsyncMock(return_value=False)

        data = VerifyEmailRequest(email="a@b.com", code="wrong")
        with pytest.raises(HTTPException) as exc:
            await verify_email_api(data, db, email_service)
        assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# resend_verification_submit
# ---------------------------------------------------------------------------


class TestResendVerificationSubmit:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    async def test_user_found(self, _pfx, _tid):
        from auth.api.routes.auth.verify import resend_verification_submit

        request = _mock_request()
        db = AsyncMock()
        user = make_user()
        user_service = AsyncMock()
        user_service.get_by_email = AsyncMock(return_value=user)
        email_service = AsyncMock()
        email_service.send_verification_email = AsyncMock()
        branding = AsyncMock()
        branding.render_template = AsyncMock(return_value="<html>ok</html>")

        result = await resend_verification_submit(
            request, "a@b.com", "", db, user_service, email_service, branding
        )

        assert result.status_code == 200
        email_service.send_verification_email.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    async def test_user_not_found_still_returns_success(self, _pfx, _tid):
        from auth.api.routes.auth.verify import resend_verification_submit

        request = _mock_request()
        db = AsyncMock()
        user_service = AsyncMock()
        user_service.get_by_email = AsyncMock(return_value=None)
        email_service = AsyncMock()
        branding = AsyncMock()
        branding.render_template = AsyncMock(return_value="<html>ok</html>")

        result = await resend_verification_submit(
            request, "a@b.com", "", db, user_service, email_service, branding
        )

        assert result.status_code == 200
        email_service.send_verification_email.assert_not_awaited()

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value="tid-1")
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    async def test_with_tenant_id(self, _pfx, _tid):
        from auth.api.routes.auth.verify import resend_verification_submit

        request = _mock_request()
        db = AsyncMock()
        user = make_user()
        user_service = AsyncMock()
        user_service.get_by_email = AsyncMock(return_value=user)
        email_service = AsyncMock()
        email_service.send_verification_email = AsyncMock()
        branding = AsyncMock()
        branding.render_template = AsyncMock(return_value="<html>ok</html>")

        await resend_verification_submit(
            request, "a@b.com", "", db, user_service, email_service, branding
        )

        call_kwargs = email_service.send_verification_email.call_args
        assert call_kwargs[1]["tenant_id"] == "tid-1"


# ---------------------------------------------------------------------------
# resend_verification_api
# ---------------------------------------------------------------------------


class TestResendVerificationApi:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.settings")
    async def test_user_found(self, mock_settings, _tid):
        from auth.api.routes.auth.verify import ResendVerificationRequest, resend_verification_api

        mock_settings.issuer = "https://auth.example.com"
        db = AsyncMock()
        user = make_user()
        user_service = AsyncMock()
        user_service.get_by_email = AsyncMock(return_value=user)
        email_service = AsyncMock()
        email_service.send_verification_email = AsyncMock()

        data = ResendVerificationRequest(email="a@b.com")
        result = await resend_verification_api(data, db, user_service, email_service)

        assert "verification code has been sent" in result.message
        email_service.send_verification_email.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    async def test_user_not_found_still_returns_success(self, _tid):
        from auth.api.routes.auth.verify import ResendVerificationRequest, resend_verification_api

        db = AsyncMock()
        user_service = AsyncMock()
        user_service.get_by_email = AsyncMock(return_value=None)
        email_service = AsyncMock()

        data = ResendVerificationRequest(email="a@b.com")
        result = await resend_verification_api(data, db, user_service, email_service)

        assert "verification code has been sent" in result.message
        email_service.send_verification_email.assert_not_awaited()

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value="tid-1")
    @patch(f"{MODULE}.settings")
    async def test_with_tenant_id(self, mock_settings, _tid):
        from auth.api.routes.auth.verify import ResendVerificationRequest, resend_verification_api

        mock_settings.issuer = "https://auth.example.com"
        db = AsyncMock()
        user = make_user()
        user_service = AsyncMock()
        user_service.get_by_email = AsyncMock(return_value=user)
        email_service = AsyncMock()
        email_service.send_verification_email = AsyncMock()

        data = ResendVerificationRequest(email="a@b.com")
        await resend_verification_api(data, db, user_service, email_service)

        call_kwargs = email_service.send_verification_email.call_args
        assert call_kwargs[1]["tenant_id"] == "tid-1"
