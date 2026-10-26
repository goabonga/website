# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for internal.routes.contact_groups — full coverage, fully mocked."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import RedirectResponse
from internal.auth.models import User
from internal.routes.contact_groups import (
    contact_group_add_contacts,
    contact_group_add_contacts_form,
    contact_group_bulk_delete,
    contact_group_create,
    contact_group_delete,
    contact_group_detail,
    contact_group_edit,
    contact_group_new,
    contact_group_remove_contacts,
    contact_group_update,
    contact_groups_list,
    generate_slug,
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
    """Tests for parse_datetime_fields, parse_contacts, parse_groups."""

    def test_parse_datetime_fields_converts_iso_string(self):
        item = {"created_at": "2024-01-15T10:30:00Z", "name": "foo"}
        result = parse_datetime_fields(item, ["created_at"])
        assert isinstance(result["created_at"], datetime)
        assert result["name"] == "foo"

    def test_parse_datetime_fields_with_timezone(self):
        item = {"updated_at": "2024-06-01T08:00:00+03:00"}
        result = parse_datetime_fields(item, ["updated_at"])
        assert isinstance(result["updated_at"], datetime)

    def test_parse_datetime_fields_skips_non_string(self):
        dt = datetime(2024, 1, 15, tzinfo=UTC)
        item = {"created_at": dt}
        result = parse_datetime_fields(item, ["created_at"])
        assert result["created_at"] is dt

    def test_parse_datetime_fields_skips_missing_field(self):
        item = {"name": "foo"}
        result = parse_datetime_fields(item, ["created_at"])
        assert "created_at" not in result

    def test_parse_datetime_fields_skips_none(self):
        item = {"created_at": None}
        result = parse_datetime_fields(item, ["created_at"])
        assert result["created_at"] is None

    def test_parse_datetime_fields_skips_empty_string(self):
        item = {"created_at": ""}
        result = parse_datetime_fields(item, ["created_at"])
        assert result["created_at"] == ""

    def test_parse_datetime_fields_handles_invalid(self):
        item = {"created_at": "not-a-date"}
        result = parse_datetime_fields(item, ["created_at"])
        assert result["created_at"] == "not-a-date"

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

    def test_parse_groups_empty(self):
        assert parse_groups([]) == []

    def test_parse_contacts(self):
        contacts = [
            {"email": "a@b.com", "created_at": "2024-01-01T00:00:00Z", "updated_at": None},
        ]
        result = parse_contacts(contacts)
        assert len(result) == 1
        assert isinstance(result[0]["created_at"], datetime)

    def test_parse_contacts_empty(self):
        assert parse_contacts([]) == []


class TestGenerateSlug:
    def test_basic_name(self):
        assert generate_slug("My Group") == "my-group"

    def test_special_characters(self):
        assert generate_slug("Hello! World@2024") == "hello-world2024"

    def test_multiple_spaces_and_dashes(self):
        assert generate_slug("  a -- b   c  ") == "a-b-c"

    def test_long_name_truncated(self):
        name = "a" * 200
        slug = generate_slug(name)
        assert len(slug) <= 100

    def test_empty_string(self):
        assert generate_slug("") == ""

    def test_only_special_chars(self):
        assert generate_slug("!@#$%") == ""

    def test_preserves_underscores(self):
        assert generate_slug("my_group_name") == "my_group_name"

    def test_strip_whitespace(self):
        assert generate_slug("  hello  ") == "hello"


# ---------------------------------------------------------------------------
# Route handler tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestContactGroupsList:
    @patch("internal.routes.contact_groups.mailler_client")
    @patch("internal.routes.contact_groups.templates")
    async def test_success(self, mock_templates, mock_mc):
        mock_mc.get_contact_groups = AsyncMock(
            return_value={
                "items": [{"name": "g1", "created_at": "2024-01-01T00:00:00Z", "updated_at": None}],
                "total": 1,
                "pages": 1,
            }
        )
        mock_templates.TemplateResponse.return_value = "ok"

        req = _make_request(query_params={})
        user = _make_user()

        result = await contact_groups_list(req, page=1, search=None, auth_result=user)
        assert result == "ok"
        mock_mc.get_contact_groups.assert_awaited_once_with(page=1, page_size=20, search=None)

    @patch("internal.routes.contact_groups.mailler_client")
    @patch("internal.routes.contact_groups.templates")
    async def test_with_search(self, mock_templates, mock_mc):
        mock_mc.get_contact_groups = AsyncMock(return_value={"items": [], "total": 0, "pages": 1})
        mock_templates.TemplateResponse.return_value = "ok"

        req = _make_request(query_params={"success": "created", "error": None})
        user = _make_user()

        result = await contact_groups_list(req, page=2, search="test", auth_result=user)
        assert result == "ok"
        mock_mc.get_contact_groups.assert_awaited_once_with(page=2, page_size=20, search="test")

    @patch("internal.routes.contact_groups.mailler_client")
    @patch("internal.routes.contact_groups.templates")
    async def test_template_context(self, mock_templates, mock_mc):
        mock_mc.get_contact_groups = AsyncMock(
            return_value={
                "items": [],
                "total": 5,
                "pages": 3,
            }
        )
        mock_templates.TemplateResponse.return_value = "ok"

        req = _make_request(query_params={"success": "yes"})
        user = _make_user()

        await contact_groups_list(req, page=2, search="q", auth_result=user)
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["total"] == 5
        assert ctx["total_pages"] == 3
        assert ctx["page"] == 2
        assert ctx["search"] == "q"

    async def test_auth_redirect(self):
        redirect = RedirectResponse(url="/login")
        req = _make_request()
        result = await contact_groups_list(req, page=1, search=None, auth_result=redirect)
        assert result is redirect


@pytest.mark.asyncio
class TestContactGroupNew:
    @patch("internal.routes.contact_groups.templates")
    async def test_success(self, mock_templates):
        mock_templates.TemplateResponse.return_value = "ok"

        req = _make_request()
        user = _make_user()

        result = await contact_group_new(req, auth_result=user)
        assert result == "ok"
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["group"] is None
        assert ctx["is_edit"] is False

    @patch("internal.routes.contact_groups.templates")
    async def test_shows_the_error_of_a_failed_creation(self, mock_templates):
        mock_templates.TemplateResponse.return_value = "ok"

        req = _make_request(query_params={"error": "Failed to create group"})

        await contact_group_new(req, auth_result=_make_user())
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["error"] == "Failed to create group"

    async def test_auth_redirect(self):
        redirect = RedirectResponse(url="/login")
        req = _make_request()
        result = await contact_group_new(req, auth_result=redirect)
        assert result is redirect


@pytest.mark.asyncio
class TestContactGroupCreate:
    @patch("internal.routes.contact_groups.mailler_client")
    async def test_success(self, mock_mc):
        mock_mc.create_contact_group = AsyncMock(return_value={"id": 1, "slug": "vip"})

        req = _make_request()
        user = _make_user()

        result = await contact_group_create(
            req,
            name="VIP",
            slug="vip",
            description="VIP contacts",
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers["location"]
        mock_mc.create_contact_group.assert_awaited_once_with(
            {
                "slug": "vip",
                "name": "VIP",
                "description": "VIP contacts",
            }
        )

    @patch("internal.routes.contact_groups.mailler_client")
    async def test_auto_slug(self, mock_mc):
        mock_mc.create_contact_group = AsyncMock(return_value={"id": 2, "slug": "my-group"})

        req = _make_request()
        user = _make_user()

        result = await contact_group_create(
            req,
            name="My Group",
            slug="",
            description="",
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers["location"]
        call_data = mock_mc.create_contact_group.call_args[0][0]
        assert call_data["slug"] == "my-group"
        assert call_data["description"] is None

    @patch("internal.routes.contact_groups.mailler_client")
    async def test_create_fails(self, mock_mc):
        mock_mc.create_contact_group = AsyncMock(return_value=None)

        req = _make_request()
        user = _make_user()

        result = await contact_group_create(
            req,
            name="Fail",
            slug="",
            description="",
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "error" in result.headers["location"]

    async def test_auth_redirect(self):
        redirect = RedirectResponse(url="/login")
        req = _make_request()
        result = await contact_group_create(
            req,
            name="X",
            slug="",
            description="",
            auth_result=redirect,
        )
        assert result is redirect


@pytest.mark.asyncio
class TestContactGroupDetail:
    @patch("internal.routes.contact_groups.mailler_client")
    @patch("internal.routes.contact_groups.templates")
    async def test_success(self, mock_templates, mock_mc):
        mock_mc.get_contact_group = AsyncMock(
            return_value={
                "id": 1,
                "name": "g1",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": None,
            }
        )
        mock_mc.get_group_contacts = AsyncMock(
            return_value={
                "items": [{"email": "a@b.com", "created_at": None, "updated_at": None}],
                "total": 1,
                "pages": 1,
            }
        )
        mock_templates.TemplateResponse.return_value = "ok"

        req = _make_request(query_params={"success": "added"})
        user = _make_user()

        result = await contact_group_detail(req, group_id=1, page=1, search=None, auth_result=user)
        assert result == "ok"

    @patch("internal.routes.contact_groups.mailler_client")
    @patch("internal.routes.contact_groups.templates")
    async def test_with_search_and_pagination(self, mock_templates, mock_mc):
        mock_mc.get_contact_group = AsyncMock(
            return_value={
                "id": 1,
                "name": "g1",
                "created_at": None,
                "updated_at": None,
            }
        )
        mock_mc.get_group_contacts = AsyncMock(
            return_value={
                "items": [],
                "total": 100,
                "pages": 5,
            }
        )
        mock_templates.TemplateResponse.return_value = "ok"

        req = _make_request()
        user = _make_user()

        await contact_group_detail(req, group_id=1, page=3, search="q", auth_result=user)
        mock_mc.get_group_contacts.assert_awaited_once_with(
            group_id=1,
            page=3,
            page_size=50,
            search="q",
        )
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["total_members"] == 100
        assert ctx["total_pages"] == 5
        assert ctx["search"] == "q"

    @patch("internal.routes.contact_groups.mailler_client")
    async def test_not_found(self, mock_mc):
        mock_mc.get_contact_group = AsyncMock(return_value=None)

        req = _make_request()
        user = _make_user()

        result = await contact_group_detail(
            req, group_id=999, page=1, search=None, auth_result=user
        )
        assert isinstance(result, RedirectResponse)
        assert "not+found" in result.headers["location"]

    async def test_auth_redirect(self):
        redirect = RedirectResponse(url="/login")
        req = _make_request()
        result = await contact_group_detail(
            req, group_id=1, page=1, search=None, auth_result=redirect
        )
        assert result is redirect


@pytest.mark.asyncio
class TestContactGroupEdit:
    @patch("internal.routes.contact_groups.mailler_client")
    @patch("internal.routes.contact_groups.templates")
    async def test_success(self, mock_templates, mock_mc):
        mock_mc.get_contact_group = AsyncMock(
            return_value={
                "id": 1,
                "name": "g1",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": None,
            }
        )
        mock_templates.TemplateResponse.return_value = "ok"

        req = _make_request()
        user = _make_user()

        result = await contact_group_edit(req, group_id=1, auth_result=user)
        assert result == "ok"
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["is_edit"] is True
        assert ctx["group"]["name"] == "g1"

    @patch("internal.routes.contact_groups.mailler_client")
    @patch("internal.routes.contact_groups.templates")
    async def test_shows_the_error_of_a_failed_update(self, mock_templates, mock_mc):
        mock_mc.get_contact_group = AsyncMock(
            return_value={"id": 1, "name": "g1", "created_at": None, "updated_at": None}
        )
        mock_templates.TemplateResponse.return_value = "ok"

        req = _make_request(query_params={"error": "Failed to update group"})

        await contact_group_edit(req, group_id=1, auth_result=_make_user())
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["error"] == "Failed to update group"

    @patch("internal.routes.contact_groups.mailler_client")
    async def test_not_found(self, mock_mc):
        mock_mc.get_contact_group = AsyncMock(return_value=None)

        req = _make_request()
        user = _make_user()

        result = await contact_group_edit(req, group_id=999, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "not+found" in result.headers["location"]

    async def test_auth_redirect(self):
        redirect = RedirectResponse(url="/login")
        req = _make_request()
        result = await contact_group_edit(req, group_id=1, auth_result=redirect)
        assert result is redirect


@pytest.mark.asyncio
class TestContactGroupUpdate:
    @patch("internal.routes.contact_groups.mailler_client")
    async def test_success(self, mock_mc):
        mock_mc.get_contact_group = AsyncMock(return_value={"id": 1, "name": "old"})
        mock_mc.update_contact_group = AsyncMock(return_value={"id": 1, "name": "new"})

        req = _make_request()
        user = _make_user()

        result = await contact_group_update(
            req,
            group_id=1,
            name="new",
            slug="new-slug",
            description="desc",
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers["location"]
        mock_mc.update_contact_group.assert_awaited_once_with(
            1,
            {
                "name": "new",
                "slug": "new-slug",
                "description": "desc",
            },
        )

    @patch("internal.routes.contact_groups.mailler_client")
    async def test_auto_slug(self, mock_mc):
        mock_mc.get_contact_group = AsyncMock(return_value={"id": 1})
        mock_mc.update_contact_group = AsyncMock(return_value={"id": 1})

        req = _make_request()
        user = _make_user()

        await contact_group_update(
            req,
            group_id=1,
            name="New Name",
            slug="",
            description="",
            auth_result=user,
        )
        call_data = mock_mc.update_contact_group.call_args[0][1]
        assert call_data["slug"] == "new-name"
        assert call_data["description"] is None

    @patch("internal.routes.contact_groups.mailler_client")
    async def test_group_not_found(self, mock_mc):
        mock_mc.get_contact_group = AsyncMock(return_value=None)

        req = _make_request()
        user = _make_user()

        result = await contact_group_update(
            req,
            group_id=999,
            name="x",
            slug="",
            description="",
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "not+found" in result.headers["location"]

    @patch("internal.routes.contact_groups.mailler_client")
    async def test_update_fails(self, mock_mc):
        mock_mc.get_contact_group = AsyncMock(return_value={"id": 1})
        mock_mc.update_contact_group = AsyncMock(return_value=None)

        req = _make_request()
        user = _make_user()

        result = await contact_group_update(
            req,
            group_id=1,
            name="x",
            slug="",
            description="",
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "error" in result.headers["location"]
        assert "Failed" in result.headers["location"]

    async def test_auth_redirect(self):
        redirect = RedirectResponse(url="/login")
        req = _make_request()
        result = await contact_group_update(
            req,
            group_id=1,
            name="x",
            slug="",
            description="",
            auth_result=redirect,
        )
        assert result is redirect


@pytest.mark.asyncio
class TestContactGroupAddContactsForm:
    @patch("internal.routes.contact_groups.mailler_client")
    @patch("internal.routes.contact_groups.templates")
    async def test_success(self, mock_templates, mock_mc):
        mock_mc.get_contact_group = AsyncMock(
            return_value={
                "id": 1,
                "name": "g1",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": None,
            }
        )
        mock_mc.get_contacts_not_in_group = AsyncMock(
            return_value={
                "items": [{"email": "new@b.com", "created_at": None, "updated_at": None}],
                "total": 1,
                "pages": 1,
            }
        )
        mock_templates.TemplateResponse.return_value = "ok"

        req = _make_request()
        user = _make_user()

        result = await contact_group_add_contacts_form(
            req,
            group_id=1,
            page=1,
            search=None,
            auth_result=user,
        )
        assert result == "ok"

    @patch("internal.routes.contact_groups.mailler_client")
    @patch("internal.routes.contact_groups.templates")
    async def test_with_search_and_pagination(self, mock_templates, mock_mc):
        mock_mc.get_contact_group = AsyncMock(
            return_value={
                "id": 1,
                "name": "g1",
                "created_at": None,
                "updated_at": None,
            }
        )
        mock_mc.get_contacts_not_in_group = AsyncMock(
            return_value={
                "items": [],
                "total": 50,
                "pages": 3,
            }
        )
        mock_templates.TemplateResponse.return_value = "ok"

        req = _make_request()
        user = _make_user()

        await contact_group_add_contacts_form(
            req,
            group_id=1,
            page=2,
            search="foo",
            auth_result=user,
        )
        mock_mc.get_contacts_not_in_group.assert_awaited_once_with(
            group_id=1,
            page=2,
            page_size=50,
            search="foo",
        )
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["total"] == 50
        assert ctx["total_pages"] == 3

    @patch("internal.routes.contact_groups.mailler_client")
    @patch("internal.routes.contact_groups.templates")
    async def test_shows_the_error_of_a_refused_addition(self, mock_templates, mock_mc):
        mock_mc.get_contact_group = AsyncMock(
            return_value={"id": 1, "name": "g1", "created_at": None, "updated_at": None}
        )
        mock_mc.get_contacts_not_in_group = AsyncMock(
            return_value={"items": [], "total": 0, "pages": 1}
        )
        mock_templates.TemplateResponse.return_value = "ok"

        req = _make_request(query_params={"error": "No contacts selected"})

        await contact_group_add_contacts_form(
            req, group_id=1, page=1, search=None, auth_result=_make_user()
        )
        ctx = mock_templates.TemplateResponse.call_args[1]["context"]
        assert ctx["error"] == "No contacts selected"

    @patch("internal.routes.contact_groups.mailler_client")
    async def test_group_not_found(self, mock_mc):
        mock_mc.get_contact_group = AsyncMock(return_value=None)

        req = _make_request()
        user = _make_user()

        result = await contact_group_add_contacts_form(
            req,
            group_id=999,
            page=1,
            search=None,
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "not+found" in result.headers["location"]

    async def test_auth_redirect(self):
        redirect = RedirectResponse(url="/login")
        req = _make_request()
        result = await contact_group_add_contacts_form(
            req,
            group_id=1,
            page=1,
            search=None,
            auth_result=redirect,
        )
        assert result is redirect


@pytest.mark.asyncio
class TestContactGroupAddContacts:
    @patch("internal.routes.contact_groups.mailler_client")
    async def test_success(self, mock_mc):
        mock_mc.add_contacts_to_group = AsyncMock(return_value={"added": 3})

        form = MagicMock()
        form.get = MagicMock(
            side_effect=lambda key, default="": "id1,id2,id3" if key == "contact_ids" else default
        )

        req = _make_request()
        req.form = AsyncMock(return_value=form)
        user = _make_user()

        result = await contact_group_add_contacts(req, group_id=1, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "3+contact(s)+added" in result.headers["location"]
        mock_mc.add_contacts_to_group.assert_awaited_once_with(1, ["id1", "id2", "id3"])

    @patch("internal.routes.contact_groups.mailler_client")
    async def test_empty_contact_ids(self, mock_mc):
        form = MagicMock()
        form.get = MagicMock(return_value="")

        req = _make_request()
        req.form = AsyncMock(return_value=form)
        user = _make_user()

        result = await contact_group_add_contacts(req, group_id=1, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "No+contacts+selected" in result.headers["location"]

    @patch("internal.routes.contact_groups.mailler_client")
    async def test_whitespace_only_ids(self, mock_mc):
        form = MagicMock()
        form.get = MagicMock(return_value="  ,  ,  ")

        req = _make_request()
        req.form = AsyncMock(return_value=form)
        user = _make_user()

        result = await contact_group_add_contacts(req, group_id=1, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "No+contacts+selected" in result.headers["location"]

    @patch("internal.routes.contact_groups.mailler_client")
    async def test_result_none(self, mock_mc):
        """When mailler returns None, added should default to 0."""
        mock_mc.add_contacts_to_group = AsyncMock(return_value=None)

        form = MagicMock()
        form.get = MagicMock(
            side_effect=lambda key, default="": "id1" if key == "contact_ids" else default
        )

        req = _make_request()
        req.form = AsyncMock(return_value=form)
        user = _make_user()

        result = await contact_group_add_contacts(req, group_id=1, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "0+contact(s)+added" in result.headers["location"]

    async def test_auth_redirect(self):
        redirect = RedirectResponse(url="/login")
        req = _make_request()
        result = await contact_group_add_contacts(req, group_id=1, auth_result=redirect)
        assert result is redirect


@pytest.mark.asyncio
class TestContactGroupRemoveContacts:
    @patch("internal.routes.contact_groups.mailler_client")
    async def test_success(self, mock_mc):
        mock_mc.remove_contacts_from_group = AsyncMock(return_value={"removed": 2})

        form = MagicMock()
        form.get = MagicMock(
            side_effect=lambda key, default="": "id1,id2" if key == "contact_ids" else default
        )

        req = _make_request()
        req.form = AsyncMock(return_value=form)
        user = _make_user()

        result = await contact_group_remove_contacts(req, group_id=1, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "2+contact(s)+removed" in result.headers["location"]
        mock_mc.remove_contacts_from_group.assert_awaited_once_with(1, ["id1", "id2"])

    @patch("internal.routes.contact_groups.mailler_client")
    async def test_empty_ids(self, mock_mc):
        form = MagicMock()
        form.get = MagicMock(return_value="")

        req = _make_request()
        req.form = AsyncMock(return_value=form)
        user = _make_user()

        result = await contact_group_remove_contacts(req, group_id=1, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "No+contacts+selected" in result.headers["location"]

    @patch("internal.routes.contact_groups.mailler_client")
    async def test_whitespace_only_ids(self, mock_mc):
        form = MagicMock()
        form.get = MagicMock(return_value=" , , ")

        req = _make_request()
        req.form = AsyncMock(return_value=form)
        user = _make_user()

        result = await contact_group_remove_contacts(req, group_id=1, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "No+contacts+selected" in result.headers["location"]

    @patch("internal.routes.contact_groups.mailler_client")
    async def test_result_none(self, mock_mc):
        """When mailler returns None, removed should default to 0."""
        mock_mc.remove_contacts_from_group = AsyncMock(return_value=None)

        form = MagicMock()
        form.get = MagicMock(
            side_effect=lambda key, default="": "id1" if key == "contact_ids" else default
        )

        req = _make_request()
        req.form = AsyncMock(return_value=form)
        user = _make_user()

        result = await contact_group_remove_contacts(req, group_id=1, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "0+contact(s)+removed" in result.headers["location"]

    async def test_auth_redirect(self):
        redirect = RedirectResponse(url="/login")
        req = _make_request()
        result = await contact_group_remove_contacts(req, group_id=1, auth_result=redirect)
        assert result is redirect


@pytest.mark.asyncio
class TestContactGroupBulkDelete:
    @patch("internal.routes.contact_groups.mailler_client")
    async def test_success(self, mock_mc):
        mock_mc.delete_contact_group = AsyncMock(return_value=True)

        form = MagicMock()
        form.getlist = MagicMock(return_value=["1", "2", "3"])

        req = _make_request()
        req.form = AsyncMock(return_value=form)
        user = _make_user()

        result = await contact_group_bulk_delete(req, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "3+group(s)+deleted" in result.headers["location"]
        assert mock_mc.delete_contact_group.await_count == 3

    @patch("internal.routes.contact_groups.mailler_client")
    async def test_partial_delete(self, mock_mc):
        mock_mc.delete_contact_group = AsyncMock(side_effect=[True, False, True])

        form = MagicMock()
        form.getlist = MagicMock(return_value=["1", "2", "3"])

        req = _make_request()
        req.form = AsyncMock(return_value=form)
        user = _make_user()

        result = await contact_group_bulk_delete(req, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "2+group(s)+deleted" in result.headers["location"]

    @patch("internal.routes.contact_groups.mailler_client")
    async def test_empty_list(self, mock_mc):
        form = MagicMock()
        form.getlist = MagicMock(return_value=[])

        req = _make_request()
        req.form = AsyncMock(return_value=form)
        user = _make_user()

        result = await contact_group_bulk_delete(req, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "No+groups+selected" in result.headers["location"]

    @patch("internal.routes.contact_groups.mailler_client")
    async def test_invalid_ids(self, mock_mc):
        form = MagicMock()
        form.getlist = MagicMock(return_value=["1", "not_a_number"])

        req = _make_request()
        req.form = AsyncMock(return_value=form)
        user = _make_user()

        result = await contact_group_bulk_delete(req, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "Invalid+group+IDs" in result.headers["location"]

    async def test_auth_redirect(self):
        redirect = RedirectResponse(url="/login")
        req = _make_request()
        result = await contact_group_bulk_delete(req, auth_result=redirect)
        assert result is redirect


@pytest.mark.asyncio
class TestContactGroupDelete:
    @patch("internal.routes.contact_groups.mailler_client")
    async def test_success(self, mock_mc):
        mock_mc.get_contact_group = AsyncMock(return_value={"id": 1, "name": "g1"})
        mock_mc.delete_contact_group = AsyncMock(return_value=True)

        req = _make_request()
        user = _make_user()

        result = await contact_group_delete(req, group_id=1, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers["location"]

    @patch("internal.routes.contact_groups.mailler_client")
    async def test_group_not_found(self, mock_mc):
        mock_mc.get_contact_group = AsyncMock(return_value=None)

        req = _make_request()
        user = _make_user()

        result = await contact_group_delete(req, group_id=999, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "not+found" in result.headers["location"]

    @patch("internal.routes.contact_groups.mailler_client")
    async def test_delete_fails(self, mock_mc):
        mock_mc.get_contact_group = AsyncMock(return_value={"id": 1})
        mock_mc.delete_contact_group = AsyncMock(return_value=False)

        req = _make_request()
        user = _make_user()

        result = await contact_group_delete(req, group_id=1, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "Failed+to+delete" in result.headers["location"]

    async def test_auth_redirect(self):
        redirect = RedirectResponse(url="/login")
        req = _make_request()
        result = await contact_group_delete(req, group_id=1, auth_result=redirect)
        assert result is redirect
