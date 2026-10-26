# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the REST API v1 feature.

Every request authenticates with a personal access token created through the
real ``PersonalAccessTokenService``; the application, the repositories and the
scope checks all run unchanged against the scenario database.
"""

import asyncio

from api_support import _body, _send, _user
from auth.db.models.rbac import Scope
from auth.services.pat import PersonalAccessTokenService
from behave import given, then, when
from sqlalchemy import select


# ------------------------------------------------------------------ fixtures
@given('"{email}" holds a personal access token with the scopes "{scopes}"')
def step_personal_access_token(context, email, scopes):
    user = _user(context, email)
    context.admin_id = user.id
    _pat, raw = asyncio.run(
        PersonalAccessTokenService().create_token(
            context.db, user_id=user.id, name="behave", scopes=scopes.split()
        )
    )
    context.database.commit()
    context.bearer = raw


@given('a custom scope "{name}" exists')
def step_custom_scope(context, name):
    resource, action = name.split(":")
    scope = Scope(name=name, resource=resource, action=action, category="custom", is_system=False)
    context.database.sync_session.add(scope)
    context.database.commit()
    context.scope_id = scope.id


# ------------------------------------------------------------------ requests
@when('I GET "{path}" with the bearer value "{value}"')
def step_bearer_value(context, path, value):
    context.bearer = value
    _send(context, "GET", path.replace("{admin_id}", ""))


@when('I {method:Method} "{path}" with the token')
def step_with_token(context, method, path):
    _send(context, method, path.replace("{admin_id}", str(getattr(context, "admin_id", ""))))


@when('I {method:Method} "{path}" with the token and the JSON body')
def step_with_token_and_body(context, method, path):
    _send(context, method, path, body=_body(context), remember=method == "POST")


@when("I {method:Method} the created resource with the token")
def step_created_resource(context, method):
    _send(context, method, context.created_path)


@when("I {method:Method} the created resource with the token and the JSON body")
def step_created_resource_body(context, method):
    _send(context, method, context.created_path, body=_body(context))


@when('with the token I {method:Method} the sub-path "{suffix}" of the created resource')
def step_created_sub_path(context, method, suffix):
    _send(context, method, context.created_path + suffix)


@when(
    'with the token I {method:Method} the sub-path "{suffix}" of the created resource '
    "and the JSON body"
)
def step_created_sub_path_body(context, method, suffix):
    _send(context, method, context.created_path + suffix, body=_body(context))


@when('I assign the created role to "{email}" with the token')
def step_assign_role(context, email):
    _send(
        context,
        "POST",
        context.created_path + "/users",
        body={"user_id": str(_user(context, email).id)},
    )


# ---------------------------------------------------------------- assertions
@then("the response contains a client secret")
def step_has_secret(context):
    assert context.response.json().get("client_secret"), context.response.text[:200]


@then("the response does not contain a client secret")
def step_no_secret(context):
    assert not context.response.json().get("client_secret"), context.response.text[:200]


@then("the response contains a new personal access token")
def step_new_pat(context):
    assert context.response.json()["token"].startswith("gab_pat_"), context.response.text[:200]


@then('the user "{email}" has the role "{name}"')
def step_has_role(context, email, name):
    from auth.db.models.rbac import Role, UserRole

    rows = context.database.sync_session.scalars(
        select(Role)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == _user(context, email).id)
    ).all()
    assert name in [role.name for role in rows], [role.name for role in rows]
