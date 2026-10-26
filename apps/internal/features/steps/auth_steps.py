# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Authentication step definitions for BDD tests."""

import uuid

from behave import given

TEST_USER_ID = "00000000-0000-0000-0000-000000000001"


@given("I am authenticated")
def step_authenticated(context):
    context.authenticated = True
    context.user_scopes = "*"
    context.configure_auth(context)


@given("I am not authenticated")
def step_not_authenticated(context):
    context.authenticated = False
    context.configure_auth(context)


@given('I am authenticated with scope "{scope}"')
def step_authenticated_with_scope(context, scope):
    context.authenticated = True
    context.user_scopes = scope
    context.configure_auth(context)


@given('I am authenticated with scopes "{scopes}"')
def step_authenticated_with_scopes(context, scopes):
    context.authenticated = True
    context.user_scopes = scopes
    context.configure_auth(context)


@given("I am a super admin")
def step_super_admin(context):
    context.authenticated = True
    context.user_scopes = "*"
    context.configure_auth(context)


@given('I am authenticated as user "{email}"')
def step_authenticated_as_user(context, email):
    context.authenticated = True
    context.user_email = email
    context.user_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, email))
    context.configure_auth(context)
