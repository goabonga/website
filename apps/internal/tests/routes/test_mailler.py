# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for internal.routes.mailler route handlers."""

import uuid
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
# mailler_dashboard
# ---------------------------------------------------------------------------


class TestMaillerDashboard:
    @patch("internal.routes.mailler.mailler_client")
    @patch("internal.routes.mailler.settings")
    @patch("internal.routes.mailler.templates")
    async def test_success_with_stats(self, mock_templates, mock_settings, mock_client):
        from internal.routes.mailler import mailler_dashboard

        mock_settings.oauth2_client_id = "cid"
        mock_client.get_stats = AsyncMock(
            return_value={
                "total": {"sent": 40, "delivered": 60, "bounced": 5, "failed": 3},
            }
        )
        mock_client.get_providers = AsyncMock(return_value=["brevo", "ses"])
        user = _make_user()
        request = _make_request()

        await mailler_dashboard(request, days=30, provider=None, auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["days"] == 30
        assert ctx["providers"] == ["brevo", "ses"]
        # total_sent = 40 + 60 = 100
        assert ctx["delivery_rate"] == 60.0
        assert ctx["bounce_rate"] == 5.0
        assert ctx["fail_rate"] == 3.0

    @patch("internal.routes.mailler.mailler_client")
    @patch("internal.routes.mailler.settings")
    @patch("internal.routes.mailler.templates")
    async def test_zero_total_sent(self, mock_templates, mock_settings, mock_client):
        from internal.routes.mailler import mailler_dashboard

        mock_settings.oauth2_client_id = "cid"
        mock_client.get_stats = AsyncMock(
            return_value={
                "total": {"sent": 0, "delivered": 0, "bounced": 0, "failed": 0},
            }
        )
        mock_client.get_providers = AsyncMock(return_value=[])
        user = _make_user()
        request = _make_request()

        await mailler_dashboard(request, days=7, provider=None, auth_result=user)

        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["delivery_rate"] == 0
        assert ctx["bounce_rate"] == 0
        assert ctx["fail_rate"] == 0

    @patch("internal.routes.mailler.mailler_client")
    @patch("internal.routes.mailler.settings")
    @patch("internal.routes.mailler.templates")
    async def test_empty_total(self, mock_templates, mock_settings, mock_client):
        """Stats dict has no 'total' key."""
        from internal.routes.mailler import mailler_dashboard

        mock_settings.oauth2_client_id = "cid"
        mock_client.get_stats = AsyncMock(return_value={})
        mock_client.get_providers = AsyncMock(return_value=[])
        user = _make_user()
        request = _make_request()

        await mailler_dashboard(request, days=30, provider=None, auth_result=user)

        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["delivery_rate"] == 0
        assert ctx["bounce_rate"] == 0
        assert ctx["fail_rate"] == 0

    @patch("internal.routes.mailler.mailler_client")
    @patch("internal.routes.mailler.settings")
    @patch("internal.routes.mailler.templates")
    async def test_provider_filter(self, mock_templates, mock_settings, mock_client):
        from internal.routes.mailler import mailler_dashboard

        mock_settings.oauth2_client_id = "cid"
        mock_client.get_stats = AsyncMock(return_value={"total": {}})
        mock_client.get_providers = AsyncMock(return_value=["brevo"])
        user = _make_user()
        request = _make_request()

        await mailler_dashboard(request, days=30, provider="brevo", auth_result=user)

        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["provider_filter"] == "brevo"
        mock_client.get_stats.assert_awaited_once()
        call_kwargs = mock_client.get_stats.call_args[1]
        assert call_kwargs["provider"] == "brevo"

    async def test_redirect_auth(self):
        from internal.routes.mailler import mailler_dashboard

        redirect = RedirectResponse(url="/login")
        result = await mailler_dashboard(MagicMock(), auth_result=redirect)
        assert result is redirect


# ---------------------------------------------------------------------------
# emails_list
# ---------------------------------------------------------------------------


class TestEmailsList:
    @patch("internal.routes.mailler.mailler_client")
    @patch("internal.routes.mailler.templates")
    async def test_success(self, mock_templates, mock_client):
        from internal.routes.mailler import emails_list

        mock_client.get_emails = AsyncMock(
            return_value={
                "items": [{"id": "e1"}],
                "total": 1,
                "page": 1,
                "page_size": 20,
                "pages": 1,
            }
        )
        mock_client.get_providers = AsyncMock(return_value=["brevo"])
        user = _make_user()
        request = _make_request()

        await emails_list(
            request,
            page=1,
            page_size=20,
            provider=None,
            status=None,
            auth_result=user,
        )

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["emails"] == [{"id": "e1"}]
        assert ctx["total"] == 1
        assert ctx["providers"] == ["brevo"]
        assert "pending" in ctx["statuses"]

    @patch("internal.routes.mailler.mailler_client")
    @patch("internal.routes.mailler.templates")
    async def test_with_filters(self, mock_templates, mock_client):
        from internal.routes.mailler import emails_list

        mock_client.get_emails = AsyncMock(
            return_value={
                "items": [],
                "total": 0,
                "page": 1,
                "page_size": 20,
                "pages": 1,
            }
        )
        mock_client.get_providers = AsyncMock(return_value=[])
        user = _make_user()
        request = _make_request()

        await emails_list(
            request,
            page=2,
            page_size=50,
            provider="ses",
            status="sent",
            auth_result=user,
        )

        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["provider_filter"] == "ses"
        assert ctx["status_filter"] == "sent"

    @patch("internal.routes.mailler.mailler_client")
    @patch("internal.routes.mailler.templates")
    async def test_empty_response(self, mock_templates, mock_client):
        from internal.routes.mailler import emails_list

        mock_client.get_emails = AsyncMock(return_value={})
        mock_client.get_providers = AsyncMock(return_value=[])
        user = _make_user()
        request = _make_request()

        await emails_list(request, auth_result=user)

        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["emails"] == []
        assert ctx["total"] == 0

    async def test_redirect_auth(self):
        from internal.routes.mailler import emails_list

        redirect = RedirectResponse(url="/login")
        result = await emails_list(MagicMock(), auth_result=redirect)
        assert result is redirect


# ---------------------------------------------------------------------------
# email_detail
# ---------------------------------------------------------------------------


class TestEmailDetail:
    @patch("internal.routes.mailler.mailler_client")
    @patch("internal.routes.mailler.templates")
    async def test_success(self, mock_templates, mock_client):
        from internal.routes.mailler import email_detail

        valid_uuid = str(uuid.uuid4())
        mock_client.get_email = AsyncMock(return_value={"id": valid_uuid, "to": "a@b.com"})
        user = _make_user()
        request = _make_request()

        await email_detail(request, email_id=valid_uuid, auth_result=user)

        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["email"]["id"] == valid_uuid

    @patch("internal.routes.mailler.mailler_client")
    async def test_invalid_uuid(self, mock_client):
        from internal.routes.mailler import email_detail

        user = _make_user()
        request = _make_request()

        result = await email_detail(request, email_id="not-a-uuid", auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "error=Invalid" in result.headers["location"]

    @patch("internal.routes.mailler.mailler_client")
    async def test_not_found(self, mock_client):
        from internal.routes.mailler import email_detail

        valid_uuid = str(uuid.uuid4())
        mock_client.get_email = AsyncMock(return_value=None)
        user = _make_user()
        request = _make_request()

        result = await email_detail(request, email_id=valid_uuid, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "error=Email" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.mailler import email_detail

        redirect = RedirectResponse(url="/login")
        result = await email_detail(MagicMock(), email_id="abc", auth_result=redirect)
        assert result is redirect


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class TestMaillerSettings:
    def test_defaults_are_neutral(self, monkeypatch):
        from internal.config import Settings

        for name in (
            "MAILLER_API_URL",
            "MAILLER_SOCKET_PATH",
            "MAILLER_ADMIN_SCOPE",
            "MAILLER_TIMEOUT",
            "MAILLER_DEFAULT_PROVIDER",
        ):
            monkeypatch.delenv(name, raising=False)
        settings = Settings(_env_file=None)

        assert settings.mailler_api_url == ""
        assert settings.mailler_socket_path == ""
        assert settings.mailler_admin_scope == "mailler:admin"
        assert settings.mailler_timeout == 30.0
        assert settings.mailler_default_provider == ""

    def test_admin_scope_follows_the_environment(self, monkeypatch):
        from internal.config import Settings

        monkeypatch.setenv("MAILLER_ADMIN_SCOPE", "mailler:root")
        assert Settings(_env_file=None).mailler_admin_scope == "mailler:root"
