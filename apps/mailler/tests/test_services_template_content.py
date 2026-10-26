# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the content resolution of emails sent from a template."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from mailler.auth.dependencies import AuthContext
from mailler.auth.models import User
from mailler.schemas.email import SendEmailRequest
from mailler.services.template_content import resolve_content


def _auth(client_id="app-one", is_admin=False):
    return AuthContext(user=User(id=uuid4(), client_id=client_id, scopes=[]), is_admin=is_admin)


def _db(template):
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = template
    db.execute.return_value = result
    return db


def _template(**fields):
    template = MagicMock()
    template.slug = "welcome"
    template.status = "active"
    template.subject_template = "Hello {{ name }}"
    template.html_compiled = "<p>Hello {{ name }}</p>"
    template.plain_text = None
    template.variables = ["name"]
    for key, value in fields.items():
        setattr(template, key, value)
    return template


def _request(**fields):
    return SendEmailRequest(
        to_email="user@example.com", template_slug="welcome", variables={"name": "Ann"}, **fields
    )


class TestPlainContent:
    async def test_content_is_returned_as_given(self):
        db = _db(None)
        request = SendEmailRequest(
            to_email="user@example.com",
            subject="Hi",
            html_content="<p>Hi</p>",
            text_content="Hi",
            metadata={"a": 1},
        )
        content = await resolve_content(db, _auth(), request)
        assert (content.subject, content.html, content.text) == ("Hi", "<p>Hi</p>", "Hi")
        assert content.metadata == {"a": 1}
        assert content.missing_variables == []
        db.execute.assert_not_called()


class TestTemplateContent:
    async def test_template_is_rendered(self):
        content = await resolve_content(_db(_template()), _auth(), _request())
        assert content.subject == "Hello Ann"
        assert content.html == "<p>Hello Ann</p>"
        assert content.metadata == {"template_slug": "welcome"}
        assert content.missing_variables == []

    async def test_template_is_looked_up_in_the_client_of_the_caller(self):
        db = _db(_template())
        await resolve_content(db, _auth("app-two"), _request())
        params = db.execute.await_args.args[0].compile().params
        assert params["client_id_1"] == "app-two"
        assert params["slug_1"] == "welcome"

    async def test_plain_text_is_rendered_or_derived_from_the_html(self):
        content = await resolve_content(_db(_template(plain_text="Hi %name%")), _auth(), _request())
        assert content.text == "Hi Ann"
        content = await resolve_content(_db(_template()), _auth(), _request())
        assert content.text == "Hello Ann"

    async def test_values_are_escaped_in_the_html_only(self):
        request = SendEmailRequest(
            to_email="user@example.com", template_slug="welcome", variables={"name": "<b>&</b>"}
        )
        content = await resolve_content(_db(_template()), _auth(), request)
        assert content.html == "<p>Hello &lt;b&gt;&amp;&lt;/b&gt;</p>"
        assert content.subject == "Hello <b>&</b>"

    async def test_request_metadata_is_kept(self):
        request = _request(metadata={"workspace": 7})
        content = await resolve_content(_db(_template()), _auth(), request)
        assert content.metadata == {"workspace": 7, "template_slug": "welcome"}

    async def test_missing_variables_are_reported(self):
        template = _template(variables=["name", "link"])
        content = await resolve_content(_db(template), _auth(), _request())
        assert content.missing_variables == ["link"]

    async def test_unknown_template(self):
        with pytest.raises(HTTPException) as exc_info:
            await resolve_content(_db(None), _auth(), _request())
        assert exc_info.value.status_code == 404
        assert "'welcome' not found" in exc_info.value.detail

    @pytest.mark.parametrize("status", ["draft", "archived"])
    async def test_template_must_be_active(self, status):
        with pytest.raises(HTTPException) as exc_info:
            await resolve_content(_db(_template(status=status)), _auth(), _request())
        assert exc_info.value.status_code == 422
        assert "not active" in exc_info.value.detail

    async def test_template_must_be_compiled(self):
        with pytest.raises(HTTPException) as exc_info:
            await resolve_content(_db(_template(html_compiled=None)), _auth(), _request())
        assert exc_info.value.status_code == 422
        assert "not been compiled" in exc_info.value.detail

    async def test_rendering_errors(self):
        template = _template(html_compiled="<p>{{ user.name }}</p>")
        with pytest.raises(HTTPException) as exc_info:
            await resolve_content(_db(template), _auth(), _request())
        assert exc_info.value.status_code == 422
        assert "Missing variable" in exc_info.value.detail

    async def test_hostile_templates_do_not_run(self):
        template = _template(html_compiled="<p>{{ ''.__class__.__mro__ }}</p>")
        with pytest.raises(HTTPException) as exc_info:
            await resolve_content(_db(template), _auth(), _request())
        assert "not allowed" in exc_info.value.detail

    async def test_empty_subject(self):
        template = _template(subject_template="{{ missing }}")
        with pytest.raises(HTTPException) as exc_info:
            await resolve_content(_db(template), _auth(), _request())
        assert exc_info.value.status_code == 422
        assert "subject is empty" in exc_info.value.detail

    async def test_subject_too_long(self):
        template = _template(subject_template="x{{ name }}")
        request = SendEmailRequest(
            to_email="user@example.com", template_slug="welcome", variables={"name": "y" * 600}
        )
        with pytest.raises(HTTPException) as exc_info:
            await resolve_content(_db(template), _auth(), request)
        assert "longer than 500" in exc_info.value.detail

    async def test_caller_without_a_client_cannot_name_one(self):
        auth = AuthContext(user=User(id=uuid4(), scopes=[]), is_admin=True)
        with pytest.raises(HTTPException) as exc_info:
            await resolve_content(_db(_template()), auth, _request())
        assert exc_info.value.status_code == 403
