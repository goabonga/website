# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The administration console only shows the controls the signed-in admin can use.

Each control is rendered from the real template, once with the scope that the
matching route requires and once without it. The routes stay the authority (they
answer 403); the templates must never offer an action that would be refused.
"""

from pathlib import Path

import auth
import pytest
from auth.api.deps import get_user_admin_permissions
from auth.db.models.rbac import Role
from jinja2 import ChainableUndefined, Environment, FileSystemLoader

TEMPLATES = Path(auth.__file__).parent / "templates"
ENV = Environment(
    loader=FileSystemLoader(str(TEMPLATES)), autoescape=True, undefined=ChainableUndefined
)

SCOPE = {"id": "s1", "name": "custom:read", "is_system": False, "is_active": True}
USER = {"id": "u1", "email": "a@example.com", "is_active": True, "active_sessions": 2}
ROLE = {
    "id": "r1",
    "name": "editor",
    "description": "",
    "scopes": [],
    "explicit_scopes": [],
    "users": [],
    "is_system": False,
    "user_count": 0,
}
TENANT = {"id": "t1", "display_name": "Acme", "slug": "acme", "is_active": True}


def _roles(*scopes):
    role = Role(name="test", description="", is_system=False)
    role.has_scope = lambda required: _holds(scopes, required)
    return [role]


def _holds(scopes, required):
    resource = required.split(":")[0]
    return "*" in scopes or required in scopes or f"{resource}:*" in scopes


def _render(template, held, **context):
    permissions = get_user_admin_permissions(_roles(*held))
    return ENV.get_template(template).render(permissions=permissions, **context)


# (template, context, marker of the control, scope that the route of the control requires)
CASES = [
    # the scopes pages are guarded by scopes:* in scopes_pages.py
    ("admin/scopes/list.html", {"scopes": []}, 'href="/admin/scopes/create"', "scopes:write"),
    ("admin/scopes/list.html", {"scopes": []}, 'action="/admin/scopes/seed"', "scopes:write"),
    (
        "admin/scopes/list.html",
        {"scopes": [SCOPE], "total_pages": 1},
        "/admin/scopes/s1/delete",
        "scopes:delete",
    ),
    ("admin/scopes/detail.html", {"scope": SCOPE}, "/admin/scopes/s1/toggle", "scopes:write"),
    ("admin/scopes/detail.html", {"scope": SCOPE}, "/admin/scopes/s1/delete", "scopes:delete"),
    # editing a custom role is a roles:write route, a system role has no such link
    (
        "admin/roles/detail.html",
        {"role": ROLE, "available_scopes": {}},
        "/admin/roles/r1/edit",
        "roles:write",
    ),
    (
        "admin/roles/detail.html",
        {"role": ROLE, "available_scopes": {}},
        "/admin/roles/r1/delete",
        "roles:delete",
    ),
    # revoking the sessions of a user is a users:write route
    ("admin/users/detail.html", {"user": USER}, "/admin/users/u1/revoke-sessions", "users:write"),
    ("admin/users/detail.html", {"user": USER}, "/admin/users/u1/disable", "users:disable"),
    ("admin/users/detail.html", {"user": USER}, "/admin/users/u1/delete", "users:delete"),
    # the dashboard quick actions lead to read pages
    ("admin/dashboard.html", {}, 'href="/admin/users"', "users:read"),
    ("admin/dashboard.html", {}, 'href="/admin/clients"', "clients:read"),
    ("admin/dashboard.html", {}, 'href="/admin/sessions"', "sessions:read"),
    ("admin/dashboard.html", {}, 'href="/admin/roles"', "roles:read"),
    # the navigation: the dashboard route requires users:read, the scopes pages scopes:read
    ("admin/dashboard.html", {}, 'class="active"', "users:read"),
    ("admin/scopes/list.html", {"scopes": []}, 'href="/admin/scopes"', "scopes:read"),
    # the pages that display the organisation settings save them with org:write
    (
        "admin/tenants/registration_fields.html",
        {"tenant": TENANT, "fields": {}},
        "Save Configuration",
        "org:write",
    ),
    (
        "admin/tenants/profile_fields.html",
        {"tenant": TENANT, "fields": {}},
        "Save Configuration",
        "org:write",
    ),
    (
        "admin/tenants/allowed_scopes.html",
        {"tenant": TENANT, "scope_groups": {}, "current_allowed": []},
        "Save Configuration",
        "org:write",
    ),
]


@pytest.mark.parametrize(("template", "context", "marker", "scope"), CASES)
def test_control_requires_the_scope_of_its_route(template, context, marker, scope):
    others = [s for s in ("users:read", "roles:read") if s != scope]
    base = {"active_section": "dashboard", **context}
    assert marker in _render(template, [scope, *others], **base)
    # every other scope of the console, except the one that the route requires
    unrelated = [
        s
        for s in (
            "users:read",
            "users:write",
            "users:disable",
            "users:delete",
            "clients:read",
            "clients:write",
            "sessions:read",
            "sessions:revoke",
            "roles:read",
            "roles:write",
            "roles:delete",
            "scopes:read",
            "scopes:write",
            "scopes:delete",
            "org:read",
        )
        if s != scope
    ]
    assert marker not in _render(template, unrelated, **base)


def test_system_roles_are_not_offered_the_edit_link():
    page = _render(
        "admin/roles/detail.html", ["*"], role={**ROLE, "is_system": True}, available_scopes={}
    )
    assert "/admin/roles/r1/edit" not in page
    assert "System roles cannot be modified or deleted" in page


def test_edit_form_checks_the_scopes_the_role_holds():
    page = _render(
        "admin/roles/edit.html",
        ["roles:write"],
        role=ROLE,
        available_scopes={"users:read": "View users", "users:write": None},
        held_scopes=["users:read"],
    )
    assert 'action="/admin/roles/r1/edit"' in page
    assert 'value="users:read" checked' in page
    assert 'value="users:write" checked' not in page
