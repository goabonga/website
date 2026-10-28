# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the synchronisation of the system roles of the organisations."""

import json

from auth.db.models.tenant import DEFAULT_TENANT_ROLES, TenantCustomRole
from behave import given, then
from cli_support import run_command
from organisation_api_steps import _tenant
from sqlalchemy import select


def _roles(context, slug):
    context.database.sync_session.expire_all()
    return {
        role.name: role
        for role in context.database.sync_session.scalars(
            select(TenantCustomRole).where(TenantCustomRole.tenant_id == _tenant(context, slug).id)
        )
    }


# ------------------------------------------------------------------ fixtures
@given('the organisation "{slug}" was created before the admin role held "{scope}"')
def step_legacy_admin(context, slug, scope):
    role = _roles(context, slug)["admin"]
    role.scopes = [s for s in role.scopes if s != scope]
    context.database.commit()


@given('the "{name}" role of the organisation "{slug}" also grants "{scope}"')
def step_role_also_grants(context, name, slug, scope):
    role = _roles(context, slug)[name]
    role.scopes = [*role.scopes, scope]
    context.database.commit()


@given('the organisation "{slug}" lost its "{name}" role')
def step_role_lost(context, slug, name):
    context.database.sync_session.delete(_roles(context, slug)[name])
    context.database.commit()


@given("the system roles were synchronised")
def step_synchronised(context):
    run_command(context, "auth tenant-roles sync")
    assert context.command_status == 0, context.command_stderr


# ---------------------------------------------------------------- assertions
@then('the "{name}" role of the organisation "{slug}" grants "{scope}"')
def step_role_grants(context, name, slug, scope):
    assert scope in _roles(context, slug)[name].scopes, _roles(context, slug)[name].scopes


@then('the "{name}" role of the organisation "{slug}" does not grant "{scope}"')
def step_role_does_not_grant(context, name, slug, scope):
    assert scope not in _roles(context, slug)[name].scopes, _roles(context, slug)[name].scopes


@then('the "{name}" role of the organisation "{slug}" grants exactly "{scopes}"')
def step_role_grants_exactly(context, name, slug, scopes):
    assert sorted(_roles(context, slug)[name].scopes) == sorted(scopes.split(", "))


@then('the organisation "{slug}" has the roles "{names}"')
def step_org_has_roles(context, slug, names):
    assert set(_roles(context, slug)) == set(names.split(", ")), set(_roles(context, slug))
    assert set(DEFAULT_TENANT_ROLES) <= set(_roles(context, slug))


@then('the JSON report says the organisation "{slug}" received "{scope}" on the role "{role}"')
def step_json_received(context, slug, scope, role):
    report = json.loads(context.command_stdout)
    assert report["changed"] is True, report
    assert scope in report["tenants"][slug]["added"][role], report["tenants"]
