# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Shared step definitions for HTTP requests and response assertions."""

import json

from behave import then, when
from httpx import ASGITransport, AsyncClient


async def _request(app, method, url, headers, body=None):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=headers
    ) as client:
        return await client.request(method, url, json=body)


@when('I send a GET request to "{url}"')
def step_send_get(context, url):
    context.response = context.run(_request(context.app, "GET", url, context.headers))


@when('I send a POST request to "{url}"')
def step_send_post(context, url):
    context.response = context.run(_request(context.app, "POST", url, context.headers))


@when('I send a POST request to "{url}" with body:')
def step_send_post_with_body(context, url):
    body = json.loads(context.text)
    context.response = context.run(_request(context.app, "POST", url, context.headers, body))


@then("the response status code should be {code:d}")
def step_check_status_code(context, code):
    assert context.response.status_code == code, (
        f"Expected status {code}, got {context.response.status_code}. Body: {context.response.text}"
    )


@then('the response should contain "{key}" with value "{value}"')
def step_check_response_value(context, key, value):
    body = context.response.json()
    assert key in body, f"Response missing key '{key}'. Body: {body}"
    actual = body[key]
    if value in ("true", "false"):
        assert actual is (value == "true"), f"Expected {key}={value}, got {actual}"
    else:
        assert str(actual) == value, f"Expected {key}='{value}', got '{actual}'"


@then('the response body should include "{key}"')
def step_check_response_contains_key(context, key):
    body = context.response.json()
    assert key in body, f"Response missing key '{key}'. Body: {body}"


@then('the response should contain "{key}" as a list')
def step_check_response_list(context, key):
    body = context.response.json()
    assert key in body, f"Response missing key '{key}'. Body: {body}"
    assert isinstance(body[key], list), f"Expected {key} to be a list, got {type(body[key])}"


@then('the response "{key}" should be null')
def step_check_response_null(context, key):
    body = context.response.json()
    assert key in body, f"Response missing key '{key}'. Body: {body}"
    assert body[key] is None, f"Expected {key} to be null, got {body[key]}"


@then('the response "{key}" should not be null')
def step_check_response_not_null(context, key):
    body = context.response.json()
    assert key in body, f"Response missing key '{key}'. Body: {body}"
    assert body[key] is not None, f"Expected {key} to not be null"
