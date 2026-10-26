# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.api.routes.oauth2.device -- OAuth2 Device Authorization endpoint (RFC 8628)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from tests.conftest import make_device_code, make_oauth2_client, make_session

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MODULE = "auth.api.routes.oauth2.device"


def _mock_request(
    cookies=None,
    headers=None,
    url_path="/oauth2/device",
    url_query="",
    base_url="https://auth.example.com/",
):
    request = MagicMock()
    request.cookies = cookies or {}
    request.headers = MagicMock()
    request.headers.get = MagicMock(side_effect=lambda k, d=None: (headers or {}).get(k, d))
    request.client = MagicMock()
    request.client.host = "10.0.0.1"
    request.url = MagicMock()
    request.url.scheme = "https"
    request.url.netloc = "auth.example.com"
    request.url.path = url_path
    request.url.query = url_query
    request.base_url = "https://auth.example.com/"
    return request


# ---------------------------------------------------------------------------
# get_tenant_prefix / get_current_tenant_id
# ---------------------------------------------------------------------------


class TestGetTenantPrefix:
    @patch(f"{MODULE}.get_tenant_context", return_value=None)
    def test_no_context(self, _):
        from auth.api.routes.oauth2.device import get_tenant_prefix

        assert get_tenant_prefix() == ""

    @patch(f"{MODULE}.get_tenant_context")
    def test_path_resolution(self, mock_ctx):
        from auth.api.routes.oauth2.device import get_tenant_prefix

        ctx = MagicMock()
        ctx.tenant_slug = "acme"
        ctx.resolution_method = "path"
        mock_ctx.return_value = ctx
        assert get_tenant_prefix() == "/t/acme"

    @patch(f"{MODULE}.get_tenant_context")
    def test_non_path_resolution(self, mock_ctx):
        from auth.api.routes.oauth2.device import get_tenant_prefix

        ctx = MagicMock()
        ctx.tenant_slug = "acme"
        ctx.resolution_method = "subdomain"
        mock_ctx.return_value = ctx
        assert get_tenant_prefix() == ""


class TestGetCurrentTenantId:
    @patch(f"{MODULE}.get_tenant_context", return_value=None)
    def test_no_context(self, _):
        from auth.api.routes.oauth2.device import get_current_tenant_id

        assert get_current_tenant_id() is None

    @patch(f"{MODULE}.get_tenant_context")
    def test_with_context(self, mock_ctx):
        from auth.api.routes.oauth2.device import get_current_tenant_id

        ctx = MagicMock()
        ctx.tenant_id = "t-42"
        mock_ctx.return_value = ctx
        assert get_current_tenant_id() == "t-42"


# ---------------------------------------------------------------------------
# _device_error
# ---------------------------------------------------------------------------


class TestDeviceError:
    def test_creates_http_exception(self):
        from auth.api.routes.oauth2.device import _device_error

        exc = _device_error("invalid_client", "Bad client")
        assert isinstance(exc, HTTPException)
        assert exc.status_code == 400
        assert exc.detail["error"] == "invalid_client"
        assert exc.detail["error_description"] == "Bad client"


# ---------------------------------------------------------------------------
# device_authorization (POST /device)
# ---------------------------------------------------------------------------


class TestDeviceAuthorization:
    @pytest.mark.asyncio
    async def test_invalid_client(self):
        from auth.api.routes.oauth2.device import device_authorization

        db = AsyncMock()
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=None)
        device_svc = AsyncMock()
        request = _mock_request()

        with pytest.raises(HTTPException) as exc_info:
            await device_authorization(
                request=request,
                client_id="unknown",
                db=db,
                oauth2_service=oauth2_svc,
                device_service=device_svc,
                scope=None,
            )
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["error"] == "invalid_client"

    @pytest.mark.asyncio
    async def test_inactive_client(self):
        from auth.api.routes.oauth2.device import device_authorization

        db = AsyncMock()
        client = make_oauth2_client()
        client.is_active = False
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        device_svc = AsyncMock()
        request = _mock_request()

        with pytest.raises(HTTPException) as exc_info:
            await device_authorization(
                request=request,
                client_id="test_client_id",
                db=db,
                oauth2_service=oauth2_svc,
                device_service=device_svc,
                scope=None,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_unauthorized_grant_type(self):
        from auth.api.routes.oauth2.device import device_authorization

        db = AsyncMock()
        client = make_oauth2_client()
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_grant_type = MagicMock(return_value=False)
        device_svc = AsyncMock()
        request = _mock_request()

        with pytest.raises(HTTPException) as exc_info:
            await device_authorization(
                request=request,
                client_id="test_client_id",
                db=db,
                oauth2_service=oauth2_svc,
                device_service=device_svc,
                scope=None,
            )
        assert exc_info.value.detail["error"] == "unauthorized_client"

    @pytest.mark.asyncio
    async def test_invalid_scope(self):
        from auth.api.routes.oauth2.device import device_authorization

        db = AsyncMock()
        client = make_oauth2_client()
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_grant_type = MagicMock(return_value=True)
        oauth2_svc.validate_scopes = MagicMock(return_value=False)
        device_svc = AsyncMock()
        request = _mock_request()

        with pytest.raises(HTTPException) as exc_info:
            await device_authorization(
                request=request,
                client_id="test_client_id",
                db=db,
                oauth2_service=oauth2_svc,
                device_service=device_svc,
                scope="bad_scope",
            )
        assert exc_info.value.detail["error"] == "invalid_scope"

    @pytest.mark.asyncio
    @patch(f"{MODULE}.settings")
    async def test_success(self, mock_settings):
        from auth.api.routes.oauth2.device import device_authorization

        mock_settings.device_code_expiry_minutes = 15

        db = AsyncMock()
        client = make_oauth2_client()
        client.is_active = True
        client.allowed_scopes = ["openid", "profile"]
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_grant_type = MagicMock(return_value=True)

        device_mock = MagicMock()
        device_mock.user_code = "ABCD-EFGH"
        device_mock.interval = 5

        device_svc = AsyncMock()
        device_svc.create_device_authorization = AsyncMock(
            return_value=("device_code_123", device_mock)
        )

        request = _mock_request()

        result = await device_authorization(
            request=request,
            client_id="test_client_id",
            db=db,
            oauth2_service=oauth2_svc,
            device_service=device_svc,
            scope=None,
        )

        assert result.device_code == "device_code_123"
        assert result.user_code == "ABCD-EFGH"
        assert result.expires_in == 900
        assert result.interval == 5
        assert "device/verify" in result.verification_uri

    @pytest.mark.asyncio
    @patch(f"{MODULE}.settings")
    async def test_success_with_scopes(self, mock_settings):
        from auth.api.routes.oauth2.device import device_authorization

        mock_settings.device_code_expiry_minutes = 10

        db = AsyncMock()
        client = make_oauth2_client()
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_grant_type = MagicMock(return_value=True)
        oauth2_svc.validate_scopes = MagicMock(return_value=True)

        device_mock = MagicMock()
        device_mock.user_code = "XXXX-YYYY"
        device_mock.interval = 10

        device_svc = AsyncMock()
        device_svc.create_device_authorization = AsyncMock(return_value=("dc_456", device_mock))

        request = _mock_request()

        result = await device_authorization(
            request=request,
            client_id="test_client_id",
            db=db,
            oauth2_service=oauth2_svc,
            device_service=device_svc,
            scope="openid profile",
        )

        assert result.device_code == "dc_456"
        assert result.expires_in == 600

    @pytest.mark.asyncio
    async def test_device_service_error(self):
        from auth.api.routes.oauth2.device import device_authorization

        db = AsyncMock()
        client = make_oauth2_client()
        client.is_active = True
        client.allowed_scopes = ["openid"]
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_grant_type = MagicMock(return_value=True)

        device_svc = AsyncMock()
        device_svc.create_device_authorization = AsyncMock(
            side_effect=ValueError("Generation failed")
        )

        request = _mock_request()

        with pytest.raises(HTTPException) as exc_info:
            await device_authorization(
                request=request,
                client_id="test_client_id",
                db=db,
                oauth2_service=oauth2_svc,
                device_service=device_svc,
                scope=None,
            )
        assert exc_info.value.detail["error"] == "server_error"


# ---------------------------------------------------------------------------
# device_verify_form (GET /device/verify)
# ---------------------------------------------------------------------------


class TestDeviceVerifyForm:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_no_session_redirects_to_login(self, mock_cookie, mock_prefix, mock_tid):
        from auth.api.routes.oauth2.device import device_verify_form

        db = AsyncMock()
        session_svc = AsyncMock()
        branding_svc = AsyncMock()
        request = _mock_request(cookies={}, url_path="/oauth2/device/verify")

        result = await device_verify_form(
            request=request,
            db=db,
            session_service=session_svc,
            branding_service=branding_svc,
            user_code=None,
        )

        assert isinstance(result, RedirectResponse)
        assert "/auth/login" in result.headers["location"]

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_invalid_session_redirects_to_login(self, mock_cookie, mock_prefix, mock_tid):
        from auth.api.routes.oauth2.device import device_verify_form

        db = AsyncMock()
        session_svc = AsyncMock()
        session_svc.get_session = AsyncMock(return_value=None)
        branding_svc = AsyncMock()
        request = _mock_request(cookies={"session": "bad_token"}, url_path="/oauth2/device/verify")

        result = await device_verify_form(
            request=request,
            db=db,
            session_service=session_svc,
            branding_service=branding_svc,
            user_code=None,
        )

        assert isinstance(result, RedirectResponse)
        assert "/auth/login" in result.headers["location"]

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value="t-1")
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_valid_session_shows_form(self, mock_cookie, mock_prefix, mock_tid):
        from auth.api.routes.oauth2.device import device_verify_form

        db = AsyncMock()
        session_record = make_session()
        session_svc = AsyncMock()
        session_svc.get_session = AsyncMock(return_value=session_record)
        branding_svc = AsyncMock()
        branding_svc.render_template = AsyncMock(return_value="<html>Device Form</html>")
        request = _mock_request(cookies={"session": "good_token"}, url_path="/oauth2/device/verify")

        result = await device_verify_form(
            request=request,
            db=db,
            session_service=session_svc,
            branding_service=branding_svc,
            user_code="ABCD-EFGH",
        )

        assert isinstance(result, HTMLResponse)
        branding_svc.render_template.assert_awaited_once()
        call_args = branding_svc.render_template.call_args
        assert call_args[0][1] == "oauth2/device.html"
        assert call_args[0][2]["user_code"] == "ABCD-EFGH"


# ---------------------------------------------------------------------------
# device_verify_code (POST /device/verify)
# ---------------------------------------------------------------------------


class TestDeviceVerifyCode:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_no_session_redirects(self, mock_cookie, mock_prefix, mock_tid):
        from auth.api.routes.oauth2.device import device_verify_code

        request = _mock_request(cookies={})
        result = await device_verify_code(
            request=request,
            user_code="ABCD-EFGH",
            db=AsyncMock(),
            device_service=AsyncMock(),
            session_service=AsyncMock(),
            branding_service=AsyncMock(),
        )

        assert isinstance(result, RedirectResponse)
        assert "/auth/login" in result.headers["location"]

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_invalid_session_redirects(self, mock_cookie, mock_prefix, mock_tid):
        from auth.api.routes.oauth2.device import device_verify_code

        session_svc = AsyncMock()
        session_svc.get_session = AsyncMock(return_value=None)
        request = _mock_request(cookies={"session": "bad"})

        result = await device_verify_code(
            request=request,
            user_code="ABCD-EFGH",
            db=AsyncMock(),
            device_service=AsyncMock(),
            session_service=session_svc,
            branding_service=AsyncMock(),
        )

        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value="t-1")
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_invalid_user_code(self, mock_cookie, mock_prefix, mock_tid):
        from auth.api.routes.oauth2.device import device_verify_code

        session_record = make_session()
        session_svc = AsyncMock()
        session_svc.get_session = AsyncMock(return_value=session_record)
        device_svc = AsyncMock()
        device_svc.get_by_user_code = AsyncMock(return_value=None)
        branding_svc = AsyncMock()
        branding_svc.render_template = AsyncMock(return_value="<html>Error</html>")
        request = _mock_request(cookies={"session": "good"})

        result = await device_verify_code(
            request=request,
            user_code="BAD-CODE",
            db=AsyncMock(),
            device_service=device_svc,
            session_service=session_svc,
            branding_service=branding_svc,
        )

        assert isinstance(result, HTMLResponse)
        call_args = branding_svc.render_template.call_args
        assert "Invalid code" in call_args[0][2]["error"]

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value="t-1")
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_expired_user_code(self, mock_cookie, mock_prefix, mock_tid):
        from auth.api.routes.oauth2.device import device_verify_code

        session_record = make_session()
        session_svc = AsyncMock()
        session_svc.get_session = AsyncMock(return_value=session_record)
        device = make_device_code()
        device_svc = AsyncMock()
        device_svc.get_by_user_code = AsyncMock(return_value=device)
        device_svc.is_expired = MagicMock(return_value=True)
        branding_svc = AsyncMock()
        branding_svc.render_template = AsyncMock(return_value="<html>Expired</html>")
        request = _mock_request(cookies={"session": "good"})

        result = await device_verify_code(
            request=request,
            user_code="ABCD-EFGH",
            db=AsyncMock(),
            device_service=device_svc,
            session_service=session_svc,
            branding_service=branding_svc,
        )

        assert isinstance(result, HTMLResponse)
        call_args = branding_svc.render_template.call_args
        assert "expired" in call_args[0][2]["error"]

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value="t-1")
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_already_used_code(self, mock_cookie, mock_prefix, mock_tid):
        from auth.api.routes.oauth2.device import device_verify_code

        session_record = make_session()
        session_svc = AsyncMock()
        session_svc.get_session = AsyncMock(return_value=session_record)
        device = make_device_code(status="authorized")
        device_svc = AsyncMock()
        device_svc.get_by_user_code = AsyncMock(return_value=device)
        device_svc.is_expired = MagicMock(return_value=False)
        branding_svc = AsyncMock()
        branding_svc.render_template = AsyncMock(return_value="<html>Used</html>")
        request = _mock_request(cookies={"session": "good"})

        result = await device_verify_code(
            request=request,
            user_code="ABCD-EFGH",
            db=AsyncMock(),
            device_service=device_svc,
            session_service=session_svc,
            branding_service=branding_svc,
        )

        assert isinstance(result, HTMLResponse)
        call_args = branding_svc.render_template.call_args
        assert "already been used" in call_args[0][2]["error"]

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value="t-1")
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_auto_authorize_no_consent(self, mock_cookie, mock_prefix, mock_tid):
        from auth.api.routes.oauth2.device import device_verify_code

        session_record = make_session()
        session_svc = AsyncMock()
        session_svc.get_session = AsyncMock(return_value=session_record)

        client_mock = MagicMock()
        client_mock.require_consent = False
        client_mock.name = "Test App"

        device = make_device_code(status="pending")
        device.client = client_mock

        db = AsyncMock()
        device_svc = AsyncMock()
        device_svc.get_by_user_code = AsyncMock(return_value=device)
        device_svc.is_expired = MagicMock(return_value=False)
        device_svc.authorize = AsyncMock()

        branding_svc = AsyncMock()
        branding_svc.render_template = AsyncMock(return_value="<html>Success</html>")
        request = _mock_request(cookies={"session": "good"})

        result = await device_verify_code(
            request=request,
            user_code="ABCD-EFGH",
            db=db,
            device_service=device_svc,
            session_service=session_svc,
            branding_service=branding_svc,
        )

        assert isinstance(result, HTMLResponse)
        device_svc.authorize.assert_awaited_once_with(db, device, session_record.user_id)
        call_args = branding_svc.render_template.call_args
        assert call_args[0][1] == "oauth2/device_complete.html"

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value="t-1")
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_shows_consent_form(self, mock_cookie, mock_prefix, mock_tid):
        from auth.api.routes.oauth2.device import device_verify_code

        session_record = make_session()
        session_svc = AsyncMock()
        session_svc.get_session = AsyncMock(return_value=session_record)

        client_mock = MagicMock()
        client_mock.require_consent = True
        client_mock.name = "Test App"

        device = make_device_code(status="pending")
        device.client = client_mock

        db = AsyncMock()
        device_svc = AsyncMock()
        device_svc.get_by_user_code = AsyncMock(return_value=device)
        device_svc.is_expired = MagicMock(return_value=False)

        branding_svc = AsyncMock()
        branding_svc.render_template = AsyncMock(return_value="<html>Consent</html>")
        request = _mock_request(cookies={"session": "good"})

        result = await device_verify_code(
            request=request,
            user_code="ABCD-EFGH",
            db=db,
            device_service=device_svc,
            session_service=session_svc,
            branding_service=branding_svc,
        )

        assert isinstance(result, HTMLResponse)
        call_args = branding_svc.render_template.call_args
        assert call_args[0][1] == "oauth2/device_consent.html"


# ---------------------------------------------------------------------------
# device_complete (POST /device/complete)
# ---------------------------------------------------------------------------


class TestDeviceComplete:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_no_session_redirects(self, mock_cookie, mock_prefix, mock_tid):
        from auth.api.routes.oauth2.device import device_complete

        request = _mock_request(cookies={})
        result = await device_complete(
            request=request,
            user_code="ABCD-EFGH",
            consent="allow",
            db=AsyncMock(),
            device_service=AsyncMock(),
            session_service=AsyncMock(),
            branding_service=AsyncMock(),
        )

        assert isinstance(result, RedirectResponse)
        assert "/auth/login" in result.headers["location"]

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_invalid_session_redirects(self, mock_cookie, mock_prefix, mock_tid):
        from auth.api.routes.oauth2.device import device_complete

        session_svc = AsyncMock()
        session_svc.get_session = AsyncMock(return_value=None)
        request = _mock_request(cookies={"session": "bad"})

        result = await device_complete(
            request=request,
            user_code="ABCD-EFGH",
            consent="allow",
            db=AsyncMock(),
            device_service=AsyncMock(),
            session_service=session_svc,
            branding_service=AsyncMock(),
        )

        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value="t-1")
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_invalid_or_expired_code(self, mock_cookie, mock_prefix, mock_tid):
        from auth.api.routes.oauth2.device import device_complete

        session_record = make_session()
        session_svc = AsyncMock()
        session_svc.get_session = AsyncMock(return_value=session_record)
        device_svc = AsyncMock()
        device_svc.get_by_user_code = AsyncMock(return_value=None)
        branding_svc = AsyncMock()
        branding_svc.render_template = AsyncMock(return_value="<html>Error</html>")
        request = _mock_request(cookies={"session": "good"})

        result = await device_complete(
            request=request,
            user_code="BAD-CODE",
            consent="allow",
            db=AsyncMock(),
            device_service=device_svc,
            session_service=session_svc,
            branding_service=branding_svc,
        )

        assert isinstance(result, HTMLResponse)
        call_args = branding_svc.render_template.call_args
        assert "Invalid or expired" in call_args[0][2]["error"]

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value="t-1")
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_expired_device_code(self, mock_cookie, mock_prefix, mock_tid):
        from auth.api.routes.oauth2.device import device_complete

        session_record = make_session()
        session_svc = AsyncMock()
        session_svc.get_session = AsyncMock(return_value=session_record)
        device = make_device_code(status="pending")
        device_svc = AsyncMock()
        device_svc.get_by_user_code = AsyncMock(return_value=device)
        device_svc.is_expired = MagicMock(return_value=True)
        branding_svc = AsyncMock()
        branding_svc.render_template = AsyncMock(return_value="<html>Error</html>")
        request = _mock_request(cookies={"session": "good"})

        result = await device_complete(
            request=request,
            user_code="ABCD-EFGH",
            consent="allow",
            db=AsyncMock(),
            device_service=device_svc,
            session_service=session_svc,
            branding_service=branding_svc,
        )

        assert isinstance(result, HTMLResponse)
        call_args = branding_svc.render_template.call_args
        assert "Invalid or expired" in call_args[0][2]["error"]

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value="t-1")
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_already_used_code(self, mock_cookie, mock_prefix, mock_tid):
        from auth.api.routes.oauth2.device import device_complete

        session_record = make_session()
        session_svc = AsyncMock()
        session_svc.get_session = AsyncMock(return_value=session_record)
        device = make_device_code(status="authorized")
        device_svc = AsyncMock()
        device_svc.get_by_user_code = AsyncMock(return_value=device)
        device_svc.is_expired = MagicMock(return_value=False)
        branding_svc = AsyncMock()
        branding_svc.render_template = AsyncMock(return_value="<html>Error</html>")
        request = _mock_request(cookies={"session": "good"})

        result = await device_complete(
            request=request,
            user_code="ABCD-EFGH",
            consent="allow",
            db=AsyncMock(),
            device_service=device_svc,
            session_service=session_svc,
            branding_service=branding_svc,
        )

        assert isinstance(result, HTMLResponse)
        call_args = branding_svc.render_template.call_args
        assert "already been used" in call_args[0][2]["error"]

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value="t-1")
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_consent_allow(self, mock_cookie, mock_prefix, mock_tid):
        from auth.api.routes.oauth2.device import device_complete

        session_record = make_session()
        session_svc = AsyncMock()
        session_svc.get_session = AsyncMock(return_value=session_record)

        device = make_device_code(status="pending")
        db = AsyncMock()
        device_svc = AsyncMock()
        device_svc.get_by_user_code = AsyncMock(return_value=device)
        device_svc.is_expired = MagicMock(return_value=False)
        device_svc.authorize = AsyncMock()

        branding_svc = AsyncMock()
        branding_svc.render_template = AsyncMock(return_value="<html>Success</html>")
        request = _mock_request(cookies={"session": "good"})

        result = await device_complete(
            request=request,
            user_code="ABCD-EFGH",
            consent="allow",
            db=db,
            device_service=device_svc,
            session_service=session_svc,
            branding_service=branding_svc,
        )

        assert isinstance(result, HTMLResponse)
        device_svc.authorize.assert_awaited_once_with(db, device, session_record.user_id)
        call_args = branding_svc.render_template.call_args
        assert call_args[0][2]["success"] is True

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value="t-1")
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_consent_deny(self, mock_cookie, mock_prefix, mock_tid):
        from auth.api.routes.oauth2.device import device_complete

        session_record = make_session()
        session_svc = AsyncMock()
        session_svc.get_session = AsyncMock(return_value=session_record)

        device = make_device_code(status="pending")
        db = AsyncMock()
        device_svc = AsyncMock()
        device_svc.get_by_user_code = AsyncMock(return_value=device)
        device_svc.is_expired = MagicMock(return_value=False)
        device_svc.deny = AsyncMock()

        branding_svc = AsyncMock()
        branding_svc.render_template = AsyncMock(return_value="<html>Denied</html>")
        request = _mock_request(cookies={"session": "good"})

        result = await device_complete(
            request=request,
            user_code="ABCD-EFGH",
            consent="deny",
            db=db,
            device_service=device_svc,
            session_service=session_svc,
            branding_service=branding_svc,
        )

        assert isinstance(result, HTMLResponse)
        device_svc.deny.assert_awaited_once_with(db, device)
        call_args = branding_svc.render_template.call_args
        assert call_args[0][2]["success"] is False


class TestDeviceVerifyFormQueryString:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_query_string_is_preserved_in_login_redirect(
        self, mock_cookie, mock_prefix, mock_tid
    ):
        from auth.api.routes.oauth2.device import device_verify_form

        request = _mock_request(
            cookies={},
            url_path="/oauth2/device/verify",
            url_query="user_code=ABCD-EFGH",
        )

        result = await device_verify_form(
            request=request,
            db=AsyncMock(),
            session_service=AsyncMock(),
            branding_service=AsyncMock(),
            user_code="ABCD-EFGH",
        )

        assert isinstance(result, RedirectResponse)
        assert "user_code%3DABCD-EFGH" in result.headers["location"] or (
            "user_code=ABCD-EFGH" in result.headers["location"]
        )
