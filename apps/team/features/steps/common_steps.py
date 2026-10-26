# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps shared by every feature: call the application and check the response."""

from behave import then, when


@when('I request "{path}"')
def step_request(context, path: str) -> None:
    context.response = context.get_client().get(path)


@then("the response status is {status:d}")
def step_status(context, status: int) -> None:
    assert context.response.status_code == status, context.response.status_code


@then('the response JSON field "{field}" is "{value}"')
def step_json_field(context, field: str, value: str) -> None:
    data = context.response.json()
    for part in field.split("."):
        data = data[part]
    assert str(data) == value, context.response.json()
