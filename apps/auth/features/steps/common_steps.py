# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions shared by every feature file."""

from behave import then, when


@when('I send a {method} request to "{path}"')
def step_send_request(context, method, path):
    context.response = context.client.request(method, path)


@when('I request "{path}" with the Accept header "{accept}"')
def step_request_accepting(context, path, accept):
    context.response = context.client.get(path, headers={"Accept": accept})


@then("the response status is {status:d}")
def step_response_status(context, status):
    assert context.response.status_code == status, (
        f"expected {status}, got {context.response.status_code}: {context.response.text[:300]}"
    )


@then('the response JSON field "{field}" is "{value}"')
def step_response_json_field(context, field, value):
    actual = context.response.json()[field]
    assert str(actual) == value, f"{field}: expected {value!r}, got {actual!r}"


@then('the response body contains "{text}"')
def step_response_body_contains(context, text):
    assert text in context.response.text, f"{text!r} not found in {context.response.text[:300]!r}"


@then('the response body does not contain "{text}"')
def step_response_body_does_not_contain(context, text):
    assert text not in context.response.text, f"{text!r} found in the response body"
