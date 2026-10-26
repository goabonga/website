# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps shared by every feature file."""

from behave import then, when


@when('I request "{path}"')
def request_path(context, path):
    context.response = context.client.get(path)


@then("the response status is {status:d}")
def check_status(context, status):
    assert context.response.status_code == status, (
        f"expected {status}, got {context.response.status_code}: {context.response.text}"
    )


@then('the JSON field "{field}" is "{value}"')
def check_json_field(context, field, value):
    assert str(context.response.json()[field]) == value
