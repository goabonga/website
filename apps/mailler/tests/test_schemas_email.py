# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the send / schedule request schemas."""

import pytest
from mailler.schemas.email import ScheduleEmailRequest, SendEmailRequest, SendEmailResponse
from pydantic import ValidationError

BASE = {"to_email": "user@example.com"}


class TestContentOrTemplate:
    def test_content_request(self):
        request = SendEmailRequest(**BASE, subject="Hi", html_content="<p>Hi</p>")
        assert request.template_slug is None
        assert request.provider is None

    def test_template_request(self):
        request = SendEmailRequest(
            **BASE, template_slug="workspace_invitation", variables={"name": "Ann"}
        )
        assert request.template_slug == "workspace_invitation"
        assert request.variables == {"name": "Ann"}

    def test_template_request_without_variables(self):
        assert SendEmailRequest(**BASE, template_slug="welcome").variables is None

    def test_nothing_is_refused(self):
        with pytest.raises(ValidationError, match="subject and html_content are required"):
            SendEmailRequest(**BASE)

    def test_subject_without_html_is_refused(self):
        with pytest.raises(ValidationError, match="subject and html_content are required"):
            SendEmailRequest(**BASE, subject="Hi")

    @pytest.mark.parametrize(
        "extra",
        [{"subject": "Hi"}, {"html_content": "<p>x</p>"}, {"text_content": "x"}],
    )
    def test_template_and_content_are_exclusive(self, extra):
        with pytest.raises(ValidationError, match="cannot be combined"):
            SendEmailRequest(**BASE, template_slug="welcome", **extra)

    def test_variables_need_a_template(self):
        with pytest.raises(ValidationError, match="variables can only be used"):
            SendEmailRequest(**BASE, subject="Hi", html_content="<p>x</p>", variables={"a": 1})

    def test_empty_slug_is_refused(self):
        with pytest.raises(ValidationError):
            SendEmailRequest(**BASE, template_slug="")

    def test_scheduled_requests_follow_the_same_rules(self):
        scheduled = ScheduleEmailRequest(
            **BASE, template_slug="welcome", scheduled_at="2030-01-01T10:00:00Z"
        )
        assert scheduled.template_slug == "welcome"
        with pytest.raises(ValidationError):
            ScheduleEmailRequest(**BASE, scheduled_at="2030-01-01T10:00:00Z")


class TestResponse:
    def test_missing_variables_default_to_empty(self):
        response = SendEmailResponse(id="1", status="queued", message="ok")
        assert response.missing_variables == []
