# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the sending scenarios."""

from unittest.mock import patch

from behave import given, then, when
from mailler.services.providers.base import EmailProvider, EmailResult
from mailler.tasks.send import send_email_task


class FakeProvider(EmailProvider):
    """Provider double returning a canned result and recording what it was given."""

    def __init__(self, result):
        self.result = result
        self.sent = []

    @property
    def provider_name(self):
        return "fake"

    def send_email(self, **kwargs):
        self.sent.append(kwargs)
        return self.result


@given('the provider accepts messages with id "{message_id}"')
def step_provider_accepts(context, message_id):
    context.provider = FakeProvider(EmailResult(success=True, provider_message_id=message_id))


@given('the provider rejects messages with "{error}"')
def step_provider_rejects(context, error):
    context.provider = FakeProvider(EmailResult(success=False, error_message=error))


@when('the send task runs for "{alias}"')
def step_run_send_task(context, alias):
    provider = getattr(context, "provider", None)
    patcher = (
        patch("mailler.tasks.send.get_provider", return_value=provider)
        if provider is not None
        else patch(
            "mailler.tasks.send.get_provider",
            side_effect=ValueError("Provider 'brevo' is not properly configured"),
        )
    )
    with patcher:
        context.task_result = send_email_task(context.created_ids[alias])


@then('the task result "{key}" should be "{value}"')
def step_task_result(context, key, value):
    assert str(context.task_result.get(key)) == value, context.task_result


@then('the task "{name}" should have been queued {count:d} time')
def step_task_queued(context, name, count):
    queued = [call for call in context.delayed if call[0] == name]
    assert len(queued) == count, f"Expected {count}, got {len(queued)}"


@then('the task "{name}" should have been queued for "{alias}"')
def step_task_queued_for(context, name, alias):
    expected = context.created_ids[alias]
    assert any(c[0] == name and c[1] == (expected,) for c in context.delayed), context.delayed


@then('the provider should have received the message to "{to_email}"')
def step_provider_received(context, to_email):
    assert any(call["to"] == to_email for call in context.provider.sent), context.provider.sent
