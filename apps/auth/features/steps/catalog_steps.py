# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the catalog of scopes and roles."""

import json
import tempfile
from pathlib import Path

from auth.db.models.oauth2 import OAuth2Client
from auth.db.models.rbac import Role, RoleScope, Scope
from behave import given, then, when
from cli_support import run_command
from helpers import patch_setting
from sqlalchemy import select


def _write_catalog(context, text):
    if getattr(context, "catalog_dir", None) is None:
        directory = tempfile.TemporaryDirectory(prefix="auth-catalog-")
        context.add_cleanup(directory.cleanup)
        context.catalog_dir = Path(directory.name)
    context.catalog_path = context.catalog_dir / "catalog.json"
    context.catalog_path.write_text(text, encoding="utf-8")


@given("a catalog file:")
@given("the catalog file is replaced by:")
def step_catalog_file(context):
    _write_catalog(context, context.text)


@given("the catalog was synchronised")
def step_catalog_synchronised(context):
    run_command(context, "auth catalog sync", "--file", str(context.catalog_path))
    assert context.command_status == 0, context.command_stderr


@given("the CATALOG_FILE setting points to the catalog file")
def step_catalog_setting(context):
    patch_setting(context, "catalog_file", str(context.catalog_path))


@given(
    'an OAuth2 client "{client_id}" allowed the scopes "{scopes}" and the grant types "{grants}"'
)
def step_client(context, client_id, scopes, grants):
    session = context.database.sync_session
    session.add(
        OAuth2Client(
            client_id=client_id,
            name=client_id,
            redirect_uris=["https://client.example.test/callback"],
            allowed_scopes=scopes.split(", "),
            allowed_grant_types=grants.split(", "),
        )
    )
    context.database.commit()


@when('I run "{command}" with the catalog file')
def step_run_with_file(context, command):
    run_command(context, command, "--file", str(context.catalog_path))


@when('I run "{command}"')
def step_run(context, command):
    run_command(context, command)


@then("the command exits with {status:d}")
def step_exit_status(context, status):
    assert context.command_status == status, (
        context.command_status,
        context.command_stdout,
        context.command_stderr,
    )


@then('the command prints "{text}"')
def step_prints(context, text):
    assert text in context.command_stdout, context.command_stdout


@then('the command reports the error "{text}"')
def step_reports_error(context, text):
    assert text in context.command_stderr, context.command_stderr


@then("the JSON report says nothing changed")
def step_json_unchanged(context):
    report = json.loads(context.command_stdout)
    assert report["changed"] is False and not report["created"] and not report["updated"], report


def _scope(context, name):
    return context.database.sync_session.scalars(select(Scope).where(Scope.name == name)).first()


@then('the scope "{name}" exists in the category "{category}" with the description "{description}"')
def step_scope_exists(context, name, category, description):
    scope = _scope(context, name)
    assert scope is not None, name
    assert (scope.category, scope.description) == (category, description)


@then('no scope "{name}" exists')
def step_no_scope(context, name):
    assert _scope(context, name) is None


@then('the role "{name}" holds the scopes "{scopes}"')
def step_role_scopes(context, name, scopes):
    session = context.database.sync_session
    role = session.scalars(select(Role).where(Role.name == name)).one()
    held = session.scalars(
        select(Scope.name)
        .join(RoleScope, RoleScope.scope_id == Scope.id)
        .where(RoleScope.role_id == role.id)
    ).all()
    assert sorted(held) == sorted(scopes.split(", ")), held


@then('no role "{name}" exists')
def step_no_role(context, name):
    session = context.database.sync_session
    assert session.scalars(select(Role).where(Role.name == name)).first() is None


def _client(context, client_id):
    return context.database.sync_session.scalars(
        select(OAuth2Client).where(OAuth2Client.client_id == client_id)
    ).first()


@then('the client "{client_id}" is allowed the scopes "{scopes}"')
def step_client_scopes(context, client_id, scopes):
    assert _client(context, client_id).allowed_scopes == scopes.split(", ")


@then('the client "{client_id}" is allowed the grant types "{grants}"')
def step_client_grants(context, client_id, grants):
    assert _client(context, client_id).allowed_grant_types == grants.split(", ")


@then('no OAuth2 client "{client_id}" exists')
def step_no_client(context, client_id):
    assert _client(context, client_id) is None
