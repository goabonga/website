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


# ---------------------------------------------------------------------------
# Authorized clients: parsing the form
# ---------------------------------------------------------------------------

_FORM = {
    "name": "",
    "from_email": "",
    "from_name": "",
    "reply_to": "",
    "allowed_senders": "",
    "allowed_providers": [],
    "default_provider": "",
    "rate_limit_per_minute": "",
    "daily_quota": "",
    "callback_url": "",
    "callback_secret": "",
    "is_active": True,
}


class TestParseSenders:
    def test_address_with_optional_name(self):
        from internal.routes.mailler import parse_senders

        text = "a@example.test\n\n b@example.test , The B Team \nc@example.test, Name, with comma"
        assert parse_senders(text) == [
            {"email": "a@example.test"},
            {"email": "b@example.test", "name": "The B Team"},
            {"email": "c@example.test", "name": "Name, with comma"},
        ]

    def test_nothing(self):
        from internal.routes.mailler import parse_senders

        assert parse_senders("") == []
        assert parse_senders(" \n ") == []

    def test_a_line_without_address(self):
        import pytest
        from internal.routes.mailler import parse_senders

        for text in (", Name", "two words@example.test"):
            with pytest.raises(ValueError, match="is not a sender"):
                parse_senders(text)


class TestParseLimit:
    def test_whole_numbers(self):
        from internal.routes.mailler import parse_limit

        assert parse_limit(" 60 ", "The rate limit") == 60

    def test_nothing_means_no_limit(self):
        from internal.routes.mailler import parse_limit

        assert parse_limit("", "The rate limit") is None
        assert parse_limit("  ", "The rate limit") is None

    def test_refused_values(self):
        import pytest
        from internal.routes.mailler import parse_limit

        for text in ("0", "-5", "1.5", "ten"):
            with pytest.raises(ValueError, match="The daily quota must be a positive whole number"):
                parse_limit(text, "The daily quota")


class TestClientPayload:
    def _payload(self, **fields):
        from internal.routes.mailler import client_payload

        return client_payload(**{**_FORM, "updating": False, **fields})

    def test_registering_leaves_empty_fields_out(self):
        assert self._payload() == {
            "is_active": True,
            "allowed_senders": [],
            "allowed_providers": [],
        }

    def test_registering_a_complete_client(self):
        payload = self._payload(
            name=" My app ",
            from_email="no-reply@example.test",
            from_name="My app",
            reply_to="help@example.test",
            allowed_senders="other@example.test, Other",
            allowed_providers=["one", "", "two"],
            default_provider="one",
            rate_limit_per_minute="60",
            daily_quota="5000",
            callback_url=" https://app.example.test/status ",
            callback_secret="s" * 16,
        )
        assert payload == {
            "name": "My app",
            "is_active": True,
            "from_email": "no-reply@example.test",
            "from_name": "My app",
            "reply_to": "help@example.test",
            "allowed_senders": [{"email": "other@example.test", "name": "Other"}],
            "allowed_providers": ["one", "two"],
            "default_provider": "one",
            "rate_limit_per_minute": 60,
            "daily_quota": 5000,
            "callback_url": "https://app.example.test/status",
            "callback_secret": "s" * 16,
        }

    def test_updating_sends_empty_fields_as_null_to_remove_them(self):
        payload = self._payload(updating=True)
        assert payload == {
            "name": None,
            "is_active": True,
            "from_email": None,
            "from_name": None,
            "reply_to": None,
            "allowed_senders": [],
            "allowed_providers": [],
            "default_provider": None,
            "rate_limit_per_minute": None,
            "daily_quota": None,
            "callback_url": None,
            "callback_secret": None,
        }

    def test_updating_keeps_the_secret_when_the_url_stays(self):
        payload = self._payload(updating=True, callback_url="https://app.example.test/status")
        assert "callback_secret" not in payload

    def test_updating_replaces_the_secret(self):
        payload = self._payload(
            updating=True, callback_url="https://app.example.test/status", callback_secret="n" * 16
        )
        assert payload["callback_secret"] == "n" * 16

    def test_malformed_fields(self):
        import pytest

        with pytest.raises(ValueError, match="positive whole number"):
            self._payload(daily_quota="0")
        with pytest.raises(ValueError, match="is not a sender"):
            self._payload(allowed_senders=",x")


# ---------------------------------------------------------------------------
# Authorized clients: route handlers
# ---------------------------------------------------------------------------

_CLIENT = {
    "client_id": "app-one",
    "name": "App one",
    "is_active": True,
    "from_email": "no-reply@example.test",
    "from_name": "App one",
    "reply_to": None,
    "allowed_senders": [{"email": "other@example.test", "name": "Other"}],
    "allowed_providers": ["one"],
    "default_provider": "one",
    "rate_limit_per_minute": 60,
    "daily_quota": None,
    "callback_url": "https://app.example.test/status",
    "has_callback_secret": True,
}


def _form_kwargs(**fields):
    return {**_FORM, "rate_limit_per_minute": "", "daily_quota": "", **fields}


class TestClientsList:
    @patch("internal.routes.mailler.mailler_client")
    @patch("internal.routes.mailler.templates")
    async def test_success(self, mock_templates, mock_client):
        from internal.routes.mailler import clients_list

        mock_client.list_clients = AsyncMock(
            return_value={"items": [_CLIENT], "total": 41, "page": 2, "pages": 3}
        )
        request = MagicMock(query_params={"success": "done"})

        with patch("internal.routes.mailler.settings") as s:
            s.mailler_clients_page_size = 15
            s.oauth2_client_id = "cid"
            await clients_list(
                request, page=2, search="app", status="inactive", auth_result=_make_user()
            )

        mock_client.list_clients.assert_awaited_once_with(
            page=2, page_size=15, is_active=False, search="app"
        )
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["clients"] == [_CLIENT]
        assert (ctx["total"], ctx["page"], ctx["pages"]) == (41, 2, 3)
        assert ctx["search"] == "app"
        assert ctx["status_filter"] == "inactive"
        assert ctx["success"] == "done"
        assert ctx["active_section"] == "mailler"

    @patch("internal.routes.mailler.mailler_client")
    @patch("internal.routes.mailler.templates")
    async def test_status_filter(self, mock_templates, mock_client):
        from internal.routes.mailler import clients_list

        mock_client.list_clients = AsyncMock(return_value={})

        for status, expected in ((None, None), ("active", True), ("inactive", False)):
            await clients_list(
                MagicMock(query_params={}),
                page=1,
                search=None,
                status=status,
                auth_result=_make_user(),
            )
            assert mock_client.list_clients.call_args[1]["is_active"] is expected

    async def test_redirect_auth(self):
        from internal.routes.mailler import clients_list

        redirect = RedirectResponse(url="/login")
        result = await clients_list(
            MagicMock(), page=1, search=None, status=None, auth_result=redirect
        )
        assert result is redirect


class TestClientForms:
    @patch("internal.routes.mailler.mailler_client")
    @patch("internal.routes.mailler.templates")
    async def test_new_form(self, mock_templates, mock_client):
        from internal.routes.mailler import client_new

        mock_client.get_providers = AsyncMock(return_value=["one", "two"])

        await client_new(MagicMock(query_params={"error": "oops"}), auth_result=_make_user())

        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["client"] is None
        assert ctx["is_edit"] is False
        assert ctx["providers"] == ["one", "two"]
        assert ctx["error"] == "oops"

    @patch("internal.routes.mailler.mailler_client")
    @patch("internal.routes.mailler.templates")
    async def test_edit_form(self, mock_templates, mock_client):
        from internal.routes.mailler import client_edit

        mock_client.get_client = AsyncMock(return_value=_CLIENT)
        mock_client.get_providers = AsyncMock(return_value=["one"])

        await client_edit(MagicMock(query_params={}), client_id="app-one", auth_result=_make_user())

        mock_client.get_client.assert_awaited_once_with("app-one")
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["client"] == _CLIENT
        assert ctx["is_edit"] is True

    @patch("internal.routes.mailler.mailler_client")
    async def test_edit_form_of_an_unknown_client(self, mock_client):
        from internal.routes.mailler import client_edit

        mock_client.get_client = AsyncMock(return_value=None)

        result = await client_edit(MagicMock(), client_id="gone", auth_result=_make_user())

        assert result.headers["location"] == "/mailler/clients?error=Client+not+found"

    async def test_redirect_auth(self):
        from internal.routes.mailler import client_edit, client_new

        redirect = RedirectResponse(url="/login")
        assert await client_new(MagicMock(), auth_result=redirect) is redirect
        assert await client_edit(MagicMock(), client_id="x", auth_result=redirect) is redirect


class TestClientCreate:
    @patch("internal.routes.mailler.mailler_client")
    async def test_success(self, mock_client):
        from internal.routes.mailler import client_create

        mock_client.create_client = AsyncMock(return_value=_CLIENT)

        result = await client_create(
            MagicMock(),
            client_id=" app-one ",
            **_form_kwargs(from_email="no-reply@example.test", rate_limit_per_minute="60"),
            auth_result=_make_user(),
        )

        assert result.headers["location"] == "/mailler/clients?success=Client+app-one+registered"
        sent = mock_client.create_client.call_args[0][0]
        assert sent["client_id"] == "app-one"
        assert sent["from_email"] == "no-reply@example.test"
        assert sent["rate_limit_per_minute"] == 60

    @patch("internal.routes.mailler.mailler_client")
    async def test_the_service_refuses(self, mock_client):
        from internal.routes.mailler import client_create
        from internal.services.mailler_client import MaillerAPIError

        mock_client.create_client = AsyncMock(
            side_effect=MaillerAPIError("Client 'app-one' is already registered", 409)
        )

        result = await client_create(
            MagicMock(), client_id="app-one", **_form_kwargs(), auth_result=_make_user()
        )

        assert result.headers["location"].startswith("/mailler/clients/new?error=")
        assert "already+registered" in result.headers["location"]

    @patch("internal.routes.mailler.mailler_client")
    async def test_the_service_does_not_answer(self, mock_client):
        from internal.routes.mailler import client_create

        mock_client.create_client = AsyncMock(return_value={})

        result = await client_create(
            MagicMock(), client_id="app-one", **_form_kwargs(), auth_result=_make_user()
        )

        assert "did+not+answer" in result.headers["location"]

    @patch("internal.routes.mailler.mailler_client")
    async def test_invalid_form_is_refused_before_the_call(self, mock_client):
        from internal.routes.mailler import client_create

        mock_client.create_client = AsyncMock()

        for client_id, fields in (
            ("", {}),
            ("two words", {}),
            ("app-one", {"daily_quota": "0"}),
            ("app-one", {"allowed_senders": ",x"}),
        ):
            result = await client_create(
                MagicMock(), client_id=client_id, **_form_kwargs(**fields), auth_result=_make_user()
            )
            assert result.headers["location"].startswith("/mailler/clients/new?error=")

        mock_client.create_client.assert_not_awaited()

    async def test_redirect_auth(self):
        from internal.routes.mailler import client_create

        redirect = RedirectResponse(url="/login")
        result = await client_create(
            MagicMock(), client_id="x", **_form_kwargs(), auth_result=redirect
        )
        assert result is redirect


class TestClientUpdate:
    @patch("internal.routes.mailler.mailler_client")
    async def test_success_applies_every_field(self, mock_client):
        from internal.routes.mailler import client_update

        mock_client.update_client = AsyncMock(return_value=_CLIENT)

        result = await client_update(
            MagicMock(),
            client_id="app-one",
            **_form_kwargs(name="Renamed", daily_quota="100"),
            auth_result=_make_user(),
        )

        assert result.headers["location"] == "/mailler/clients?success=Client+app-one+updated"
        client_id, sent = mock_client.update_client.call_args[0]
        assert client_id == "app-one"
        assert sent["name"] == "Renamed"
        assert sent["daily_quota"] == 100
        assert sent["rate_limit_per_minute"] is None
        assert sent["callback_secret"] is None

    @patch("internal.routes.mailler.mailler_client")
    async def test_errors_return_to_the_form_of_the_client(self, mock_client):
        from internal.routes.mailler import client_update
        from internal.services.mailler_client import MaillerAPIError

        mock_client.update_client = AsyncMock(
            side_effect=MaillerAPIError("callback_secret needs a callback_url", 422)
        )

        result = await client_update(
            MagicMock(), client_id="a b", **_form_kwargs(), auth_result=_make_user()
        )
        invalid = await client_update(
            MagicMock(),
            client_id="a b",
            **_form_kwargs(rate_limit_per_minute="x"),
            auth_result=_make_user(),
        )

        assert result.headers["location"].startswith("/mailler/clients/a%20b/edit?error=")
        assert invalid.headers["location"].startswith("/mailler/clients/a%20b/edit?error=")

    @patch("internal.routes.mailler.mailler_client")
    async def test_the_service_does_not_answer(self, mock_client):
        from internal.routes.mailler import client_update

        mock_client.update_client = AsyncMock(return_value={})

        result = await client_update(
            MagicMock(), client_id="app-one", **_form_kwargs(), auth_result=_make_user()
        )

        assert "did+not+answer" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.mailler import client_update

        redirect = RedirectResponse(url="/login")
        result = await client_update(
            MagicMock(), client_id="x", **_form_kwargs(), auth_result=redirect
        )
        assert result is redirect


class TestClientActivation:
    @patch("internal.routes.mailler.mailler_client")
    async def test_deactivate(self, mock_client):
        from internal.routes.mailler import client_deactivate

        mock_client.update_client = AsyncMock(return_value=_CLIENT)

        result = await client_deactivate(MagicMock(), client_id="app-one", auth_result=_make_user())

        assert result.headers["location"] == "/mailler/clients?success=Client+app-one+deactivated"
        mock_client.update_client.assert_awaited_once_with("app-one", {"is_active": False})

    @patch("internal.routes.mailler.mailler_client")
    async def test_activate(self, mock_client):
        from internal.routes.mailler import client_activate

        mock_client.update_client = AsyncMock(return_value=_CLIENT)

        result = await client_activate(MagicMock(), client_id="app-one", auth_result=_make_user())

        assert result.headers["location"] == "/mailler/clients?success=Client+app-one+activated"
        mock_client.update_client.assert_awaited_once_with("app-one", {"is_active": True})

    @patch("internal.routes.mailler.mailler_client")
    async def test_refused_by_the_service(self, mock_client):
        from internal.routes.mailler import client_deactivate
        from internal.services.mailler_client import MaillerAPIError

        mock_client.update_client = AsyncMock(side_effect=MaillerAPIError("Client not found", 404))

        result = await client_deactivate(MagicMock(), client_id="gone", auth_result=_make_user())

        assert result.headers["location"] == "/mailler/clients?error=Client+not+found"

    @patch("internal.routes.mailler.mailler_client")
    async def test_no_answer(self, mock_client):
        from internal.routes.mailler import client_activate

        mock_client.update_client = AsyncMock(return_value={})

        result = await client_activate(MagicMock(), client_id="x", auth_result=_make_user())

        assert "did+not+answer" in result.headers["location"]

    async def test_redirect_auth(self):
        from internal.routes.mailler import client_activate, client_deactivate

        redirect = RedirectResponse(url="/login")
        assert await client_deactivate(MagicMock(), client_id="x", auth_result=redirect) is redirect
        assert await client_activate(MagicMock(), client_id="x", auth_result=redirect) is redirect


# ---------------------------------------------------------------------------
# Authorized clients: templates (rendered for real)
# ---------------------------------------------------------------------------


def _render(name, **context):
    from internal.routes.mailler import templates

    context.setdefault("user", _make_user())
    context.setdefault("active_section", "mailler")
    context.setdefault("request", MagicMock())
    return templates.get_template(f"admin/mailler/{name}").render(**context)


class TestClientTemplates:
    def _list(self, clients, **context):
        return _render(
            "clients.html",
            clients=clients,
            total=len(clients),
            page=1,
            pages=1,
            search=None,
            status_filter=None,
            success=None,
            error=None,
            **context,
        )

    def test_list_shows_the_records(self):
        html = self._list([_CLIENT])
        assert "app-one" in html
        assert "App one" in html
        assert "no-reply@example.test" in html
        assert "60/min" in html
        assert "https://app.example.test/status" in html
        assert "/mailler/clients/app-one/edit" in html
        assert "/mailler/clients/app-one/deactivate" in html

    def test_list_offers_activation_for_an_inactive_client(self):
        html = self._list([{**_CLIENT, "is_active": False, "callback_url": None}])
        assert "Inactive" in html
        assert "/mailler/clients/app-one/activate" in html
        assert "/deactivate" not in html

    def test_list_of_a_client_without_limits_or_sender(self):
        html = self._list(
            [
                {
                    **_CLIENT,
                    "from_email": None,
                    "rate_limit_per_minute": None,
                    "allowed_providers": [],
                }
            ]
        )
        assert "Unlimited" in html

    def test_list_escapes_the_client_id_in_urls(self):
        html = self._list([{**_CLIENT, "client_id": "a b"}])
        assert "/mailler/clients/a%20b/edit" in html

    def test_empty_list(self):
        html = self._list([])
        assert "No clients found." in html

    def test_empty_filtered_list_offers_to_clear_the_filters(self):
        html = _render(
            "clients.html",
            clients=[],
            total=0,
            page=1,
            pages=1,
            search="zzz",
            status_filter="active",
            success=None,
            error=None,
        )
        assert "Clear filters" in html

    def test_list_paginates_keeping_the_filters(self):
        html = _render(
            "clients.html",
            clients=[_CLIENT],
            total=40,
            page=2,
            pages=3,
            search="a b",
            status_filter="active",
            success="Saved",
            error="Oops",
        )
        assert "page=1&search=a%20b&status=active" in html
        assert "page=3&search=a%20b&status=active" in html
        assert "Saved" in html
        assert "Oops" in html

    def test_new_form(self):
        html = _render(
            "client_form.html", client=None, is_edit=False, providers=["one", "two"], error=None
        )
        assert 'action="/mailler/clients/new"' in html
        assert 'name="client_id"' in html
        assert 'name="allowed_providers" value="one"' in html
        assert 'name="allowed_providers" value="two"' in html
        assert "Register Client" in html

    def test_edit_form_shows_the_record(self):
        html = _render(
            "client_form.html",
            client=_CLIENT,
            is_edit=True,
            providers=["one", "two"],
            error=None,
        )
        assert 'action="/mailler/clients/app-one/edit"' in html
        assert 'value="no-reply@example.test"' in html
        assert 'value="60"' in html
        assert "other@example.test, Other" in html
        assert 'value="one" checked' in html
        assert '<option value="one" selected>' in html
        assert "A secret is set: leave empty to keep it" in html
        assert 'name="client_id"' not in html

    def test_edit_form_keeps_a_provider_the_service_no_longer_configures(self):
        client = {**_CLIENT, "allowed_providers": ["gone"], "default_provider": "gone"}
        html = _render(
            "client_form.html", client=client, is_edit=True, providers=["one"], error=None
        )
        assert 'value="gone" checked' in html
        assert "not configured on the service" in html

    def test_edit_form_of_an_inactive_client_leaves_the_box_unticked(self):
        client = {**_CLIENT, "is_active": False}
        html = _render("client_form.html", client=client, is_edit=True, providers=[], error=None)
        assert 'name="is_active" value="true" >' in html.replace("\n", " ").replace("  ", " ")

    def test_dashboard_links_to_the_clients_for_administrators_only(self):
        context = {
            "days": 30,
            "provider_filter": None,
            "stats": {"total": {}, "by_date": [], "by_provider": {}},
            "providers": [],
            "delivery_rate": 0,
            "bounce_rate": 0,
            "fail_rate": 0,
            "error": None,
        }
        admin = _render("dashboard.html", user=_make_user(scopes=["mailler:admin"]), **context)
        reader = _render("dashboard.html", user=_make_user(scopes=["mailler:read"]), **context)
        assert 'href="/mailler/clients"' in admin
        assert 'href="/mailler/clients"' not in reader


# ---------------------------------------------------------------------------
# Authorized clients: through the application (token exchange like production)
# ---------------------------------------------------------------------------


class TestClientsThroughTheApplication:
    async def test_an_administrator_manages_the_clients(self, tmp_path):
        from ..sidebar import running_app

        async with running_app(tmp_path) as env:
            mailler = env.client("mailler.mailler_client")
            mailler.list_clients.return_value = {
                "items": [_CLIENT],
                "total": 1,
                "page": 1,
                "pages": 1,
            }
            mailler.get_providers.return_value = ["one"]
            mailler.create_client.return_value = _CLIENT
            mailler.update_client.return_value = _CLIENT

            page = await env.get("/mailler/clients", ["mailler:*"])
            created = await env.post(
                "/mailler/clients/new", ["mailler:*"], {"client_id": "app-two", "is_active": "true"}
            )
            deactivated = await env.post("/mailler/clients/app-one/deactivate", ["mailler:*"])

        assert page.status_code == 200
        assert "app-one" in page.text
        assert created.status_code == 303
        assert "success=" in created.headers["location"]
        assert deactivated.status_code == 303
        mailler.update_client.assert_awaited_once_with("app-one", {"is_active": False})

    async def test_the_registry_needs_the_admin_scope(self, tmp_path):
        from ..sidebar import PAGES, prepare_page, running_app

        async with running_app(tmp_path) as env:
            mailler = env.client("mailler.mailler_client")
            scopes = ["mailler:read", "mailler:write", "mailler:delete"]

            listing = await env.get("/mailler/clients", scopes)
            form = await env.get("/mailler/clients/new", scopes)
            created = await env.post("/mailler/clients/new", scopes, {"client_id": "app-two"})
            deactivated = await env.post("/mailler/clients/app-one/deactivate", scopes)
            statistics = await env.get(await prepare_page(env, PAGES["mailler"][0]), scopes)

        assert [listing.status_code, form.status_code] == [403, 403]
        assert [created.status_code, deactivated.status_code] == [403, 403]
        assert statistics.status_code == 200
        assert 'href="/mailler/clients"' not in statistics.text
        mailler.list_clients.assert_not_awaited()
        mailler.create_client.assert_not_awaited()
        mailler.update_client.assert_not_awaited()
