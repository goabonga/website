# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for internal.routes.contacts — full coverage, fully mocked."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import RedirectResponse, StreamingResponse
from internal.auth.models import User
from internal.routes.contacts import (
    CONTACT_STATUSES,
    contact_create,
    contact_delete,
    contact_detail,
    contact_edit,
    contact_export,
    contact_import,
    contact_import_form,
    contact_new,
    contact_unsubscribe,
    contact_update,
    contacts_bulk_add_to_group,
    contacts_bulk_delete,
    contacts_list,
    parse_contacts,
    parse_datetime_fields,
    parse_groups,
)

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _make_user():
    return User(
        id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
        email="test@example.com",
        name="Test",
        scopes=["*"],
    )


def _make_request(**kwargs):
    req = MagicMock()
    req.query_params = kwargs.get("query_params", {})
    req.headers = kwargs.get("headers", {})
    return req


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------


class TestParseHelpers:
    """Tests for helper functions: parse_datetime_fields, parse_contacts, parse_groups."""

    def test_parse_datetime_fields_converts_iso_string(self):
        item = {"created_at": "2024-01-15T10:30:00Z", "name": "foo"}
        result = parse_datetime_fields(item, ["created_at"])
        assert isinstance(result["created_at"], datetime)
        assert result["name"] == "foo"

    def test_parse_datetime_fields_with_timezone_offset(self):
        item = {"created_at": "2024-01-15T10:30:00+02:00"}
        result = parse_datetime_fields(item, ["created_at"])
        assert isinstance(result["created_at"], datetime)

    def test_parse_datetime_fields_skips_non_string(self):
        dt = datetime(2024, 1, 15, tzinfo=UTC)
        item = {"created_at": dt}
        result = parse_datetime_fields(item, ["created_at"])
        assert result["created_at"] is dt  # unchanged

    def test_parse_datetime_fields_skips_missing_field(self):
        item = {"name": "foo"}
        result = parse_datetime_fields(item, ["created_at"])
        assert "created_at" not in result

    def test_parse_datetime_fields_skips_none_value(self):
        item = {"created_at": None}
        result = parse_datetime_fields(item, ["created_at"])
        assert result["created_at"] is None

    def test_parse_datetime_fields_skips_empty_string(self):
        item = {"created_at": ""}
        result = parse_datetime_fields(item, ["created_at"])
        assert result["created_at"] == ""

    def test_parse_datetime_fields_handles_invalid_datetime(self):
        item = {"created_at": "not-a-date"}
        result = parse_datetime_fields(item, ["created_at"])
        # Should suppress ValueError and leave value as-is
        assert result["created_at"] == "not-a-date"

    def test_parse_contacts(self):
        contacts = [
            {
                "email": "a@b.com",
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-02-01T12:00:00Z",
            },
            {"email": "c@d.com", "created_at": None, "updated_at": None},
        ]
        result = parse_contacts(contacts)
        assert len(result) == 2
        assert isinstance(result[0]["created_at"], datetime)
        assert result[1]["created_at"] is None

    def test_parse_contacts_empty_list(self):
        assert parse_contacts([]) == []

    def test_parse_groups(self):
        groups = [
            {
                "name": "g1",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-02T00:00:00Z",
            },
        ]
        result = parse_groups(groups)
        assert len(result) == 1
        assert isinstance(result[0]["created_at"], datetime)

    def test_parse_groups_empty_list(self):
        assert parse_groups([]) == []


class TestContactStatuses:
    """Test module-level CONTACT_STATUSES list."""

    def test_statuses_exist(self):
        assert CONTACT_STATUSES == ["active", "unsubscribed", "bounced", "complained"]


# ---------------------------------------------------------------------------
# Route handler tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestContactsList:
    @patch("internal.routes.contacts.mailler_client")
    @patch("internal.routes.contacts.templates")
    async def test_success(self, mock_templates, mock_mc):
        mock_mc.get_contacts = AsyncMock(
            return_value={
                "items": [
                    {"email": "a@b.com", "created_at": "2024-01-01T00:00:00Z", "updated_at": None}
                ],
                "total": 1,
                "pages": 1,
            }
        )
        mock_mc.get_contact_groups = AsyncMock(return_value={"items": [], "total": 0, "pages": 1})
        mock_templates.TemplateResponse.return_value = "ok"

        req = _make_request(query_params={})
        user = _make_user()

        result = await contacts_list(
            req, page=1, search=None, status=None, group=None, auth_result=user
        )
        assert result == "ok"
        mock_mc.get_contacts.assert_awaited_once()
        mock_mc.get_contact_groups.assert_awaited_once()
        mock_templates.TemplateResponse.assert_called_once()

    @patch("internal.routes.contacts.mailler_client")
    @patch("internal.routes.contacts.templates")
    async def test_with_filters(self, mock_templates, mock_mc):
        mock_mc.get_contacts = AsyncMock(return_value={"items": [], "total": 0, "pages": 1})
        mock_mc.get_contact_groups = AsyncMock(return_value={"items": [], "total": 0, "pages": 1})
        mock_templates.TemplateResponse.return_value = "ok"

        req = _make_request(query_params={"success": "done"})
        user = _make_user()

        result = await contacts_list(
            req, page=2, search="foo", status="active", group="5", auth_result=user
        )
        assert result == "ok"
        mock_mc.get_contacts.assert_awaited_once_with(
            page=2, page_size=50, status="active", search="foo", group_id=5
        )

    @patch("internal.routes.contacts.mailler_client")
    @patch("internal.routes.contacts.templates")
    async def test_invalid_status_filter(self, mock_templates, mock_mc):
        mock_mc.get_contacts = AsyncMock(return_value={"items": [], "total": 0, "pages": 1})
        mock_mc.get_contact_groups = AsyncMock(return_value={"items": [], "total": 0, "pages": 1})
        mock_templates.TemplateResponse.return_value = "ok"

        req = _make_request()
        user = _make_user()

        await contacts_list(
            req, page=1, search=None, status="invalid_status", group=None, auth_result=user
        )
        # Invalid status should be passed as None
        mock_mc.get_contacts.assert_awaited_once_with(
            page=1, page_size=50, status=None, search=None, group_id=None
        )

    @patch("internal.routes.contacts.mailler_client")
    @patch("internal.routes.contacts.templates")
    async def test_group_empty_string(self, mock_templates, mock_mc):
        mock_mc.get_contacts = AsyncMock(return_value={"items": [], "total": 0, "pages": 1})
        mock_mc.get_contact_groups = AsyncMock(return_value={"items": [], "total": 0, "pages": 1})
        mock_templates.TemplateResponse.return_value = "ok"

        req = _make_request()
        user = _make_user()

        await contacts_list(req, page=1, search=None, status=None, group="  ", auth_result=user)
        mock_mc.get_contacts.assert_awaited_once_with(
            page=1, page_size=50, status=None, search=None, group_id=None
        )

    @patch("internal.routes.contacts.mailler_client")
    @patch("internal.routes.contacts.templates")
    async def test_group_not_a_number(self, mock_templates, mock_mc):
        mock_mc.get_contacts = AsyncMock(return_value={"items": [], "total": 0, "pages": 1})
        mock_mc.get_contact_groups = AsyncMock(return_value={"items": [], "total": 0, "pages": 1})
        mock_templates.TemplateResponse.return_value = "ok"

        # A tampered address must not fail: the filter is ignored
        await contacts_list(
            _make_request(), page=1, search=None, status=None, group="abc", auth_result=_make_user()
        )
        mock_mc.get_contacts.assert_awaited_once_with(
            page=1, page_size=50, status=None, search=None, group_id=None
        )

    async def test_auth_redirect(self):
        redirect = RedirectResponse(url="/login")
        req = _make_request()

        result = await contacts_list(
            req, page=1, search=None, status=None, group=None, auth_result=redirect
        )
        assert result is redirect


@pytest.mark.asyncio
class TestContactNew:
    @patch("internal.routes.contacts.mailler_client")
    @patch("internal.routes.contacts.templates")
    async def test_success(self, mock_templates, mock_mc):
        mock_mc.get_contact_groups = AsyncMock(
            return_value={
                "items": [{"name": "g1", "created_at": "2024-01-01T00:00:00Z", "updated_at": None}],
            }
        )
        mock_templates.TemplateResponse.return_value = "ok"

        req = _make_request()
        user = _make_user()

        result = await contact_new(req, auth_result=user)
        assert result == "ok"
        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["contact"] is None
        assert ctx["is_edit"] is False

    @patch("internal.routes.contacts.mailler_client")
    @patch("internal.routes.contacts.templates")
    async def test_shows_the_error_of_a_failed_creation(self, mock_templates, mock_mc):
        mock_mc.get_contact_groups = AsyncMock(return_value={"items": []})
        mock_templates.TemplateResponse.return_value = "ok"

        req = _make_request(query_params={"error": "Failed to create contact"})

        await contact_new(req, auth_result=_make_user())
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["error"] == "Failed to create contact"

    async def test_auth_redirect(self):
        redirect = RedirectResponse(url="/login")
        req = _make_request()
        result = await contact_new(req, auth_result=redirect)
        assert result is redirect


@pytest.mark.asyncio
class TestContactCreate:
    @patch("internal.routes.contacts.mailler_client")
    async def test_success(self, mock_mc):
        mock_mc.create_contact = AsyncMock(return_value={"id": 42, "email": "new@test.com"})
        mock_mc.add_contacts_to_group = AsyncMock(return_value={"added": 1})

        req = _make_request()
        user = _make_user()

        result = await contact_create(
            req,
            email="  New@Test.Com  ",
            first_name="John",
            last_name="Doe",
            status="active",
            source="manual",
            group_ids=[1, 2],
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "success" in result.headers["location"]
        mock_mc.create_contact.assert_awaited_once()
        assert mock_mc.add_contacts_to_group.await_count == 2

    @patch("internal.routes.contacts.mailler_client")
    async def test_success_no_groups(self, mock_mc):
        mock_mc.create_contact = AsyncMock(return_value={"id": 42})

        req = _make_request()
        user = _make_user()

        result = await contact_create(
            req,
            email="a@b.com",
            first_name="",
            last_name="",
            status="active",
            source="",
            group_ids=[],
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers["location"]

    @patch("internal.routes.contacts.mailler_client")
    async def test_create_fails(self, mock_mc):
        mock_mc.create_contact = AsyncMock(return_value=None)

        req = _make_request()
        user = _make_user()

        result = await contact_create(
            req,
            email="a@b.com",
            first_name="",
            last_name="",
            status="active",
            source="",
            group_ids=[],
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "error" in result.headers["location"]

    @patch("internal.routes.contacts.mailler_client")
    async def test_invalid_status_defaults_to_active(self, mock_mc):
        mock_mc.create_contact = AsyncMock(return_value={"id": 1})

        req = _make_request()
        user = _make_user()

        await contact_create(
            req,
            email="a@b.com",
            first_name="",
            last_name="",
            status="INVALID",
            source="",
            group_ids=[],
            auth_result=user,
        )
        # Should still succeed with defaulted status
        mock_mc.create_contact.assert_awaited_once()

    async def test_auth_redirect(self):
        redirect = RedirectResponse(url="/login")
        req = _make_request()
        result = await contact_create(
            req,
            email="a@b.com",
            first_name="",
            last_name="",
            status="active",
            source="",
            group_ids=[],
            auth_result=redirect,
        )
        assert result is redirect

    @patch("internal.routes.contacts.mailler_client")
    async def test_create_returns_no_id(self, mock_mc):
        """Contact created but response has no id -- should not add to groups."""
        mock_mc.create_contact = AsyncMock(return_value={"email": "a@b.com"})
        mock_mc.add_contacts_to_group = AsyncMock()

        req = _make_request()
        user = _make_user()

        result = await contact_create(
            req,
            email="a@b.com",
            first_name="",
            last_name="",
            status="active",
            source="",
            group_ids=[1],
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers["location"]
        mock_mc.add_contacts_to_group.assert_not_awaited()


@pytest.mark.asyncio
class TestContactImportForm:
    @patch("internal.routes.contacts.templates")
    async def test_success(self, mock_templates):
        mock_templates.TemplateResponse.return_value = "ok"
        req = _make_request(query_params={"error": "something"})
        user = _make_user()

        result = await contact_import_form(req, auth_result=user)
        assert result == "ok"
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["error"] == "something"

    async def test_auth_redirect(self):
        redirect = RedirectResponse(url="/login")
        req = _make_request()
        result = await contact_import_form(req, auth_result=redirect)
        assert result is redirect


@pytest.mark.asyncio
class TestContactImport:
    @patch("internal.routes.contacts.mailler_client")
    async def test_success(self, mock_mc):
        mock_mc.create_contacts_bulk = AsyncMock(
            return_value={"created": 1, "skipped": 0, "failed": 0}
        )

        csv_bytes = b"email,first_name,last_name\ntest@test.com,Test,User\n"
        file = MagicMock(filename="contacts.csv", read=AsyncMock(return_value=csv_bytes))
        req = _make_request()
        user = _make_user()

        result = await contact_import(
            req,
            file=file,
            update_existing=False,
            source="csv_import",
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers["location"]
        assert "Imported" in result.headers["location"]
        mock_mc.create_contacts_bulk.assert_awaited_once()

    @patch("internal.routes.contacts.mailler_client")
    async def test_success_with_skipped_and_failed(self, mock_mc):
        mock_mc.create_contacts_bulk = AsyncMock(
            return_value={"created": 2, "skipped": 1, "failed": 3}
        )

        csv_bytes = b"email,first_name\na@b.com,A\nc@d.com,C\ne@f.com,E\n"
        file = MagicMock(filename="data.csv", read=AsyncMock(return_value=csv_bytes))
        req = _make_request()
        user = _make_user()

        result = await contact_import(
            req,
            file=file,
            update_existing=True,
            source="csv_import",
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        loc = result.headers["location"]
        assert "skipped" in loc
        assert "failed" in loc

    async def test_not_csv(self):
        file = MagicMock(filename="data.txt", read=AsyncMock())
        req = _make_request()
        user = _make_user()

        result = await contact_import(
            req, file=file, update_existing=False, source="", auth_result=user
        )
        assert isinstance(result, RedirectResponse)
        assert "error" in result.headers["location"]
        assert "CSV" in result.headers["location"]

    async def test_no_filename(self):
        file = MagicMock(filename=None, read=AsyncMock())
        req = _make_request()
        user = _make_user()

        result = await contact_import(
            req, file=file, update_existing=False, source="", auth_result=user
        )
        assert isinstance(result, RedirectResponse)
        assert "error" in result.headers["location"]

    @patch("internal.routes.contacts.mailler_client")
    async def test_empty_csv(self, mock_mc):
        csv_bytes = b"email,first_name\n"
        file = MagicMock(filename="empty.csv", read=AsyncMock(return_value=csv_bytes))
        req = _make_request()
        user = _make_user()

        result = await contact_import(
            req, file=file, update_existing=False, source="csv_import", auth_result=user
        )
        assert isinstance(result, RedirectResponse)
        assert "No+valid+contacts" in result.headers["location"]

    @patch("internal.routes.contacts.mailler_client")
    async def test_csv_with_empty_email_rows(self, mock_mc):
        """Rows with empty email should be skipped."""
        mock_mc.create_contacts_bulk = AsyncMock(
            return_value={"created": 1, "skipped": 0, "failed": 0}
        )
        csv_bytes = b"email,first_name\n,Empty\nvalid@email.com,Valid\n"
        file = MagicMock(filename="test.csv", read=AsyncMock(return_value=csv_bytes))
        req = _make_request()
        user = _make_user()

        result = await contact_import(
            req, file=file, update_existing=False, source="test", auth_result=user
        )
        assert isinstance(result, RedirectResponse)
        # Only 1 contact should have been sent (valid@email.com)
        call_args = mock_mc.create_contacts_bulk.call_args
        assert len(call_args[1]["contacts"]) == 1

    async def test_read_exception(self):
        file = MagicMock(
            filename="bad.csv",
            read=AsyncMock(side_effect=UnicodeDecodeError("utf-8", b"", 0, 1, "bad")),
        )
        req = _make_request()
        user = _make_user()

        result = await contact_import(
            req, file=file, update_existing=False, source="", auth_result=user
        )
        assert isinstance(result, RedirectResponse)
        assert "error" in result.headers["location"]
        assert "Import+failed" in result.headers["location"]

    async def test_auth_redirect(self):
        redirect = RedirectResponse(url="/login")
        file = MagicMock(filename="test.csv")
        req = _make_request()
        result = await contact_import(
            req, file=file, update_existing=False, source="", auth_result=redirect
        )
        assert result is redirect

    @patch("internal.routes.contacts.mailler_client")
    async def test_source_strip_empty(self, mock_mc):
        """Empty source should default to csv_import."""
        mock_mc.create_contacts_bulk = AsyncMock(
            return_value={"created": 1, "skipped": 0, "failed": 0}
        )
        csv_bytes = b"email\na@b.com\n"
        file = MagicMock(filename="test.csv", read=AsyncMock(return_value=csv_bytes))
        req = _make_request()
        user = _make_user()

        await contact_import(req, file=file, update_existing=False, source="  ", auth_result=user)
        call_args = mock_mc.create_contacts_bulk.call_args
        contacts = call_args[1]["contacts"]
        assert contacts[0]["source"] == "csv_import"


@pytest.mark.asyncio
class TestContactExport:
    @patch("internal.routes.contacts.mailler_client")
    async def test_success_no_group(self, mock_mc):
        mock_mc.get_contacts = AsyncMock(
            return_value={
                "items": [
                    {
                        "email": "a@b.com",
                        "first_name": "A",
                        "last_name": "B",
                        "status": "active",
                        "source": "manual",
                    }
                ],
                "total": 1,
                "pages": 1,
            }
        )

        req = _make_request()
        user = _make_user()

        result = await contact_export(req, group=None, auth_result=user)
        assert isinstance(result, StreamingResponse)
        assert "contacts.csv" in result.headers["content-disposition"]

    @patch("internal.routes.contacts.mailler_client")
    async def test_success_with_group(self, mock_mc):
        mock_mc.get_contacts = AsyncMock(
            return_value={
                "items": [
                    {
                        "email": "a@b.com",
                        "first_name": "",
                        "last_name": "",
                        "status": "active",
                        "source": "",
                    }
                ],
                "total": 1,
                "pages": 1,
            }
        )
        mock_mc.get_contact_group = AsyncMock(return_value={"slug": "vip", "name": "VIP"})

        req = _make_request()
        user = _make_user()

        result = await contact_export(req, group="3", auth_result=user)
        assert isinstance(result, StreamingResponse)
        assert "contacts_vip.csv" in result.headers["content-disposition"]

    @patch("internal.routes.contacts.mailler_client")
    async def test_export_with_group_not_found(self, mock_mc):
        mock_mc.get_contacts = AsyncMock(
            return_value={
                "items": [],
                "total": 0,
                "pages": 1,
            }
        )
        mock_mc.get_contact_group = AsyncMock(return_value=None)

        req = _make_request()
        user = _make_user()

        result = await contact_export(req, group="99", auth_result=user)
        assert isinstance(result, StreamingResponse)
        # Should use default filename since group not found
        assert "contacts.csv" in result.headers["content-disposition"]

    @patch("internal.routes.contacts.mailler_client")
    async def test_export_multiple_pages(self, mock_mc):
        """Pagination loop fetches all pages."""
        mock_mc.get_contacts = AsyncMock(
            side_effect=[
                {
                    "items": [
                        {
                            "email": "a@b.com",
                            "first_name": "",
                            "last_name": "",
                            "status": "",
                            "source": "",
                        }
                    ],
                    "total": 2,
                    "pages": 2,
                },
                {
                    "items": [
                        {
                            "email": "c@d.com",
                            "first_name": "",
                            "last_name": "",
                            "status": "",
                            "source": "",
                        }
                    ],
                    "total": 2,
                    "pages": 2,
                },
            ]
        )

        req = _make_request()
        user = _make_user()

        result = await contact_export(req, group=None, auth_result=user)
        assert isinstance(result, StreamingResponse)
        assert mock_mc.get_contacts.await_count == 2

    @patch("internal.routes.contacts.mailler_client")
    async def test_export_group_empty_string(self, mock_mc):
        mock_mc.get_contacts = AsyncMock(return_value={"items": [], "total": 0, "pages": 1})

        req = _make_request()
        user = _make_user()

        result = await contact_export(req, group="  ", auth_result=user)
        assert isinstance(result, StreamingResponse)
        assert "contacts.csv" in result.headers["content-disposition"]

    @patch("internal.routes.contacts.mailler_client")
    async def test_export_group_not_a_number(self, mock_mc):
        mock_mc.get_contacts = AsyncMock(return_value={"items": [], "total": 0, "pages": 1})

        result = await contact_export(_make_request(), group="abc", auth_result=_make_user())
        assert isinstance(result, StreamingResponse)
        assert mock_mc.get_contacts.await_args.kwargs["group_id"] is None

    async def test_auth_redirect(self):
        redirect = RedirectResponse(url="/login")
        req = _make_request()
        result = await contact_export(req, group=None, auth_result=redirect)
        assert result is redirect


@pytest.mark.asyncio
class TestContactDetail:
    @patch("internal.routes.contacts.mailler_client")
    @patch("internal.routes.contacts.templates")
    async def test_success(self, mock_templates, mock_mc):
        mock_mc.get_contact = AsyncMock(
            return_value={
                "id": "abc",
                "email": "a@b.com",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": None,
            }
        )
        mock_templates.TemplateResponse.return_value = "ok"

        req = _make_request(query_params={"success": "done"})
        user = _make_user()

        result = await contact_detail(req, contact_id="abc", auth_result=user)
        assert result == "ok"

    @patch("internal.routes.contacts.mailler_client")
    async def test_not_found(self, mock_mc):
        mock_mc.get_contact = AsyncMock(return_value=None)

        req = _make_request()
        user = _make_user()

        result = await contact_detail(req, contact_id="nonexistent", auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "error" in result.headers["location"]
        assert "not+found" in result.headers["location"]

    async def test_auth_redirect(self):
        redirect = RedirectResponse(url="/login")
        req = _make_request()
        result = await contact_detail(req, contact_id="abc", auth_result=redirect)
        assert result is redirect


@pytest.mark.asyncio
class TestContactEdit:
    @patch("internal.routes.contacts.mailler_client")
    @patch("internal.routes.contacts.templates")
    async def test_success(self, mock_templates, mock_mc):
        mock_mc.get_contact = AsyncMock(
            return_value={
                "id": "abc",
                "email": "a@b.com",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": None,
                "groups": [{"id": 1, "name": "g1"}, {"id": 2, "name": "g2"}],
            }
        )
        mock_mc.get_contact_groups = AsyncMock(
            return_value={
                "items": [{"name": "g1", "created_at": None, "updated_at": None}],
            }
        )
        mock_templates.TemplateResponse.return_value = "ok"

        req = _make_request()
        user = _make_user()

        result = await contact_edit(req, contact_id="abc", auth_result=user)
        assert result == "ok"
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["is_edit"] is True
        assert ctx["current_group_ids"] == [1, 2]

    @patch("internal.routes.contacts.mailler_client")
    @patch("internal.routes.contacts.templates")
    async def test_shows_the_error_of_a_failed_update(self, mock_templates, mock_mc):
        mock_mc.get_contact = AsyncMock(
            return_value={"id": "abc", "email": "a@b.com", "created_at": None, "groups": []}
        )
        mock_mc.get_contact_groups = AsyncMock(return_value={"items": []})
        mock_templates.TemplateResponse.return_value = "ok"

        req = _make_request(query_params={"error": "Failed to update contact"})

        await contact_edit(req, contact_id="abc", auth_result=_make_user())
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["error"] == "Failed to update contact"

    @patch("internal.routes.contacts.mailler_client")
    async def test_not_found(self, mock_mc):
        mock_mc.get_contact = AsyncMock(return_value=None)

        req = _make_request()
        user = _make_user()

        result = await contact_edit(req, contact_id="nope", auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "error" in result.headers["location"]

    async def test_auth_redirect(self):
        redirect = RedirectResponse(url="/login")
        req = _make_request()
        result = await contact_edit(req, contact_id="abc", auth_result=redirect)
        assert result is redirect

    @patch("internal.routes.contacts.mailler_client")
    @patch("internal.routes.contacts.templates")
    async def test_groups_with_no_id(self, mock_templates, mock_mc):
        """Groups without an id key should be filtered out."""
        mock_mc.get_contact = AsyncMock(
            return_value={
                "id": "abc",
                "email": "a@b.com",
                "created_at": None,
                "updated_at": None,
                "groups": [{"name": "g1"}, {"id": 5, "name": "g2"}],
            }
        )
        mock_mc.get_contact_groups = AsyncMock(return_value={"items": []})
        mock_templates.TemplateResponse.return_value = "ok"

        req = _make_request()
        user = _make_user()

        await contact_edit(req, contact_id="abc", auth_result=user)
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["current_group_ids"] == [5]


@pytest.mark.asyncio
class TestContactUpdate:
    @patch("internal.routes.contacts.mailler_client")
    async def test_success(self, mock_mc):
        mock_mc.get_contact = AsyncMock(
            return_value={
                "id": "abc",
                "groups": [{"id": 1, "name": "g1"}, {"id": 2, "name": "g2"}],
            }
        )
        mock_mc.update_contact = AsyncMock(return_value={"id": "abc"})
        mock_mc.remove_contacts_from_group = AsyncMock()
        mock_mc.add_contacts_to_group = AsyncMock()

        req = _make_request()
        user = _make_user()

        result = await contact_update(
            req,
            contact_id="abc",
            first_name="John",
            last_name="Doe",
            status="active",
            source="manual",
            group_ids=[2, 3],
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers["location"]
        # Should remove from group 1, add to group 3
        mock_mc.remove_contacts_from_group.assert_awaited_once_with(1, ["abc"])
        mock_mc.add_contacts_to_group.assert_awaited_once_with(3, ["abc"])

    @patch("internal.routes.contacts.mailler_client")
    async def test_contact_not_found(self, mock_mc):
        mock_mc.get_contact = AsyncMock(return_value=None)

        req = _make_request()
        user = _make_user()

        result = await contact_update(
            req,
            contact_id="abc",
            first_name="",
            last_name="",
            status="active",
            source="",
            group_ids=[],
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "not+found" in result.headers["location"]

    @patch("internal.routes.contacts.mailler_client")
    async def test_update_fails(self, mock_mc):
        mock_mc.get_contact = AsyncMock(return_value={"id": "abc", "groups": []})
        mock_mc.update_contact = AsyncMock(return_value=None)

        req = _make_request()
        user = _make_user()

        result = await contact_update(
            req,
            contact_id="abc",
            first_name="",
            last_name="",
            status="active",
            source="",
            group_ids=[],
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "error" in result.headers["location"]
        assert "Failed" in result.headers["location"]

    @patch("internal.routes.contacts.mailler_client")
    async def test_invalid_status(self, mock_mc):
        mock_mc.get_contact = AsyncMock(return_value={"id": "abc", "groups": []})
        mock_mc.update_contact = AsyncMock(return_value={"id": "abc"})

        req = _make_request()
        user = _make_user()

        await contact_update(
            req,
            contact_id="abc",
            first_name="",
            last_name="",
            status="INVALID",
            source="",
            group_ids=[],
            auth_result=user,
        )
        call_data = mock_mc.update_contact.call_args[0][1]
        assert call_data["status"] == "active"

    async def test_auth_redirect(self):
        redirect = RedirectResponse(url="/login")
        req = _make_request()
        result = await contact_update(
            req,
            contact_id="abc",
            first_name="",
            last_name="",
            status="active",
            source="",
            group_ids=[],
            auth_result=redirect,
        )
        assert result is redirect

    @patch("internal.routes.contacts.mailler_client")
    async def test_no_group_changes(self, mock_mc):
        """Same groups before and after -- no add/remove calls."""
        mock_mc.get_contact = AsyncMock(return_value={"id": "abc", "groups": [{"id": 1}]})
        mock_mc.update_contact = AsyncMock(return_value={"id": "abc"})
        mock_mc.remove_contacts_from_group = AsyncMock()
        mock_mc.add_contacts_to_group = AsyncMock()

        req = _make_request()
        user = _make_user()

        await contact_update(
            req,
            contact_id="abc",
            first_name="",
            last_name="",
            status="active",
            source="",
            group_ids=[1],
            auth_result=user,
        )
        mock_mc.remove_contacts_from_group.assert_not_awaited()
        mock_mc.add_contacts_to_group.assert_not_awaited()


@pytest.mark.asyncio
class TestContactUnsubscribe:
    @patch("internal.routes.contacts.mailler_client")
    async def test_success(self, mock_mc):
        mock_mc.unsubscribe_contact = AsyncMock(return_value={"status": "unsubscribed"})

        req = _make_request()
        user = _make_user()

        result = await contact_unsubscribe(req, contact_id="abc", auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers["location"]

    @patch("internal.routes.contacts.mailler_client")
    async def test_not_found(self, mock_mc):
        mock_mc.unsubscribe_contact = AsyncMock(return_value=None)

        req = _make_request()
        user = _make_user()

        result = await contact_unsubscribe(req, contact_id="nonexistent", auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "error" in result.headers["location"]

    async def test_auth_redirect(self):
        redirect = RedirectResponse(url="/login")
        req = _make_request()
        result = await contact_unsubscribe(req, contact_id="abc", auth_result=redirect)
        assert result is redirect


@pytest.mark.asyncio
class TestContactDelete:
    @patch("internal.routes.contacts.mailler_client")
    async def test_success(self, mock_mc):
        mock_mc.delete_contact = AsyncMock(return_value=True)

        req = _make_request()
        user = _make_user()

        result = await contact_delete(req, contact_id="abc", auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers["location"]

    @patch("internal.routes.contacts.mailler_client")
    async def test_fails(self, mock_mc):
        mock_mc.delete_contact = AsyncMock(return_value=False)

        req = _make_request()
        user = _make_user()

        result = await contact_delete(req, contact_id="abc", auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "error" in result.headers["location"]

    async def test_auth_redirect(self):
        redirect = RedirectResponse(url="/login")
        req = _make_request()
        result = await contact_delete(req, contact_id="abc", auth_result=redirect)
        assert result is redirect


@pytest.mark.asyncio
class TestContactsBulkDelete:
    @patch("internal.routes.contacts.mailler_client")
    async def test_success(self, mock_mc):
        mock_mc.delete_contact = AsyncMock(return_value=True)

        form = MagicMock()
        form.get = MagicMock(
            side_effect=lambda key, default="": "id1,id2,id3" if key == "contact_ids" else default
        )

        req = _make_request()
        req.form = AsyncMock(return_value=form)
        user = _make_user()

        result = await contacts_bulk_delete(req, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "3+contact(s)+deleted" in result.headers["location"]

    @patch("internal.routes.contacts.mailler_client")
    async def test_partial_delete(self, mock_mc):
        mock_mc.delete_contact = AsyncMock(side_effect=[True, False])

        form = MagicMock()
        form.get = MagicMock(
            side_effect=lambda key, default="": "id1,id2" if key == "contact_ids" else default
        )

        req = _make_request()
        req.form = AsyncMock(return_value=form)
        user = _make_user()

        result = await contacts_bulk_delete(req, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "1+contact(s)+deleted" in result.headers["location"]

    @patch("internal.routes.contacts.mailler_client")
    async def test_empty_ids(self, mock_mc):
        form = MagicMock()
        form.get = MagicMock(return_value="")

        req = _make_request()
        req.form = AsyncMock(return_value=form)
        user = _make_user()

        result = await contacts_bulk_delete(req, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "error" in result.headers["location"]
        assert "No+contacts+selected" in result.headers["location"]

    @patch("internal.routes.contacts.mailler_client")
    async def test_whitespace_only_ids(self, mock_mc):
        form = MagicMock()
        form.get = MagicMock(return_value=" , , ")

        req = _make_request()
        req.form = AsyncMock(return_value=form)
        user = _make_user()

        result = await contacts_bulk_delete(req, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "No+contacts+selected" in result.headers["location"]

    async def test_auth_redirect(self):
        redirect = RedirectResponse(url="/login")
        req = _make_request()
        result = await contacts_bulk_delete(req, auth_result=redirect)
        assert result is redirect


@pytest.mark.asyncio
class TestContactsBulkAddToGroup:
    @patch("internal.routes.contacts.mailler_client")
    async def test_success(self, mock_mc):
        mock_mc.add_contacts_to_group = AsyncMock(return_value={"added": 2})

        form = MagicMock()
        form.get = MagicMock(
            side_effect=lambda key, default="": {
                "contact_ids": "id1,id2",
                "group_id": "5",
            }.get(key, default)
        )

        req = _make_request()
        req.form = AsyncMock(return_value=form)
        user = _make_user()

        result = await contacts_bulk_add_to_group(req, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "2+contact(s)+added+to+group" in result.headers["location"]
        mock_mc.add_contacts_to_group.assert_awaited_once_with(5, ["id1", "id2"])

    @patch("internal.routes.contacts.mailler_client")
    async def test_missing_contact_ids(self, mock_mc):
        form = MagicMock()
        form.get = MagicMock(
            side_effect=lambda key, default="": {
                "contact_ids": "",
                "group_id": "5",
            }.get(key, default)
        )

        req = _make_request()
        req.form = AsyncMock(return_value=form)
        user = _make_user()

        result = await contacts_bulk_add_to_group(req, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "Missing+contacts+or+group" in result.headers["location"]

    @patch("internal.routes.contacts.mailler_client")
    async def test_missing_group_id(self, mock_mc):
        form = MagicMock()
        form.get = MagicMock(
            side_effect=lambda key, default="": {
                "contact_ids": "id1",
                "group_id": "",
            }.get(key, default)
        )

        req = _make_request()
        req.form = AsyncMock(return_value=form)
        user = _make_user()

        result = await contacts_bulk_add_to_group(req, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "Missing+contacts+or+group" in result.headers["location"]

    @patch("internal.routes.contacts.mailler_client")
    async def test_invalid_group_id(self, mock_mc):
        form = MagicMock()
        form.get = MagicMock(
            side_effect=lambda key, default="": {
                "contact_ids": "id1",
                "group_id": "not_a_number",
            }.get(key, default)
        )

        req = _make_request()
        req.form = AsyncMock(return_value=form)
        user = _make_user()

        result = await contacts_bulk_add_to_group(req, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "Invalid+IDs" in result.headers["location"]

    async def test_auth_redirect(self):
        redirect = RedirectResponse(url="/login")
        req = _make_request()
        result = await contacts_bulk_add_to_group(req, auth_result=redirect)
        assert result is redirect
