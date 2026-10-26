# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the administration console feature."""

import asyncio

from auth.db.models.rbac import Role, RoleScope, Scope, UserRole
from auth.db.models.user import User, UserEmail
from auth.services.session import SessionService
from behave import given, then, when
from sqlalchemy import func, select

SESSION_COOKIE = "session"


def _session(context):
    return context.database.sync_session


def _user(context, email):
    return (
        _session(context)
        .scalars(select(User).join(UserEmail).where(func.lower(UserEmail.email) == email.lower()))
        .one()
    )


def _get(context, path, **kwargs):
    context.response = context.client.get(path, follow_redirects=False, **kwargs)


# ------------------------------------------------------------------ fixtures
@given('"{email}" holds the administrator role')
def step_administrator_role(context, email):
    session = _session(context)
    role = session.scalars(select(Role).where(Role.name == "console_admin")).first()
    if role is None:
        scope = Scope(name="*", resource="*", action="*", category="admin", is_system=True)
        role = Role(name="console_admin", description="Console administrators", is_system=True)
        session.add_all([scope, role])
        session.flush()
        session.add(RoleScope(role_id=role.id, scope_id=scope.id))
    session.add(UserRole(role_id=role.id, user_id=_user(context, email).id))
    context.database.commit()


def _scope_names(scopes):
    """The names of `"roles:read" and "users:read"`."""
    return [name.strip('" ') for name in scopes.split(" and ")]


def _scope(session, name):
    scope = session.scalars(select(Scope).where(Scope.name == name)).first()
    if scope is None:
        resource, action = name.split(":")
        scope = Scope(name=name, resource=resource, action=action, category="admin")
        session.add(scope)
        session.flush()
    return scope


def _role(context, name):
    return _session(context).scalars(select(Role).where(Role.name == name)).one()


@given('"{email}" holds a role limited to {scopes}')
def step_limited_role(context, email, scopes):
    """A role that only holds the listed scopes, for instance `"roles:read" and "users:read"`."""
    names = _scope_names(scopes)
    session = _session(context)
    role = Role(name=f"limited_{len(names)}_{email}", description="Limited role", is_system=False)
    session.add(role)
    session.flush()
    for name in names:
        session.add(RoleScope(role_id=role.id, scope_id=_scope(session, name).id))
    session.add(UserRole(role_id=role.id, user_id=_user(context, email).id))
    context.database.commit()


@given('the scope "{name}" exists')
def step_scope_exists(context, name):
    _scope(_session(context), name)
    context.database.commit()


@given('a custom role "{name}" holds the scopes {scopes}')
def step_custom_role(context, name, scopes):
    session = _session(context)
    role = Role(name=name, description="Custom role", is_system=False)
    session.add(role)
    session.flush()
    for scope in _scope_names(scopes):
        session.add(RoleScope(role_id=role.id, scope_id=_scope(session, scope).id))
    context.database.commit()


@given('an administrator session for "{email}"')
def step_administrator_session(context, email):
    token, _csrf = asyncio.run(
        SessionService().create_session(context.db, str(_user(context, email).id))
    )
    context.database.commit()
    context.client.cookies.set(SESSION_COOKIE, token)


# ------------------------------------------------------------------ requests
@when('I open the admin page "{path}"')
def step_open_page(context, path):
    _get(context, path)


@when('I open the admin page "{path}" with the token')
def step_open_page_with_token(context, path):
    _get(context, path, headers={"Authorization": f"Bearer {context.bearer}"})


@when('I open the detail page of the user "{email}"')
def step_open_user(context, email):
    _get(context, f"/admin/users/{_user(context, email).id}")


@when('I submit the admin form "{path}" with')
def step_submit_form(context, path):
    data = {row["field"]: row["value"] for row in context.table}
    context.response = context.client.post(path, data=data, follow_redirects=False)


@when('I open the edit page of the role "{name}"')
def step_open_role_edit(context, name):
    _get(context, f"/admin/roles/{_role(context, name).id}/edit")


@when('I submit the edit form of the role "{name}" with')
def step_submit_role_edit(context, name):
    data = {}
    for row in context.table:
        data.setdefault(row["field"], []).append(row["value"])
    context.response = context.client.post(
        f"/admin/roles/{_role(context, name).id}/edit", data=data, follow_redirects=False
    )


@when('I post to the admin action "{action}" of the user "{email}"')
def step_user_action(context, action, email):
    context.response = context.client.post(
        f"/admin/users/{_user(context, email).id}/{action}", follow_redirects=False
    )


# ---------------------------------------------------------------- assertions
@then('the user "{email}" is disabled')
def step_user_disabled(context, email):
    _session(context).expire_all()
    assert _user(context, email).is_active is False


@then('the user "{email}" is enabled')
def step_user_enabled(context, email):
    _session(context).expire_all()
    assert _user(context, email).is_active is True


@then('the role "{name}" holds exactly the scopes {scopes}')
def step_role_scopes(context, name, scopes):
    _session(context).expire_all()
    held = {link.scope.name for link in _role(context, name).role_scopes}
    assert held == set(_scope_names(scopes)), held
