# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for internal.routes.email_templates module."""

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import JSONResponse, RedirectResponse
from internal.auth.models import User
from internal.routes.email_templates import (
    DEFAULT_MJML,
    TEMPLATE_STATUSES,
    email_template_bulk_delete,
    email_template_compile,
    email_template_create,
    email_template_delete,
    email_template_detail,
    email_template_duplicate,
    email_template_edit,
    email_template_new,
    email_template_preview,
    email_template_update,
    email_templates_list,
    generate_slug,
    parse_datetime_fields,
    parse_templates_list,
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
    req.form = AsyncMock(return_value=MagicMock())
    req.json = AsyncMock(return_value={})
    return req


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------


class TestParseDatetimeFields:
    """Tests for parse_datetime_fields helper."""

    def test_parses_iso_string(self):
        item = {"created_at": "2024-01-15T10:30:00Z"}
        result = parse_datetime_fields(item, ["created_at"])
        assert isinstance(result["created_at"], datetime)

    def test_parses_iso_string_with_offset(self):
        item = {"created_at": "2024-01-15T10:30:00+00:00"}
        result = parse_datetime_fields(item, ["created_at"])
        assert isinstance(result["created_at"], datetime)

    def test_skips_missing_field(self):
        item = {"name": "test"}
        result = parse_datetime_fields(item, ["created_at"])
        assert "created_at" not in result

    def test_skips_none_value(self):
        item = {"created_at": None}
        result = parse_datetime_fields(item, ["created_at"])
        assert result["created_at"] is None

    def test_skips_non_string_value(self):
        dt = datetime(2024, 1, 15, tzinfo=UTC)
        item = {"created_at": dt}
        result = parse_datetime_fields(item, ["created_at"])
        assert result["created_at"] is dt

    def test_suppresses_invalid_format(self):
        item = {"created_at": "not-a-date"}
        result = parse_datetime_fields(item, ["created_at"])
        assert result["created_at"] == "not-a-date"

    def test_multiple_fields(self):
        item = {
            "created_at": "2024-01-15T10:30:00Z",
            "updated_at": "2024-02-20T12:00:00Z",
        }
        result = parse_datetime_fields(item, ["created_at", "updated_at"])
        assert isinstance(result["created_at"], datetime)
        assert isinstance(result["updated_at"], datetime)

    def test_empty_string_value(self):
        item = {"created_at": ""}
        result = parse_datetime_fields(item, ["created_at"])
        assert result["created_at"] == ""


class TestParseTemplatesList:
    """Tests for parse_templates_list helper."""

    def test_parses_list_of_templates(self):
        items = [
            {"created_at": "2024-01-15T10:00:00Z", "name": "T1"},
            {"created_at": "2024-02-20T12:00:00Z", "name": "T2"},
        ]
        result = parse_templates_list(items)
        assert len(result) == 2
        assert isinstance(result[0]["created_at"], datetime)
        assert isinstance(result[1]["created_at"], datetime)

    def test_empty_list(self):
        assert parse_templates_list([]) == []

    def test_both_datetime_fields(self):
        item = {
            "created_at": "2024-01-15T10:00:00Z",
            "updated_at": "2024-01-15T11:00:00Z",
        }
        result = parse_templates_list([item])
        assert isinstance(result[0]["created_at"], datetime)
        assert isinstance(result[0]["updated_at"], datetime)


class TestGenerateSlug:
    """Tests for generate_slug helper."""

    def test_basic_slug(self):
        assert generate_slug("Hello World") == "hello-world"

    def test_strips_whitespace(self):
        assert generate_slug("  Hello World  ") == "hello-world"

    def test_removes_special_characters(self):
        assert generate_slug("Hello, World!") == "hello-world"

    def test_collapses_hyphens_and_spaces(self):
        assert generate_slug("Hello   --  World") == "hello-world"

    def test_truncates_to_100_chars(self):
        long_name = "a" * 200
        assert len(generate_slug(long_name)) == 100

    def test_empty_string(self):
        assert generate_slug("") == ""

    def test_preserves_underscores(self):
        assert generate_slug("hello_world") == "hello_world"

    def test_unicode_removal(self):
        result = generate_slug("caf@#$%")
        assert result == "caf"


class TestModuleLevelConstants:
    """Tests for module-level constants."""

    def test_template_statuses(self):
        assert TEMPLATE_STATUSES == ["draft", "active", "archived"]

    def test_default_mjml_contains_mjml_tags(self):
        assert "<mjml>" in DEFAULT_MJML
        assert "</mjml>" in DEFAULT_MJML
        assert "%subject%" in DEFAULT_MJML
        assert "%first_name%" in DEFAULT_MJML


# ---------------------------------------------------------------------------
# Route handler tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEmailTemplatesList:
    """Tests for email_templates_list handler."""

    @patch("internal.routes.email_templates.templates")
    @patch("internal.routes.email_templates.mailler_client")
    async def test_success(self, mock_mc, mock_tpl):
        user = _make_user()
        req = _make_request(query_params={"success": "ok", "error": None})
        mock_mc.get_templates = AsyncMock(
            return_value={
                "items": [{"created_at": "2024-01-15T10:00:00Z", "name": "T1"}],
                "total": 1,
                "pages": 1,
            }
        )
        mock_tpl.TemplateResponse.return_value = "rendered"

        result = await email_templates_list(
            request=req,
            page=1,
            search=None,
            status=None,
            auth_result=user,
        )

        assert result == "rendered"
        mock_mc.get_templates.assert_awaited_once_with(
            page=1,
            page_size=20,
            status=None,
            search=None,
        )
        ctx = mock_tpl.TemplateResponse.call_args.kwargs["context"]
        assert ctx["total"] == 1
        assert len(ctx["templates"]) == 1
        assert ctx["statuses"] == TEMPLATE_STATUSES

    @patch("internal.routes.email_templates.templates")
    @patch("internal.routes.email_templates.mailler_client")
    async def test_with_valid_status_filter(self, mock_mc, mock_tpl):
        user = _make_user()
        req = _make_request(query_params={})
        mock_mc.get_templates = AsyncMock(return_value={"items": [], "total": 0, "pages": 1})
        mock_tpl.TemplateResponse.return_value = "rendered"

        await email_templates_list(
            request=req,
            page=1,
            search=None,
            status="active",
            auth_result=user,
        )

        mock_mc.get_templates.assert_awaited_once_with(
            page=1,
            page_size=20,
            status="active",
            search=None,
        )

    @patch("internal.routes.email_templates.templates")
    @patch("internal.routes.email_templates.mailler_client")
    async def test_with_invalid_status_filter(self, mock_mc, mock_tpl):
        """Invalid status should be passed as None."""
        user = _make_user()
        req = _make_request(query_params={})
        mock_mc.get_templates = AsyncMock(return_value={"items": [], "total": 0, "pages": 1})
        mock_tpl.TemplateResponse.return_value = "rendered"

        await email_templates_list(
            request=req,
            page=1,
            search=None,
            status="invalid_status",
            auth_result=user,
        )

        mock_mc.get_templates.assert_awaited_once_with(
            page=1,
            page_size=20,
            status=None,
            search=None,
        )

    @patch("internal.routes.email_templates.templates")
    @patch("internal.routes.email_templates.mailler_client")
    async def test_with_search(self, mock_mc, mock_tpl):
        user = _make_user()
        req = _make_request(query_params={})
        mock_mc.get_templates = AsyncMock(return_value={"items": [], "total": 0, "pages": 1})
        mock_tpl.TemplateResponse.return_value = "rendered"

        await email_templates_list(
            request=req,
            page=2,
            search="welcome",
            status=None,
            auth_result=user,
        )

        mock_mc.get_templates.assert_awaited_once_with(
            page=2,
            page_size=20,
            status=None,
            search="welcome",
        )

    async def test_redirect_when_not_authenticated(self):
        redirect = RedirectResponse(url="/login", status_code=303)
        result = await email_templates_list(
            request=_make_request(),
            page=1,
            search=None,
            status=None,
            auth_result=redirect,
        )
        assert result is redirect


@pytest.mark.asyncio
class TestEmailTemplateNew:
    """Tests for email_template_new handler."""

    @patch("internal.routes.email_templates.templates")
    async def test_success(self, mock_tpl):
        user = _make_user()
        req = _make_request()
        mock_tpl.TemplateResponse.return_value = "rendered"

        result = await email_template_new(request=req, auth_result=user)

        assert result == "rendered"
        ctx = mock_tpl.TemplateResponse.call_args.kwargs["context"]
        assert ctx["template"] is None
        assert ctx["is_edit"] is False
        assert ctx["default_mjml"] == DEFAULT_MJML
        assert ctx["statuses"] == TEMPLATE_STATUSES

    async def test_redirect_when_not_authenticated(self):
        redirect = RedirectResponse(url="/login", status_code=303)
        result = await email_template_new(request=_make_request(), auth_result=redirect)
        assert result is redirect


@pytest.mark.asyncio
class TestEmailTemplateCreate:
    """Tests for email_template_create handler."""

    @patch("internal.routes.email_templates.mailler_client")
    async def test_success(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.create_template = AsyncMock(return_value={"id": 10, "slug": "my-template"})

        result = await email_template_create(
            request=req,
            name="  My Template  ",
            slug="  my-template  ",
            description="  A description  ",
            subject_template="  Hello {{name}}  ",
            mjml_source="  <mjml></mjml>  ",
            plain_text="  Hello  ",
            status="active",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "success" in result.headers["location"]
        call_data = mock_mc.create_template.call_args[0][0]
        assert call_data["name"] == "My Template"
        assert call_data["slug"] == "my-template"
        assert call_data["description"] == "A description"
        assert call_data["status"] == "active"

    @patch("internal.routes.email_templates.mailler_client")
    async def test_success_auto_generates_slug(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.create_template = AsyncMock(return_value={"id": 10})

        await email_template_create(
            request=req,
            name="My Template",
            slug="",
            description="",
            subject_template="Subject",
            mjml_source="<mjml></mjml>",
            plain_text="",
            status="draft",
            auth_result=user,
        )

        call_data = mock_mc.create_template.call_args[0][0]
        assert call_data["slug"] == "my-template"

    @patch("internal.routes.email_templates.mailler_client")
    async def test_empty_optional_fields(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.create_template = AsyncMock(return_value={"id": 10})

        await email_template_create(
            request=req,
            name="Template",
            slug="template",
            description="",
            subject_template="Subject",
            mjml_source="<mjml></mjml>",
            plain_text="",
            status="draft",
            auth_result=user,
        )

        call_data = mock_mc.create_template.call_args[0][0]
        assert call_data["description"] is None
        assert call_data["plain_text"] is None

    @patch("internal.routes.email_templates.mailler_client")
    async def test_invalid_status_defaults_to_draft(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.create_template = AsyncMock(return_value={"id": 10})

        await email_template_create(
            request=req,
            name="Template",
            slug="template",
            description="",
            subject_template="Subject",
            mjml_source="<mjml></mjml>",
            plain_text="",
            status="bogus_status",
            auth_result=user,
        )

        call_data = mock_mc.create_template.call_args[0][0]
        assert call_data["status"] == "draft"

    @patch("internal.routes.email_templates.mailler_client")
    async def test_create_fails(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.create_template = AsyncMock(return_value=None)

        result = await email_template_create(
            request=req,
            name="Template",
            slug="template",
            description="",
            subject_template="Subject",
            mjml_source="<mjml></mjml>",
            plain_text="",
            status="draft",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "error" in result.headers["location"]
        assert "Failed+to+create" in result.headers["location"]

    async def test_redirect_when_not_authenticated(self):
        redirect = RedirectResponse(url="/login", status_code=303)
        result = await email_template_create(
            request=_make_request(),
            name="T",
            slug="t",
            description="",
            subject_template="S",
            mjml_source="<mjml></mjml>",
            plain_text="",
            status="draft",
            auth_result=redirect,
        )
        assert result is redirect


@pytest.mark.asyncio
class TestEmailTemplateDetail:
    """Tests for email_template_detail handler."""

    @patch("internal.routes.email_templates.templates")
    @patch("internal.routes.email_templates.mailler_client")
    async def test_success(self, mock_mc, mock_tpl):
        user = _make_user()
        req = _make_request(query_params={"success": "ok", "error": None})
        mock_mc.get_template = AsyncMock(
            return_value={
                "id": 1,
                "name": "T1",
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T11:00:00Z",
            }
        )
        mock_tpl.TemplateResponse.return_value = "rendered"

        result = await email_template_detail(request=req, template_id=1, auth_result=user)

        assert result == "rendered"
        ctx = mock_tpl.TemplateResponse.call_args.kwargs["context"]
        assert ctx["template"]["id"] == 1
        assert isinstance(ctx["template"]["created_at"], datetime)

    @patch("internal.routes.email_templates.mailler_client")
    async def test_template_not_found(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_template = AsyncMock(return_value=None)

        result = await email_template_detail(request=req, template_id=999, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "not+found" in result.headers["location"]

    async def test_redirect_when_not_authenticated(self):
        redirect = RedirectResponse(url="/login", status_code=303)
        result = await email_template_detail(
            request=_make_request(),
            template_id=1,
            auth_result=redirect,
        )
        assert result is redirect


@pytest.mark.asyncio
class TestEmailTemplateEdit:
    """Tests for email_template_edit handler."""

    @patch("internal.routes.email_templates.templates")
    @patch("internal.routes.email_templates.mailler_client")
    async def test_success(self, mock_mc, mock_tpl):
        user = _make_user()
        req = _make_request()
        mock_mc.get_template = AsyncMock(
            return_value={
                "id": 1,
                "name": "T1",
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T11:00:00Z",
            }
        )
        mock_tpl.TemplateResponse.return_value = "rendered"

        result = await email_template_edit(request=req, template_id=1, auth_result=user)

        assert result == "rendered"
        ctx = mock_tpl.TemplateResponse.call_args.kwargs["context"]
        assert ctx["is_edit"] is True
        assert ctx["template"]["id"] == 1
        assert ctx["default_mjml"] == DEFAULT_MJML

    @patch("internal.routes.email_templates.mailler_client")
    async def test_template_not_found(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_template = AsyncMock(return_value=None)

        result = await email_template_edit(request=req, template_id=999, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "not+found" in result.headers["location"]

    async def test_redirect_when_not_authenticated(self):
        redirect = RedirectResponse(url="/login", status_code=303)
        result = await email_template_edit(
            request=_make_request(),
            template_id=1,
            auth_result=redirect,
        )
        assert result is redirect


@pytest.mark.asyncio
class TestEmailTemplateUpdate:
    """Tests for email_template_update handler."""

    @patch("internal.routes.email_templates.mailler_client")
    async def test_success(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.update_template = AsyncMock(return_value={"id": 1})

        result = await email_template_update(
            request=req,
            template_id=1,
            name="  Updated  ",
            description="  desc  ",
            subject_template="  Subject  ",
            mjml_source="  <mjml></mjml>  ",
            plain_text="  text  ",
            status="active",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers["location"]
        call_args = mock_mc.update_template.call_args
        assert call_args[0][0] == 1
        data = call_args[0][1]
        assert data["name"] == "Updated"
        assert data["description"] == "desc"
        assert data["status"] == "active"

    @patch("internal.routes.email_templates.mailler_client")
    async def test_empty_optional_fields(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.update_template = AsyncMock(return_value={"id": 1})

        await email_template_update(
            request=req,
            template_id=1,
            name="T",
            description="",
            subject_template="S",
            mjml_source="<mjml></mjml>",
            plain_text="",
            status="draft",
            auth_result=user,
        )

        data = mock_mc.update_template.call_args[0][1]
        assert data["description"] is None
        assert data["plain_text"] is None

    @patch("internal.routes.email_templates.mailler_client")
    async def test_invalid_status_defaults_to_draft(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.update_template = AsyncMock(return_value={"id": 1})

        await email_template_update(
            request=req,
            template_id=1,
            name="T",
            description="",
            subject_template="S",
            mjml_source="<mjml></mjml>",
            plain_text="",
            status="bogus",
            auth_result=user,
        )

        data = mock_mc.update_template.call_args[0][1]
        assert data["status"] == "draft"

    @patch("internal.routes.email_templates.mailler_client")
    async def test_update_fails(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.update_template = AsyncMock(return_value=None)

        result = await email_template_update(
            request=req,
            template_id=1,
            name="T",
            description="",
            subject_template="S",
            mjml_source="<mjml></mjml>",
            plain_text="",
            status="draft",
            auth_result=user,
        )

        assert isinstance(result, RedirectResponse)
        assert "Failed+to+update" in result.headers["location"]

    async def test_redirect_when_not_authenticated(self):
        redirect = RedirectResponse(url="/login", status_code=303)
        result = await email_template_update(
            request=_make_request(),
            template_id=1,
            name="T",
            description="",
            subject_template="S",
            mjml_source="<mjml></mjml>",
            plain_text="",
            status="draft",
            auth_result=redirect,
        )
        assert result is redirect


@pytest.mark.asyncio
class TestEmailTemplateCompile:
    """Tests for email_template_compile handler (AJAX endpoint)."""

    @patch("internal.routes.email_templates.mailler_client")
    async def test_success_without_sample_data(self, mock_mc):
        user = _make_user()
        req = _make_request()
        req.json = AsyncMock(
            return_value={
                "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>%name%</mj-text></mj-column></mj-section></mj-body></mjml>",
                "subject": "Hello %name%",
                "sample_data": {},
            }
        )
        mock_mc.compile_mjml = AsyncMock(
            return_value={
                "html": "<html>compiled</html>",
                "errors": [],
            }
        )

        result = await email_template_compile(request=req, auth_result=user)

        assert isinstance(result, JSONResponse)
        data = json.loads(result.body.decode())
        assert data["success"] is True
        assert data["html"] == "<html>compiled</html>"
        assert "name" in data["variables"]
        assert data["errors"] == []

    @patch("internal.routes.email_templates.mailler_client")
    async def test_success_with_sample_data(self, mock_mc):
        user = _make_user()
        req = _make_request()
        req.json = AsyncMock(
            return_value={
                "mjml_source": "<mjml><mj-body>{{greeting}}</mj-body></mjml>",
                "subject": "Hello {{name}}",
                "sample_data": {"greeting": "Hi there", "name": "John"},
            }
        )
        mock_mc.compile_mjml = AsyncMock(
            return_value={
                "html": "<html>{{greeting}}</html>",
                "errors": [],
            }
        )

        result = await email_template_compile(request=req, auth_result=user)

        data = json.loads(result.body.decode())
        assert data["success"] is True
        # Jinja2 should render sample data
        assert "Hi there" in data["html"]
        assert data["subject"] == "Hello John"

    @patch("internal.routes.email_templates.mailler_client")
    async def test_compile_errors(self, mock_mc):
        user = _make_user()
        req = _make_request()
        req.json = AsyncMock(
            return_value={
                "mjml_source": "<invalid>",
                "subject": "",
                "sample_data": {},
            }
        )
        mock_mc.compile_mjml = AsyncMock(
            return_value={
                "html": "",
                "errors": ["Invalid MJML"],
            }
        )

        result = await email_template_compile(request=req, auth_result=user)

        data = json.loads(result.body.decode())
        assert data["success"] is False
        assert data["errors"] == ["Invalid MJML"]

    @patch("internal.routes.email_templates.mailler_client")
    async def test_no_mjml_source(self, mock_mc):
        user = _make_user()
        req = _make_request()
        req.json = AsyncMock(return_value={"mjml_source": "", "subject": "", "sample_data": {}})

        result = await email_template_compile(request=req, auth_result=user)

        assert isinstance(result, JSONResponse)
        assert result.status_code == 400
        data = json.loads(result.body.decode())
        assert data["error"] == "No MJML source provided"

    @patch("internal.routes.email_templates.mailler_client")
    async def test_invalid_json(self, mock_mc):
        user = _make_user()
        req = _make_request()
        req.json = AsyncMock(side_effect=ValueError("Invalid JSON"))

        result = await email_template_compile(request=req, auth_result=user)

        assert isinstance(result, JSONResponse)
        assert result.status_code == 400
        data = json.loads(result.body.decode())
        assert data["error"] == "Invalid JSON"

    async def test_returns_401_when_not_authenticated(self):
        redirect = RedirectResponse(url="/login", status_code=303)
        result = await email_template_compile(request=_make_request(), auth_result=redirect)

        assert isinstance(result, JSONResponse)
        assert result.status_code == 401
        data = json.loads(result.body.decode())
        assert data["error"] == "Unauthorized"

    @patch("internal.routes.email_templates.mailler_client")
    async def test_variable_extraction_both_formats(self, mock_mc):
        """Test that both %var% and {{var}} formats are extracted."""
        user = _make_user()
        req = _make_request()
        req.json = AsyncMock(
            return_value={
                "mjml_source": "<mjml>%first_name% {{last_name}}</mjml>",
                "subject": "%email%",
                "sample_data": {},
            }
        )
        mock_mc.compile_mjml = AsyncMock(return_value={"html": "<html></html>", "errors": []})

        result = await email_template_compile(request=req, auth_result=user)

        data = json.loads(result.body.decode())
        variables = data["variables"]
        assert "first_name" in variables
        assert "last_name" in variables
        assert "email" in variables

    @patch("internal.routes.email_templates.mailler_client")
    async def test_sample_data_jinja2_render_error(self, mock_mc):
        """If Jinja2 rendering fails, html and subject remain unchanged."""
        user = _make_user()
        req = _make_request()
        req.json = AsyncMock(
            return_value={
                "mjml_source": "<mjml>{{ invalid | bad_filter }}</mjml>",
                "subject": "{{ invalid | bad_filter }}",
                "sample_data": {"key": "value"},
            }
        )
        mock_mc.compile_mjml = AsyncMock(
            return_value={
                "html": "<html>{{ invalid | bad_filter }}</html>",
                "errors": [],
            }
        )

        result = await email_template_compile(request=req, auth_result=user)

        data = json.loads(result.body.decode())
        assert data["success"] is True
        # The original html should remain since jinja2 error is suppressed
        assert "invalid" in data["html"]


@pytest.mark.asyncio
class TestEmailTemplatePreview:
    """Tests for email_template_preview handler (AJAX endpoint)."""

    @patch("internal.routes.email_templates.mailler_client")
    async def test_success(self, mock_mc):
        user = _make_user()
        req = _make_request()
        req.json = AsyncMock(return_value={"sample_data": {"first_name": "Alice"}})
        mock_mc.render_template = AsyncMock(
            return_value={
                "html": "<html>Hello Alice</html>",
                "subject": "Welcome Alice",
                "plain_text": "Hello Alice",
            }
        )

        result = await email_template_preview(request=req, template_id=1, auth_result=user)

        assert isinstance(result, JSONResponse)
        data = json.loads(result.body.decode())
        assert data["success"] is True
        assert data["html"] == "<html>Hello Alice</html>"
        assert data["subject"] == "Welcome Alice"
        assert data["plain_text"] == "Hello Alice"

        # Verify merged data includes defaults
        call_data = mock_mc.render_template.call_args[0][1]
        assert call_data["first_name"] == "Alice"  # Overrides default
        assert call_data["last_name"] == "Doe"  # Default

    @patch("internal.routes.email_templates.mailler_client")
    async def test_success_with_default_data(self, mock_mc):
        user = _make_user()
        req = _make_request()
        req.json = AsyncMock(return_value={"sample_data": {}})
        mock_mc.render_template = AsyncMock(
            return_value={
                "html": "<html>Hello</html>",
                "subject": "Subject",
                "plain_text": None,
            }
        )

        result = await email_template_preview(request=req, template_id=1, auth_result=user)

        data = json.loads(result.body.decode())
        assert data["success"] is True
        # Default sample data should be passed
        call_data = mock_mc.render_template.call_args[0][1]
        assert call_data["first_name"] == "John"
        assert call_data["last_name"] == "Doe"
        assert call_data["email"] == "john.doe@example.com"
        assert call_data["subject"] == "Sample Subject"

    @patch("internal.routes.email_templates.mailler_client")
    async def test_template_not_found(self, mock_mc):
        user = _make_user()
        req = _make_request()
        req.json = AsyncMock(return_value={"sample_data": {}})
        mock_mc.render_template = AsyncMock(return_value=None)

        result = await email_template_preview(request=req, template_id=999, auth_result=user)

        assert isinstance(result, JSONResponse)
        assert result.status_code == 404
        data = json.loads(result.body.decode())
        assert data["error"] == "Template not found"

    @patch("internal.routes.email_templates.mailler_client")
    async def test_invalid_json_uses_empty_sample_data(self, mock_mc):
        """If request.json() fails, sample_data defaults to empty dict."""
        user = _make_user()
        req = _make_request()
        req.json = AsyncMock(side_effect=ValueError("Bad JSON"))
        mock_mc.render_template = AsyncMock(
            return_value={
                "html": "<html></html>",
                "subject": "Subject",
            }
        )

        result = await email_template_preview(request=req, template_id=1, auth_result=user)

        data = json.loads(result.body.decode())
        assert data["success"] is True
        # Default data should still be passed
        call_data = mock_mc.render_template.call_args[0][1]
        assert call_data["first_name"] == "John"

    async def test_returns_401_when_not_authenticated(self):
        redirect = RedirectResponse(url="/login", status_code=303)
        result = await email_template_preview(
            request=_make_request(),
            template_id=1,
            auth_result=redirect,
        )

        assert isinstance(result, JSONResponse)
        assert result.status_code == 401
        data = json.loads(result.body.decode())
        assert data["error"] == "Unauthorized"


@pytest.mark.asyncio
class TestEmailTemplateDuplicate:
    """Tests for email_template_duplicate handler."""

    @patch("internal.routes.email_templates.mailler_client")
    async def test_success(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_template = AsyncMock(
            return_value={
                "id": 1,
                "slug": "welcome",
                "name": "Welcome",
                "description": "A welcome email",
                "subject_template": "Hello",
                "mjml_source": "<mjml></mjml>",
                "plain_text": "Hello text",
            }
        )
        mock_mc.create_template = AsyncMock(return_value={"id": 2})

        result = await email_template_duplicate(request=req, template_id=1, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "2/edit" in result.headers["location"]
        assert "duplicated" in result.headers["location"]

        call_data = mock_mc.create_template.call_args[0][0]
        assert call_data["slug"] == "welcome-copy"
        assert call_data["name"] == "Welcome (Copy)"
        assert call_data["status"] == "draft"
        assert call_data["description"] == "A welcome email"

    @patch("internal.routes.email_templates.mailler_client")
    async def test_original_not_found(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_template = AsyncMock(return_value=None)

        result = await email_template_duplicate(request=req, template_id=999, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "not+found" in result.headers["location"]

    @patch("internal.routes.email_templates.mailler_client")
    async def test_create_copy_fails(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.get_template = AsyncMock(
            return_value={
                "id": 1,
                "slug": "tpl",
                "name": "Template",
                "description": None,
                "subject_template": "S",
                "mjml_source": "<mjml></mjml>",
                "plain_text": None,
            }
        )
        mock_mc.create_template = AsyncMock(return_value=None)

        result = await email_template_duplicate(request=req, template_id=1, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "Failed+to+duplicate" in result.headers["location"]

    @patch("internal.routes.email_templates.mailler_client")
    async def test_missing_slug_uses_default(self, mock_mc):
        """When original template has no slug, fallback to 'template' prefix."""
        user = _make_user()
        req = _make_request()
        mock_mc.get_template = AsyncMock(
            return_value={
                "id": 1,
                "name": "Template",
                "description": None,
                "subject_template": "S",
                "mjml_source": "<mjml></mjml>",
                "plain_text": None,
            }
        )
        mock_mc.create_template = AsyncMock(return_value={"id": 2})

        await email_template_duplicate(request=req, template_id=1, auth_result=user)

        call_data = mock_mc.create_template.call_args[0][0]
        assert call_data["slug"] == "template-copy"

    async def test_redirect_when_not_authenticated(self):
        redirect = RedirectResponse(url="/login", status_code=303)
        result = await email_template_duplicate(
            request=_make_request(),
            template_id=1,
            auth_result=redirect,
        )
        assert result is redirect


@pytest.mark.asyncio
class TestEmailTemplateBulkDelete:
    """Tests for email_template_bulk_delete handler."""

    @patch("internal.routes.email_templates.mailler_client")
    async def test_success(self, mock_mc):
        user = _make_user()
        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["1", "2", "3"]
        req.form = AsyncMock(return_value=form_mock)
        mock_mc.delete_template = AsyncMock(return_value=True)

        result = await email_template_bulk_delete(request=req, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "3+template(s)+deleted" in result.headers["location"]

    @patch("internal.routes.email_templates.mailler_client")
    async def test_no_template_ids(self, mock_mc):
        user = _make_user()
        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = []
        req.form = AsyncMock(return_value=form_mock)

        result = await email_template_bulk_delete(request=req, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "No+templates+selected" in result.headers["location"]

    @patch("internal.routes.email_templates.mailler_client")
    async def test_invalid_template_ids(self, mock_mc):
        user = _make_user()
        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["abc"]
        req.form = AsyncMock(return_value=form_mock)

        result = await email_template_bulk_delete(request=req, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "Invalid+template+IDs" in result.headers["location"]

    @patch("internal.routes.email_templates.mailler_client")
    async def test_empty_string_ids(self, mock_mc):
        """Empty strings after filtering result in no valid templates."""
        user = _make_user()
        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["", ""]
        req.form = AsyncMock(return_value=form_mock)

        result = await email_template_bulk_delete(request=req, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "No+valid+templates+selected" in result.headers["location"]

    @patch("internal.routes.email_templates.mailler_client")
    async def test_some_deletes_fail(self, mock_mc):
        user = _make_user()
        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["1", "2"]
        req.form = AsyncMock(return_value=form_mock)
        mock_mc.delete_template = AsyncMock(side_effect=[True, False])

        result = await email_template_bulk_delete(request=req, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "1+template(s)+deleted" in result.headers["location"]

    async def test_redirect_when_not_authenticated(self):
        redirect = RedirectResponse(url="/login", status_code=303)
        result = await email_template_bulk_delete(request=_make_request(), auth_result=redirect)
        assert result is redirect


@pytest.mark.asyncio
class TestEmailTemplateDelete:
    """Tests for email_template_delete handler."""

    @patch("internal.routes.email_templates.mailler_client")
    async def test_success(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.delete_template = AsyncMock(return_value=True)

        result = await email_template_delete(request=req, template_id=1, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "deleted+successfully" in result.headers["location"].lower()

    @patch("internal.routes.email_templates.mailler_client")
    async def test_delete_fails(self, mock_mc):
        user = _make_user()
        req = _make_request()
        mock_mc.delete_template = AsyncMock(return_value=False)

        result = await email_template_delete(request=req, template_id=1, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "Failed+to+delete" in result.headers["location"]

    async def test_redirect_when_not_authenticated(self):
        redirect = RedirectResponse(url="/login", status_code=303)
        result = await email_template_delete(
            request=_make_request(),
            template_id=1,
            auth_result=redirect,
        )
        assert result is redirect
