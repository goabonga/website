# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps shared by every feature: authenticate, call the application, check the response."""

import json
import re

from behave import given, step, then


def _expand(context, text: str) -> str:
    """Replace ${name} with a value remembered from an earlier response."""
    return re.sub(r"\$\{(\w+)\}", lambda m: str(context.vars[m.group(1)]), text)


def _field(data, path: str):
    for part in path.split("."):
        data = data[int(part)] if isinstance(data, list) else data[part]
    return data


@given('I am authenticated with the scopes "{scopes}"')
def step_authenticated(context, scopes: str) -> None:
    context.claims = {"sub": "6b3a1e0e-3f0a-4c9c-9a53-6a0f4f0f9a11", "scope": scopes}


@given("I am not authenticated")
def step_not_authenticated(context) -> None:
    context.claims = None


def _send(context, method: str, path: str, body: str | None = None) -> None:
    headers = {"Authorization": "Bearer header.payload.signature"} if context.claims else {}
    kwargs = {"json": json.loads(_expand(context, body))} if body is not None else {}
    context.response = context.get_client().request(
        method.upper(), _expand(context, path), headers=headers, **kwargs
    )


@step('I request "{path}"')
def step_request(context, path: str) -> None:
    _send(context, "GET", path)


@step('I send a {method} request to "{path}"')
def step_send(context, method: str, path: str) -> None:
    _send(context, method, path)


@step("I send a {method} request to \"{path}\" with the JSON '{body}'")
def step_send_json(context, method: str, path: str, body: str) -> None:
    _send(context, method, path, body)


@step('I remember the response field "{field}" as "{name}"')
def step_remember(context, field: str, name: str) -> None:
    context.vars[name] = _field(context.response.json(), field)


@then("the response status is {status:d}")
def step_status(context, status: int) -> None:
    assert context.response.status_code == status, (
        context.response.status_code,
        context.response.text,
    )


@then('the response JSON field "{field}" is "{value}"')
def step_json_field(context, field: str, value: str) -> None:
    assert str(_field(context.response.json(), field)) == _expand(context, value), (
        context.response.json()
    )


@then("the response JSON list has {count:d} items")
def step_json_list(context, count: int) -> None:
    data = context.response.json()
    assert isinstance(data, list) and len(data) == count, data


@then('the response has no field "{field}"')
def step_no_field(context, field: str) -> None:
    try:
        _field(context.response.json(), field)
    except (KeyError, IndexError):
        return
    raise AssertionError(f"unexpected field {field}")


@then('the response detail is "{detail}"')
def step_detail(context, detail: str) -> None:
    assert context.response.json()["detail"] == detail, context.response.json()
