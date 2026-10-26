# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for template CRUD routes."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient
from mailler.routes.templates import extract_variables
from sqlalchemy.exc import IntegrityError


def _make_db_list_response(items=None, total=0):
    count_result = MagicMock()
    count_result.scalar.return_value = total
    list_result = MagicMock()
    list_result.scalars.return_value.all.return_value = items or []
    return [count_result, list_result]


def _make_template_mock(**overrides):
    now = datetime.now(UTC)
    t = MagicMock()
    t.id = overrides.get("id", 1)
    t.client_id = overrides.get("client_id", "test-client-id")
    t.slug = overrides.get("slug", "test")
    t.name = overrides.get("name", "Test")
    t.description = overrides.get("description")
    t.subject_template = overrides.get("subject_template", "Hello {{name}}")
    t.mjml_source = overrides.get("mjml_source", "<mjml><mj-body></mj-body></mjml>")
    t.html_compiled = overrides.get("html_compiled", "<p>Hello {{name}}</p>")
    t.plain_text = overrides.get("plain_text")
    t.status = overrides.get("status", "draft")
    t.variables = overrides.get("variables", ["name"])
    t.metadata_ = overrides.get("metadata_", {})
    t.created_at = overrides.get("created_at", now)
    t.updated_at = overrides.get("updated_at", now)
    return t


# --------------------------------------------------------------------------
# extract_variables
# --------------------------------------------------------------------------


class TestExtractVariables:
    def test_duplicate_variables_deduplicated(self):
        """Cover branch 55->54: when a variable appears multiple times, it is deduplicated."""
        result = extract_variables(
            "Hello {{ name }}, welcome {{ name }}!",
            "Hi {{ name }}",
        )
        assert result == ["name"]

    def test_multiple_unique_variables(self):
        """Variables are returned in order of first appearance without duplicates."""
        result = extract_variables(
            "{{ greeting }} {{ name }}, your code is {{ code }}",
            "{{ greeting }} {{ name }}",
        )
        assert result == ["greeting", "name", "code"]

    def test_no_variables(self):
        """No variables found returns empty list."""
        result = extract_variables("<p>No vars</p>", "Static subject")
        assert result == []


# --------------------------------------------------------------------------
# GET /templates
# --------------------------------------------------------------------------


class TestListTemplates:
    async def test_list_empty(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response(items=[], total=0))
        response = await auth_client.get("/api/v1/templates")
        assert response.status_code == 200
        assert response.json()["items"] == []

    async def test_list_with_items(self, auth_client: AsyncClient, mock_db_session):
        template = _make_template_mock()
        mock_db_session.execute = AsyncMock(
            side_effect=_make_db_list_response(items=[template], total=1)
        )
        response = await auth_client.get("/api/v1/templates")
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

    async def test_list_with_status_filter(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response(items=[], total=0))
        response = await auth_client.get("/api/v1/templates?status=active")
        assert response.status_code == 200

    async def test_list_with_search(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response(items=[], total=0))
        response = await auth_client.get("/api/v1/templates?search=test")
        assert response.status_code == 200

    async def test_list_with_status_and_search(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response(items=[], total=0))
        response = await auth_client.get("/api/v1/templates?status=draft&search=test")
        assert response.status_code == 200


# --------------------------------------------------------------------------
# POST /templates
# --------------------------------------------------------------------------


class TestCreateTemplate:
    @patch("mailler.routes.templates.compile_mjml")
    async def test_create_success(self, mock_compile, admin_client: AsyncClient, mock_db_session):
        mock_compile.return_value = {"html": "<p>compiled</p>", "errors": None}

        async def _refresh_with_int_id(obj, *args, **kwargs):
            now = datetime.now(UTC)
            if getattr(obj, "id", None) is None:
                obj.id = 1
            if getattr(obj, "created_at", None) is None:
                obj.created_at = now
            if getattr(obj, "updated_at", None) is None:
                obj.updated_at = now

        mock_db_session.refresh = AsyncMock(side_effect=_refresh_with_int_id)

        response = await admin_client.post(
            "/api/v1/templates",
            json={
                "slug": "welcome",
                "name": "Welcome",
                "subject_template": "Hello {{name}}",
                "mjml_source": "<mjml><mj-body></mj-body></mjml>",
            },
        )
        assert response.status_code == 201
        assert response.json()["slug"] == "welcome"

    @patch("mailler.routes.templates.compile_mjml")
    async def test_create_compilation_error(
        self, mock_compile, admin_client: AsyncClient, mock_db_session
    ):
        mock_compile.return_value = {"html": "", "errors": ["Invalid MJML"]}
        response = await admin_client.post(
            "/api/v1/templates",
            json={
                "slug": "bad",
                "name": "Bad",
                "subject_template": "S",
                "mjml_source": "<bad>",
            },
        )
        assert response.status_code == 400

    @patch("mailler.routes.templates.compile_mjml")
    async def test_create_duplicate_slug(
        self, mock_compile, admin_client: AsyncClient, mock_db_session
    ):
        mock_compile.return_value = {"html": "<p>ok</p>", "errors": None}
        mock_db_session.commit = AsyncMock(side_effect=IntegrityError("", {}, Exception()))
        response = await admin_client.post(
            "/api/v1/templates",
            json={
                "slug": "dup",
                "name": "Dup",
                "subject_template": "S",
                "mjml_source": "<mjml></mjml>",
            },
        )
        assert response.status_code == 409

    @patch("mailler.routes.templates.compile_mjml")
    async def test_create_with_explicit_variables(
        self, mock_compile, admin_client: AsyncClient, mock_db_session
    ):
        mock_compile.return_value = {"html": "<p>ok</p>", "errors": None}

        async def _refresh(obj, *args, **kwargs):
            if getattr(obj, "id", None) is None:
                obj.id = 1
            if getattr(obj, "created_at", None) is None:
                obj.created_at = datetime.now(UTC)
            if getattr(obj, "updated_at", None) is None:
                obj.updated_at = datetime.now(UTC)

        mock_db_session.refresh = AsyncMock(side_effect=_refresh)
        response = await admin_client.post(
            "/api/v1/templates",
            json={
                "slug": "vars",
                "name": "V",
                "subject_template": "S",
                "mjml_source": "<mjml></mjml>",
                "variables": ["x", "y"],
            },
        )
        assert response.status_code == 201


# --------------------------------------------------------------------------
# GET /templates/{id}
# --------------------------------------------------------------------------


class TestGetTemplate:
    async def test_get_found(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=_make_template_mock())
        response = await auth_client.get("/api/v1/templates/1")
        assert response.status_code == 200

    async def test_get_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=None)
        response = await auth_client.get("/api/v1/templates/999")
        assert response.status_code == 404


# --------------------------------------------------------------------------
# GET /templates/by-slug/{slug}
# --------------------------------------------------------------------------


class TestGetTemplateBySlug:
    async def test_found(self, auth_client: AsyncClient, mock_db_session):
        template = _make_template_mock(slug="welcome")
        result = MagicMock()
        result.scalar_one_or_none.return_value = template
        mock_db_session.execute = AsyncMock(return_value=result)
        response = await auth_client.get("/api/v1/templates/by-slug/welcome")
        assert response.status_code == 200
        assert response.json()["slug"] == "welcome"

    async def test_not_found(self, auth_client: AsyncClient, mock_db_session):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=result)
        response = await auth_client.get("/api/v1/templates/by-slug/nope")
        assert response.status_code == 404


# --------------------------------------------------------------------------
# PUT /templates/{id}
# --------------------------------------------------------------------------


class TestUpdateTemplate:
    async def test_update_success(self, admin_client: AsyncClient, mock_db_session):
        template = _make_template_mock()
        mock_db_session.get = AsyncMock(return_value=template)
        response = await admin_client.put(
            "/api/v1/templates/1",
            json={
                "name": "Updated",
                "description": "D",
                "subject_template": "New S",
                "plain_text": "Plain",
                "metadata": {"k": "v"},
                "status": "active",
            },
        )
        assert response.status_code == 200

    async def test_update_not_found(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=None)
        response = await admin_client.put("/api/v1/templates/999", json={"name": "X"})
        assert response.status_code == 404

    @patch("mailler.routes.templates.compile_mjml")
    async def test_update_recompile_mjml(
        self, mock_compile, admin_client: AsyncClient, mock_db_session
    ):
        mock_compile.return_value = {"html": "<p>new</p>", "errors": None}
        template = _make_template_mock()
        mock_db_session.get = AsyncMock(return_value=template)
        response = await admin_client.put(
            "/api/v1/templates/1",
            json={"mjml_source": "<mjml><mj-body></mj-body></mjml>"},
        )
        assert response.status_code == 200

    @patch("mailler.routes.templates.compile_mjml")
    async def test_update_mjml_compile_error(
        self, mock_compile, admin_client: AsyncClient, mock_db_session
    ):
        mock_compile.return_value = {"html": "", "errors": ["bad"]}
        template = _make_template_mock()
        mock_db_session.get = AsyncMock(return_value=template)
        response = await admin_client.put(
            "/api/v1/templates/1",
            json={"mjml_source": "<bad>"},
        )
        assert response.status_code == 400

    async def test_update_explicit_variables(self, admin_client: AsyncClient, mock_db_session):
        template = _make_template_mock()
        mock_db_session.get = AsyncMock(return_value=template)
        response = await admin_client.put(
            "/api/v1/templates/1",
            json={"variables": ["a", "b"]},
        )
        assert response.status_code == 200

    async def test_update_name_only_skips_variable_extraction(
        self, admin_client: AsyncClient, mock_db_session
    ):
        """Cover branch 355->361: update without mjml_source, subject_template, or variables.

        When none of these are provided, the variable re-extraction elif is skipped.
        """
        template = _make_template_mock()
        mock_db_session.get = AsyncMock(return_value=template)
        response = await admin_client.put(
            "/api/v1/templates/1",
            json={"name": "Renamed Template"},
        )
        assert response.status_code == 200


# --------------------------------------------------------------------------
# DELETE /templates/{id}
# --------------------------------------------------------------------------


class TestDeleteTemplate:
    async def test_delete_success(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=_make_template_mock())
        response = await admin_client.delete("/api/v1/templates/1")
        assert response.status_code == 204

    async def test_delete_not_found(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=None)
        response = await admin_client.delete("/api/v1/templates/999")
        assert response.status_code == 404


# --------------------------------------------------------------------------
# POST /templates/compile
# --------------------------------------------------------------------------


class TestCompileMjml:
    @patch("mailler.routes.templates.compile_mjml")
    async def test_compile_success(self, mock_compile, auth_client: AsyncClient):
        mock_compile.return_value = {"html": "<p>ok</p>", "errors": None}
        response = await auth_client.post(
            "/api/v1/templates/compile",
            json={"mjml_source": "<mjml></mjml>"},
        )
        assert response.status_code == 200
        assert response.json()["html"] == "<p>ok</p>"


# --------------------------------------------------------------------------
# POST /templates/{id}/render
# --------------------------------------------------------------------------


class TestRenderTemplate:
    async def test_render_success(self, auth_client: AsyncClient, mock_db_session):
        template = _make_template_mock(
            html_compiled="<p>Hello {{name}}</p>",
            subject_template="Hello {{name}}",
            plain_text="Hello {{name}}",
        )
        mock_db_session.get = AsyncMock(return_value=template)
        response = await auth_client.post(
            "/api/v1/templates/1/render",
            json={"variables": {"name": "World"}},
        )
        assert response.status_code == 200
        data = response.json()
        assert "World" in data["subject"]
        assert "World" in data["html"]
        assert "World" in data["plain_text"]

    async def test_render_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=None)
        response = await auth_client.post(
            "/api/v1/templates/999/render",
            json={"variables": {}},
        )
        assert response.status_code == 404

    async def test_render_not_compiled(self, auth_client: AsyncClient, mock_db_session):
        template = _make_template_mock(html_compiled=None)
        mock_db_session.get = AsyncMock(return_value=template)
        response = await auth_client.post(
            "/api/v1/templates/1/render",
            json={"variables": {}},
        )
        assert response.status_code == 400

    async def test_render_no_plain_text(self, auth_client: AsyncClient, mock_db_session):
        template = _make_template_mock(
            html_compiled="<p>Hi</p>",
            subject_template="S",
            plain_text=None,
        )
        mock_db_session.get = AsyncMock(return_value=template)
        response = await auth_client.post(
            "/api/v1/templates/1/render",
            json={"variables": {}},
        )
        assert response.status_code == 200
        assert response.json()["plain_text"] is None

    async def test_render_template_syntax_error(self, auth_client: AsyncClient, mock_db_session):
        template = _make_template_mock(
            html_compiled="<p>{% if %}</p>",
            subject_template="Valid Subject",
        )
        mock_db_session.get = AsyncMock(return_value=template)

        response = await auth_client.post("/api/v1/templates/1/render", json={"variables": {}})

        assert response.status_code == 400
        assert "syntax error" in response.json()["detail"].lower()

    async def test_render_undefined_variable_error(self, auth_client: AsyncClient, mock_db_session):
        template = _make_template_mock(
            html_compiled="<p>Hello {{ user.name }}</p>",
            subject_template="Hello",
        )
        mock_db_session.get = AsyncMock(return_value=template)

        response = await auth_client.post("/api/v1/templates/1/render", json={"variables": {}})

        assert response.status_code == 400
        assert "Missing variable" in response.json()["detail"]

    async def test_render_escapes_html_but_not_the_subject(
        self, auth_client: AsyncClient, mock_db_session
    ):
        template = _make_template_mock(
            html_compiled="<p>{{ name }}</p>",
            subject_template="Hello {{ name }}",
            plain_text="Hi %name%",
        )
        mock_db_session.get = AsyncMock(return_value=template)

        response = await auth_client.post(
            "/api/v1/templates/1/render", json={"variables": {"name": "<b>Tom & Jerry</b>"}}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["html"] == "<p>&lt;b&gt;Tom &amp; Jerry&lt;/b&gt;</p>"
        assert data["subject"] == "Hello <b>Tom & Jerry</b>"
        assert data["plain_text"] == "Hi <b>Tom & Jerry</b>"

    async def test_render_refuses_to_reach_python_internals(
        self, auth_client: AsyncClient, mock_db_session
    ):
        template = _make_template_mock(
            html_compiled="<p>{{ ''.__class__.__mro__ }}</p>",
            subject_template="Hello",
        )
        mock_db_session.get = AsyncMock(return_value=template)

        response = await auth_client.post("/api/v1/templates/1/render", json={"variables": {}})

        assert response.status_code == 400
        assert "not allowed" in response.json()["detail"]


# --------------------------------------------------------------------------
# Isolation between clients
# --------------------------------------------------------------------------

_BODY = {
    "slug": "welcome",
    "name": "Welcome",
    "subject_template": "Hello {{name}}",
    "mjml_source": "<mjml><mj-body></mj-body></mjml>",
}


def _params(mock_db_session, call=0):
    return mock_db_session.execute.await_args_list[call].args[0].compile().params


async def _refresh_template(obj, *args, **kwargs):
    now = datetime.now(UTC)
    obj.id = obj.id or 1
    obj.created_at = obj.created_at or now
    obj.updated_at = obj.updated_at or now


class TestTemplatesBelongToTheirClient:
    async def test_list_is_restricted_to_the_client(self, auth_client, mock_db_session):
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response())
        response = await auth_client.get("/api/v1/templates")
        assert response.status_code == 200
        assert _params(mock_db_session, 0)["client_id_1"] == "test-client-id"
        assert _params(mock_db_session, 1)["client_id_1"] == "test-client-id"

    async def test_list_of_another_client_is_forbidden(self, auth_client, mock_db_session):
        response = await auth_client.get("/api/v1/templates?client_id=other")
        assert response.status_code == 403

    async def test_admin_lists_every_client_or_one(self, admin_client, mock_db_session):
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response() * 2)
        await admin_client.get("/api/v1/templates")
        assert "client_id_1" not in _params(mock_db_session, 1)
        await admin_client.get("/api/v1/templates?client_id=other")
        assert _params(mock_db_session, 3)["client_id_1"] == "other"

    @patch("mailler.routes.templates.compile_mjml")
    async def test_created_template_is_owned_by_the_caller(
        self, mock_compile, writer_client, mock_db_session
    ):
        mock_compile.return_value = {"html": "<p>x</p>", "errors": None}
        mock_db_session.refresh = AsyncMock(side_effect=_refresh_template)
        response = await writer_client.post("/api/v1/templates", json=_BODY)
        assert response.status_code == 201
        assert mock_db_session.add.call_args[0][0].client_id == "test-client-id"
        assert response.json()["client_id"] == "test-client-id"

    @patch("mailler.routes.templates.compile_mjml")
    async def test_regular_caller_cannot_create_for_another_client(
        self, mock_compile, writer_client, mock_db_session
    ):
        response = await writer_client.post(
            "/api/v1/templates", json={**_BODY, "client_id": "other"}
        )
        assert response.status_code == 403
        mock_db_session.add.assert_not_called()

    @patch("mailler.routes.templates.compile_mjml")
    async def test_admin_can_create_for_another_client(
        self, mock_compile, admin_client, mock_db_session
    ):
        mock_compile.return_value = {"html": "<p>x</p>", "errors": None}
        mock_db_session.refresh = AsyncMock(side_effect=_refresh_template)
        response = await admin_client.post(
            "/api/v1/templates", json={**_BODY, "client_id": "other"}
        )
        assert response.status_code == 201
        assert mock_db_session.add.call_args[0][0].client_id == "other"

    async def test_get_of_another_client_is_not_found(self, auth_client, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=_make_template_mock(client_id="other"))
        assert (await auth_client.get("/api/v1/templates/1")).status_code == 404

    async def test_admin_reads_any_client(self, admin_client, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=_make_template_mock(client_id="other"))
        response = await admin_client.get("/api/v1/templates/1")
        assert response.status_code == 200
        assert response.json()["client_id"] == "other"

    async def test_by_slug_looks_inside_the_callers_client(self, auth_client, mock_db_session):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=result)
        await auth_client.get("/api/v1/templates/by-slug/welcome")
        assert _params(mock_db_session)["client_id_1"] == "test-client-id"
        assert _params(mock_db_session)["slug_1"] == "welcome"

    async def test_by_slug_of_another_client_is_forbidden(self, auth_client):
        response = await auth_client.get("/api/v1/templates/by-slug/welcome?client_id=other")
        assert response.status_code == 403

    async def test_admin_by_slug_names_the_client(self, admin_client, mock_db_session):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=result)
        await admin_client.get("/api/v1/templates/by-slug/welcome?client_id=other")
        assert _params(mock_db_session)["client_id_1"] == "other"

    async def test_delete_of_another_client_is_not_found(self, writer_client, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=_make_template_mock(client_id="other"))
        assert (await writer_client.delete("/api/v1/templates/1")).status_code == 404
        mock_db_session.delete.assert_not_called()

    async def test_update_of_another_client_is_not_found_for_a_writer(
        self, writer_client, mock_db_session
    ):
        foreign = _make_template_mock(client_id="other")
        mock_db_session.get = AsyncMock(return_value=foreign)
        response = await writer_client.put("/api/v1/templates/1", json={"name": "Hijacked"})
        assert response.status_code == 404
        assert foreign.name != "Hijacked"

    async def test_writer_updates_and_deletes_its_own_template(
        self, writer_client, mock_db_session
    ):
        own = _make_template_mock()
        mock_db_session.get = AsyncMock(return_value=own)
        assert (
            await writer_client.put("/api/v1/templates/1", json={"name": "Mine"})
        ).status_code == 200
        assert (await writer_client.delete("/api/v1/templates/1")).status_code == 204

    async def test_render_of_another_client_is_not_found(self, auth_client, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=_make_template_mock(client_id="other"))
        response = await auth_client.post("/api/v1/templates/1/render", json={"variables": {}})
        assert response.status_code == 404


class TestTemplateSlugs:
    @patch("mailler.routes.templates.compile_mjml")
    async def test_underscores_are_allowed(self, mock_compile, writer_client, mock_db_session):
        mock_compile.return_value = {"html": "<p>x</p>", "errors": None}
        mock_db_session.refresh = AsyncMock(side_effect=_refresh_template)
        response = await writer_client.post(
            "/api/v1/templates", json={**_BODY, "slug": "workspace_invitation"}
        )
        assert response.status_code == 201
        assert response.json()["slug"] == "workspace_invitation"

    async def test_malformed_slugs_are_refused(self, writer_client):
        for slug in ("_leading", "trailing_", "double__underscore", "mixed-_sep", "Upper", "a b"):
            response = await writer_client.post("/api/v1/templates", json={**_BODY, "slug": slug})
            assert response.status_code == 422, slug
