# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the status callback scenarios.

The endpoint of the client is replaced by a recorder, nothing goes on the network.
"""

import json
from unittest.mock import patch

import httpx
from behave import given, then, when
from mailler.services.callbacks import sign
from mailler.tasks.callbacks import CallbackFailed, deliver_status_callback
from steps.database_steps import load_email


@given("the client endpoint answers {status:d}")
def step_endpoint_answers(context, status):
    context.endpoint_status = status


def _recorder(context):
    context.endpoint_calls = []

    def post(url, content=None, headers=None, timeout=None):
        context.endpoint_calls.append({"url": url, "body": content, "headers": headers})
        return httpx.Response(getattr(context, "endpoint_status", 200))

    return post


@when('the callback task runs for the email to "{to_email}"')
def step_run_callback_task(context, to_email):
    email = load_email(to_email=to_email)
    context.callback_error = None
    context.callback_result = None
    with patch("mailler.tasks.callbacks.httpx.post", _recorder(context)):
        try:
            context.callback_result = deliver_status_callback(str(email.id), email.status)
        except CallbackFailed as error:
            context.callback_error = str(error)


@then("the client endpoint should have received {count:d} notification")
@then("the client endpoint should have received {count:d} notifications")
def step_endpoint_received(context, count):
    assert len(context.endpoint_calls) == count, context.endpoint_calls


@then('the notification should be posted to "{url}"')
def step_notification_url(context, url):
    assert context.endpoint_calls[-1]["url"] == url, context.endpoint_calls[-1]["url"]


@then('the notification should be signed with the secret "{secret}"')
def step_notification_signed(context, secret):
    call = context.endpoint_calls[-1]
    timestamp = call["headers"]["X-Mailler-Timestamp"]
    assert call["headers"]["X-Mailler-Signature"] == sign(secret, timestamp, call["body"])
    assert call["headers"]["X-Mailler-Signature"] != sign("another-secret", timestamp, call["body"])


@then('the notification field "{field}" should be "{value}"')
def step_notification_field(context, field, value):
    payload = json.loads(context.endpoint_calls[-1]["body"])
    assert str(payload[field]) == value, payload


@then("the callback task should be delivered again later")
def step_callback_retried(context):
    assert context.callback_error, "The callback task did not fail"


@then("the callback task should have delivered the notification")
def step_callback_delivered(context):
    assert context.callback_result == {"delivered": True, "http_status": 200}, (
        context.callback_result
    )
