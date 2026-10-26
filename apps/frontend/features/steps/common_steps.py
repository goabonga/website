# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps shared by every feature: configure settings, call the app, check the response."""

from behave import given, then, when


@given('the setting "{name}" is "{value}"')
def step_setting(context, name: str, value: str) -> None:
    context.overrides[name] = value


@given('the setting "{name}" is the list "{values}"')
def step_setting_list(context, name: str, values: str) -> None:
    context.overrides[name] = [item.strip() for item in values.split(",")]


@when('I request "{path}"')
def step_request(context, path: str) -> None:
    context.response = context.get_client().get(path)


@when('I send "{path}" with header "{header}" set to "{value}"')
def step_request_with_header(context, path: str, header: str, value: str) -> None:
    context.response = context.get_client().get(path, headers={header: value})


@then("the response status is {status:d}")
def step_status(context, status: int) -> None:
    assert context.response.status_code == status, context.response.status_code


@then('the response JSON field "{field}" is "{value}"')
def step_json_field(context, field: str, value: str) -> None:
    assert context.response.json()[field] == value


@then('the response header "{header}" is "{value}"')
def step_header(context, header: str, value: str) -> None:
    assert context.response.headers.get(header) == value, context.response.headers


@then('the response header "{header}" is present')
def step_header_present(context, header: str) -> None:
    assert header in context.response.headers, context.response.headers


@then('the response header "{header}" is absent')
def step_header_absent(context, header: str) -> None:
    assert header not in context.response.headers


@then('the response body contains "{text}"')
def step_body_contains(context, text: str) -> None:
    assert text in context.response.text
