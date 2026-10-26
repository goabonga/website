# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps shared by the features that exercise the public API."""

import json

from behave import given, then, when
from fakes import FakeSession, Store, make_auth_context

from knowledge.auth.dependencies import get_auth_context
from knowledge.database import get_db


def _install_auth(context):
    context.app.dependency_overrides[get_auth_context] = lambda: make_auth_context(
        context.user_id, context.scopes, getattr(context, "tenant_id", None)
    )


@given('I am authenticated as user "{user_id}" with scopes "{scopes}"')
def step_authenticated(context, user_id, scopes):
    context.user_id = user_id
    context.scopes = scopes
    context.store = getattr(context, "store", None) or Store()
    session = FakeSession(context.store)
    context.session = session

    async def fake_db():
        yield session

    _install_auth(context)
    context.app.dependency_overrides[get_db] = fake_db


@given('my tenant is "{tenant_id}"')
def step_tenant(context, tenant_id):
    context.tenant_id = tenant_id
    _install_auth(context)


@when('I send a {method} request to "{path}" with JSON')
def step_send_json(context, method, path):
    context.response = context.call(method.upper(), path, json=json.loads(context.text))


@then('the response JSON "{field}" should be "{value}"')
def step_json_value(context, field, value):
    data = context.response.json()
    for part in field.split("."):
        data = data[int(part)] if part.isdigit() else data[part]
    assert str(data) == value, f"expected {field}={value!r}, got {data!r}"


@then("the response should be a list of {count:d} items")
def step_list_count(context, count):
    data = context.response.json()
    assert isinstance(data, list) and len(data) == count, data
