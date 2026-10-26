# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Reusable step definitions for HTTP requests and response assertions."""

import json

from behave import then, when
from httpx import ASGITransport, AsyncClient


def _get_cookies(context) -> dict[str, str]:
    """Get cookies for the request based on auth state."""
    if getattr(context, "authenticated", False):
        return {"access_token": "test-token"}
    return {}


def _make_request(context, method, path, **kwargs):
    """Make an HTTP request to the app."""
    cookies = _get_cookies(context)

    async def _do_request():
        async with AsyncClient(
            transport=ASGITransport(app=context.app),
            base_url="http://test",
            cookies=cookies,
            follow_redirects=False,
        ) as client:
            return await getattr(client, method)(path, **kwargs)

    context.response = context.loop.run_until_complete(_do_request())
    return context.response


# --- HTTP Request Steps ---


@when('I send a GET request to "{path}"')
def step_send_get(context, path):
    _make_request(context, "get", path)


@when('I send a POST request to "{path}"')
def step_send_post(context, path):
    _make_request(context, "post", path)


@when('I send a POST request to "{path}" with form data')
def step_send_post_form(context, path):
    """POST with form data from a table.

    Supports multi-value fields (same field name repeated) via multipart encoding.

    Example:
        When I send a POST request to "/contacts/new" with form data
            | field      | value           |
            | email      | test@test.com   |
            | first_name | John            |
    """
    fields = [row["field"] for row in context.table]
    has_duplicates = len(fields) != len(set(fields))

    if has_duplicates:
        # Use multipart encoding for multi-value fields (e.g., bulk delete)
        files = [(row["field"], (None, row["value"])) for row in context.table]
        _make_request(context, "post", path, files=files)
    else:
        data = {}
        for row in context.table:
            data[row["field"]] = row["value"]
        _make_request(context, "post", path, data=data)


@when('I send a POST request to "{path}" with JSON body')
def step_send_post_json(context, path):
    """POST with JSON body from text block.

    Example:
        When I send a POST request to "/api/compile" with JSON body
            \"\"\"
            {"mjml_source": "<mjml>...</mjml>"}
            \"\"\"
    """
    body = json.loads(context.text)
    _make_request(context, "post", path, json=body)


# --- Response Assertion Steps ---


@then("the response status code should be {status_code:d}")
def step_check_status_code(context, status_code):
    actual = context.response.status_code
    assert actual == status_code, (
        f"Expected status {status_code}, got {actual}.\nResponse: {context.response.text[:500]}"
    )


@then('I should be redirected to "{url}"')
def step_check_redirect_exact(context, url):
    actual = context.response.status_code
    assert actual in (301, 302, 303, 307, 308), f"Expected redirect, got status {actual}"
    location = context.response.headers.get("location", "")
    assert location == url, f"Expected redirect to '{url}', got '{location}'"


@then('I should be redirected to a URL containing "{fragment}"')
def step_check_redirect_contains(context, fragment):
    actual = context.response.status_code
    assert actual in (301, 302, 303, 307, 308), f"Expected redirect, got status {actual}"
    location = context.response.headers.get("location", "")
    assert fragment in location, f"Expected redirect URL to contain '{fragment}', got '{location}'"


@then('the response should contain "{text}"')
def step_check_response_contains(context, text):
    body = context.response.text
    assert text in body, (
        f"Expected response to contain '{text}'.\nResponse ({len(body)} chars): {body[:500]}"
    )


@then('the response should not contain "{text}"')
def step_check_response_not_contains(context, text):
    body = context.response.text
    assert text not in body, f"Expected response NOT to contain '{text}', but it does."


@then("the response should be HTML")
def step_check_html(context):
    content_type = context.response.headers.get("content-type", "")
    assert "text/html" in content_type, f"Expected text/html, got '{content_type}'"


@then("the response should be valid JSON")
def step_check_json(context):
    try:
        context.response.json()
    except Exception as e:
        raise AssertionError(f"Response is not valid JSON: {e}")


@then('the response JSON should have key "{key}"')
def step_check_json_key(context, key):
    data = context.response.json()
    assert key in data, f"JSON missing key '{key}'. Keys: {list(data.keys())}"


@then('the response JSON key "{key}" should equal "{value}"')
def step_check_json_key_value(context, key, value):
    data = context.response.json()
    actual = str(data.get(key, ""))
    assert actual == value, f"Expected JSON['{key}'] == '{value}', got '{actual}'"
