# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Generic HTTP steps shared by every feature."""

from behave import then, when


@when('I send a {method} request to "{path}"')
def step_send_request(context, method, path):
    context.response = context.call(method.upper(), path)


@then("the response status code should be {status_code:d}")
def step_status_code(context, status_code):
    assert context.response.status_code == status_code, (
        f"expected {status_code}, got {context.response.status_code}: {context.response.text}"
    )


@then('the response field "{field}" should be "{value}"')
def step_json_field(context, field, value):
    actual = context.response.json()[field]
    assert str(actual) == value, f"expected {field}={value!r}, got {actual!r}"


@then('the response header "{name}" should be present')
def step_header_present(context, name):
    assert name in context.response.headers, (
        f"header {name!r} missing: {dict(context.response.headers)}"
    )


@then('the redirect location should be "{location}"')
def step_redirect_location(context, location):
    assert context.response.headers["location"] == location, context.response.headers
