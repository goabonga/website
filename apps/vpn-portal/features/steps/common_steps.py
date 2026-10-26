# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Shared step definitions for HTTP requests and response assertions."""

from behave import then, when
from httpx import ASGITransport, AsyncClient


async def _request(app, method, url, headers):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=headers
    ) as client:
        return await client.request(method, url)


@when('I send a GET request to "{url}"')
def step_send_get(context, url):
    context.response = context.run(_request(context.app, "GET", url, context.headers))


@then("the response status code should be {code:d}")
def step_check_status_code(context, code):
    assert context.response.status_code == code, (
        f"Expected status {code}, got {context.response.status_code}. Body: {context.response.text}"
    )


@then('the response should contain "{key}" with value "{value}"')
def step_check_response_value(context, key, value):
    body = context.response.json()
    assert key in body, f"Response missing key '{key}'. Body: {body}"
    assert str(body[key]) == value, f"Expected {key}='{value}', got '{body[key]}'"
