# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions shared across features."""

import json

from behave import then, when
from httpx import ASGITransport, AsyncClient


def send_request(context, method, path, headers=None):
    """Send a request to the ASGI application and store the response."""

    async def make_request():
        async with AsyncClient(
            transport=ASGITransport(app=context.app), base_url="http://test"
        ) as client:
            return await client.request(method, path, headers=headers)

    context.response = context.loop.run_until_complete(make_request())


@when('I send a GET request to "{path}"')
def step_send_get_request(context, path):
    """Send a GET request to the ASGI application."""
    send_request(context, "GET", path)


@then("the response status code should be {status_code:d}")
def step_check_status_code(context, status_code):
    """Check the response status code."""
    actual = context.response.status_code
    assert actual == status_code, f"Expected {status_code}, got {actual}: {context.response.text}"


@then('the response JSON field "{field}" should be "{value}"')
def step_check_json_field(context, field, value):
    """Check a top-level string field of the JSON response."""
    actual = json.loads(context.response.text)[field]
    assert str(actual) == value, f"Expected {value!r}, got {actual!r}"
