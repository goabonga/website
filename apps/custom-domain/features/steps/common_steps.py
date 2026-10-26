# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps shared by every feature file."""

from behave import then, when
from environment import http_request


@when('I send a {method} request to "{path}"')
def step_send_request(context, method, path):
    http_request(context, method, path)


@then("the response status is {status:d}")
def step_response_status(context, status):
    assert context.response.status_code == status, context.response.text


@then('the JSON field "{field}" equals "{value}"')
def step_json_field_equals(context, field, value):
    assert str(context.response.json()[field]) == value


@then('the JSON field "{field}" is null')
def step_json_field_null(context, field):
    assert context.response.json()[field] is None
