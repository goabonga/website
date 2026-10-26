# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for internal.routes.vpn route handlers."""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.responses import RedirectResponse
from internal.auth.models import User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(**kwargs):
    defaults = {
        "id": uuid.UUID("12345678-1234-5678-1234-567812345678"),
        "email": "test@example.com",
        "name": "Test User",
        "scopes": ["*"],
    }
    defaults.update(kwargs)
    return User(**defaults)


def _make_request(**kwargs):
    req = MagicMock()
    req.query_params = kwargs.get("query_params", {})
    req.headers = kwargs.get("headers", {})
    req.form = AsyncMock(return_value=MagicMock())
    return req


# ---------------------------------------------------------------------------
# vpn_sessions
# ---------------------------------------------------------------------------


class TestVpnSessions:
    @patch("internal.routes.vpn.vpn_portal_client")
    @patch("internal.routes.vpn.settings")
    @patch("internal.routes.vpn.templates")
    async def test_success(self, mock_templates, mock_settings, mock_client):
        from internal.routes.vpn import vpn_sessions

        mock_settings.oauth2_client_id = "cid"
        sessions_resp = MagicMock()
        sessions_resp.sessions = [{"serial": "abc"}]
        sessions_resp.total = 1
        mock_client.get_sessions = AsyncMock(return_value=sessions_resp)
        user = _make_user()
        request = _make_request(query_params={"success": "done"})

        await vpn_sessions(request, page=1, auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["sessions"] == [{"serial": "abc"}]
        assert ctx["total"] == 1
        assert ctx["total_pages"] == 1
        assert ctx["success"] == "done"
        # error should be None since sessions_response is truthy and no error in query_params
        assert ctx["error"] is None

    @patch("internal.routes.vpn.vpn_portal_client")
    @patch("internal.routes.vpn.settings")
    @patch("internal.routes.vpn.templates")
    async def test_service_unavailable(self, mock_templates, mock_settings, mock_client):
        from internal.routes.vpn import vpn_sessions

        mock_settings.oauth2_client_id = "cid"
        mock_client.get_sessions = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        await vpn_sessions(request, page=1, auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["sessions"] == []
        assert ctx["total"] == 0
        assert ctx["total_pages"] == 0
        assert "unavailable" in ctx["error"]

    @patch("internal.routes.vpn.vpn_portal_client")
    @patch("internal.routes.vpn.settings")
    @patch("internal.routes.vpn.templates")
    async def test_pagination(self, mock_templates, mock_settings, mock_client):
        from internal.routes.vpn import vpn_sessions

        mock_settings.oauth2_client_id = "cid"
        sessions_resp = MagicMock()
        sessions_resp.sessions = []
        sessions_resp.total = 45
        mock_client.get_sessions = AsyncMock(return_value=sessions_resp)
        user = _make_user()
        request = _make_request()

        await vpn_sessions(request, page=2, auth_result=user)

        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["page"] == 2
        assert ctx["total_pages"] == 3  # ceil(45/20)

    @patch("internal.routes.vpn.vpn_portal_client")
    @patch("internal.routes.vpn.settings")
    @patch("internal.routes.vpn.templates")
    async def test_now_is_utc_datetime(self, mock_templates, mock_settings, mock_client):
        from internal.routes.vpn import vpn_sessions

        mock_settings.oauth2_client_id = "cid"
        sessions_resp = MagicMock()
        sessions_resp.sessions = []
        sessions_resp.total = 0
        mock_client.get_sessions = AsyncMock(return_value=sessions_resp)
        user = _make_user()
        request = _make_request()

        await vpn_sessions(request, page=1, auth_result=user)

        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert isinstance(ctx["now"], datetime)

    @patch("internal.routes.vpn.vpn_portal_client")
    @patch("internal.routes.vpn.settings")
    @patch("internal.routes.vpn.templates")
    async def test_error_from_query_params(self, mock_templates, mock_settings, mock_client):
        from internal.routes.vpn import vpn_sessions

        mock_settings.oauth2_client_id = "cid"
        sessions_resp = MagicMock()
        sessions_resp.sessions = []
        sessions_resp.total = 0
        mock_client.get_sessions = AsyncMock(return_value=sessions_resp)
        user = _make_user()
        request = _make_request(query_params={"error": "qp_error"})

        await vpn_sessions(request, page=1, auth_result=user)

        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        # error is None (from sessions_response being truthy) or query_params
        assert ctx["error"] == "qp_error"

    async def test_redirect_auth(self):
        from internal.routes.vpn import vpn_sessions

        redirect = RedirectResponse(url="/login")
        result = await vpn_sessions(MagicMock(), auth_result=redirect)
        assert result is redirect


# ---------------------------------------------------------------------------
# revoke_vpn_session
# ---------------------------------------------------------------------------


class TestRevokeVpnSession:
    @patch("internal.routes.vpn.vpn_portal_client")
    @patch("internal.routes.vpn.settings")
    async def test_success(self, mock_settings, mock_client):
        from internal.routes.vpn import revoke_vpn_session

        mock_settings.oauth2_client_id = "cid"
        mock_client.revoke_session = AsyncMock(return_value=True)
        user = _make_user()
        request = _make_request()

        result = await revoke_vpn_session(
            request,
            serial_number="abc123",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success=" in result.headers["location"]

    @patch("internal.routes.vpn.vpn_portal_client")
    @patch("internal.routes.vpn.settings")
    async def test_failure(self, mock_settings, mock_client):
        from internal.routes.vpn import revoke_vpn_session

        mock_settings.oauth2_client_id = "cid"
        mock_client.revoke_session = AsyncMock(return_value=False)
        user = _make_user()
        request = _make_request()

        result = await revoke_vpn_session(
            request,
            serial_number="abc123",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.vpn import revoke_vpn_session

        redirect = RedirectResponse(url="/login")
        result = await revoke_vpn_session(
            MagicMock(),
            serial_number="abc123",
            auth_result=redirect,
        )
        assert result is redirect


# ---------------------------------------------------------------------------
# rendered page
# ---------------------------------------------------------------------------


class TestVpnSessionsPage:
    @patch("internal.routes.vpn.vpn_portal_client")
    @patch("internal.routes.vpn.settings")
    async def test_buttons_survive_quotes_in_session_data(self, mock_settings, mock_client):
        from internal.routes.vpn import vpn_sessions
        from internal.services.vpn_portal_client import VPNSession, VPNSessionsResponse

        mock_settings.oauth2_client_id = "cid"
        now = datetime.now().astimezone()
        session = VPNSession(
            id="session-001",
            user_id="user-001",
            username="o'brien",
            device_name="laptop",
            connected_at=now,
            assigned_ip="10.8.0.2",
            certificate_serial="AB'CD",
            expires_at=now,
            scopes=[],
            routes=[],
        )
        mock_client.get_sessions = AsyncMock(
            return_value=VPNSessionsResponse(sessions=[session], total=1, page=1, per_page=20)
        )
        request = MagicMock()
        request.query_params = {}

        response = await vpn_sessions(request, page=1, auth_result=_make_user())

        body = response.body.decode()
        # The serial number is a JavaScript string literal that cannot be closed by a quote
        assert 'showRevokeConfirm("AB\\u0027CD")' in body
        assert 'hideRevokeConfirm("AB\\u0027CD")' in body
