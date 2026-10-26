# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions shared across features."""

import json

from behave import then, when
from httpx import ASGITransport, AsyncClient


@when('I send a GET request to "{path}"')
def step_send_get_request(context, path):
    """Send a GET request to the ASGI application."""

    async def make_request():
        async with AsyncClient(
            transport=ASGITransport(app=context.app), base_url="http://test"
        ) as client:
            return await client.get(path)

    context.response = context.loop.run_until_complete(make_request())


@then("the response status code should be {status_code:d}")
def step_check_status_code(context, status_code):
    """Check the response status code."""
    actual = context.response.status_code
    assert actual == status_code, f"Expected {status_code}, got {actual}: {context.response.text}"


@then('the response content type should be "{content_type}"')
def step_check_content_type(context, content_type):
    """Check the response content type."""
    actual = context.response.headers.get("content-type", "")
    assert content_type in actual, f"Expected '{content_type}', got '{actual}'"


@then('the response should contain "{text}"')
def step_response_contains_text(context, text):
    """Check that the response body contains specific text."""
    assert text in context.response.text, f"Expected '{text}' in response: {context.response.text}"


@then('the response header "{header}" should contain "{value}"')
def step_check_response_header(context, header, value):
    """Check that a response header contains a value."""
    actual = context.response.headers.get(header.lower(), "")
    assert value in actual, f"Expected '{value}' in header '{header}', got '{actual}'"


@then("the response should be valid JSON")
def step_response_is_json(context):
    """Check that the response body is valid JSON."""
    try:
        context.response_json = context.response.json()
    except json.JSONDecodeError as e:
        raise AssertionError(f"Response is not valid JSON: {e}") from e


@then('the response JSON key "{key}" should equal "{value}"')
def step_json_key_equals(context, key, value):
    """Check that a JSON key has a specific value."""
    payload = context.response.json()
    actual = str(payload.get(key))
    assert actual == value, f"Expected {key}='{value}', got '{actual}'"
