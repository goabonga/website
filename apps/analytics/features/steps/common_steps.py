# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions shared by every feature."""

import json

from behave import then, when
from httpx import ASGITransport, AsyncClient


def send_request(context, method, path, **kwargs):
    """Send a request to the ASGI application and store the response."""

    async def make_request():
        async with AsyncClient(
            transport=ASGITransport(app=context.app),
            base_url="http://test",
        ) as client:
            return await client.request(method, path, **kwargs)

    context.response = context.loop.run_until_complete(make_request())
    context.response_json = None


def response_json(context):
    """Return the parsed JSON body of the last response."""
    if context.response_json is None:
        context.response_json = context.response.json()
    return context.response_json


@when('I send a GET request to "{path}"')
def step_send_get_request(context, path):
    send_request(context, "GET", path)


@then("the response status code should be {status_code:d}")
def step_check_status_code(context, status_code):
    actual = context.response.status_code
    assert actual == status_code, f"Expected {status_code}, got {actual}: {context.response.text}"


@then('the response content type should be "{content_type}"')
def step_check_content_type(context, content_type):
    actual = context.response.headers.get("content-type", "")
    assert content_type in actual, f"Expected '{content_type}', got '{actual}'"


@then('the response should contain "{text}"')
def step_response_contains_text(context, text):
    assert text in context.response.text, f"Expected '{text}' in response: {context.response.text}"


@then("the response should be valid JSON")
def step_response_is_json(context):
    try:
        context.response_json = context.response.json()
    except json.JSONDecodeError as e:
        raise AssertionError(f"Response is not valid JSON: {e}") from e


@then('the response JSON key "{key}" should equal "{value}"')
def step_json_key_equals(context, key, value):
    actual = str(response_json(context).get(key))
    assert actual == value, f"Expected {key}='{value}', got '{actual}'"
