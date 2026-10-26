# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The organisation settings pages only show the controls the member can use.

The pages receive `can`, an :class:`OrgPermissions` built from the membership, and the
templates ask `can["idp:write"]`. Each control is rendered from the real template for a
member who holds the scope that the route behind it requires (the control is there) and
for a member who holds every other organisation scope but that one (it is not). The
routes stay the authority: ``test_routes_auth_settings_org_scopes`` drives each of them
and expects 403 without the scope.
"""

from pathlib import Path

import auth
import pytest
from auth.api.routes.auth.settings import OrgPermissions
from auth.db.models.tenant import TENANT_SCOPES, TenantCustomRole, TenantMember
from jinja2 import ChainableUndefined, Environment, FileSystemLoader

TEMPLATES = Path(auth.__file__).parent / "templates"
ENV = Environment(
    loader=FileSystemLoader(str(TEMPLATES)), autoescape=True, undefined=ChainableUndefined
)
ORG = "/auth/settings/org/t1"

TENANT = {
    "id": "t1",
    "slug": "acme",
    "display_name": "Acme",
    "custom_domain": "auth.acme.example",
    "custom_domain_status": "pending",
    "is_active": True,
    "settings": {},
}
ROLE = {
    "id": "r1",
    "name": "support",
    "display_name": "Support",
    "description": "",
    "scopes": ["members:read"],
    "is_system": False,
    "is_default": False,
}
CLIENT = {
    "id": "c1",
    "client_id": "abc",
    "name": "App",
    "is_active": True,
    "is_confidential": True,
}
DETAIL = {
    "tenant": TENANT,
    "tenant_prefix": "",
    "members": [{"id": "m1", "role": "member", "role_display_name": "Member", "role_id": "r1"}],
    "tenant_roles": [ROLE],
    "role_member_counts": {},
    "identity_providers": [
        {
            "id": "i1",
            "name": "Corp",
            "provider_type": "oidc",
            "is_active": True,
            "federated_count": 0,
        }
    ],
    "trust_mode": "specific",
    "trusted_sources": [{"id": "s1", "trusted_tenant_name": "Other", "is_platform": False}],
    "available_tenants": [{"id": "t2", "display_name": "Other", "slug": "other"}],
    "webhooks": [
        {
            "id": "w1",
            "name": "Hook",
            "url": "https://h.example",
            "events": [],
            "is_active": True,
            "failure_count": 0,
            "recent_deliveries": [],
        }
    ],
    "webhook_events_by_group": {},
}
EDIT = {"tenant": TENANT, "tenant_prefix": "", "scope_groups": {}, "current_allowed": []}
TEMPLATE_LIST = {
    "tenant": TENANT,
    "tenant_prefix": "",
    "customizable_templates": ["auth/login.html"],
    "tenant_templates": [{"template_name": "auth/login.html", "is_active": True}],
}

# (template, context, marker of the control, scope that the route behind it requires)
CASES = [
    # members
    ("detail", DETAIL, f"{ORG}/members/add", "members:invite"),
    ("detail", DETAIL, f"{ORG}/members/m1/update-role", "members:update"),
    ("detail", DETAIL, f"{ORG}/members/m1/remove", "members:remove"),
    # roles
    ("detail", DETAIL, f'href="{ORG}/roles"', "roles:read"),
    ("detail", DETAIL, f"{ORG}/roles/create", "roles:write"),
    ("detail", DETAIL, f"{ORG}/roles/r1/edit", "roles:write"),
    ("detail", DETAIL, f"{ORG}/roles/r1/delete", "roles:delete"),
    (
        "roles",
        {
            "tenant": TENANT,
            "tenant_prefix": "",
            "roles": [ROLE],
            "role_stats": {},
            "available_scopes": {},
        },
        f"{ORG}/roles/create",
        "roles:write",
    ),
    (
        "roles",
        {
            "tenant": TENANT,
            "tenant_prefix": "",
            "roles": [ROLE],
            "role_stats": {},
            "available_scopes": {},
        },
        f"{ORG}/roles/r1/edit",
        "roles:write",
    ),
    (
        "roles",
        {
            "tenant": TENANT,
            "tenant_prefix": "",
            "roles": [ROLE],
            "role_stats": {},
            "available_scopes": {},
        },
        f"{ORG}/roles/r1/delete",
        "roles:delete",
    ),
    # identity providers
    ("detail", DETAIL, f"{ORG}/idp/create", "idp:write"),
    ("detail", DETAIL, f"{ORG}/idp/i1/edit", "idp:write"),
    ("detail", DETAIL, f"{ORG}/idp/i1/toggle", "idp:write"),
    ("detail", DETAIL, f"{ORG}/idp/i1/delete", "idp:delete"),
    # trust policy
    ("detail", DETAIL, f"{ORG}/trust/mode", "trust:write"),
    ("detail", DETAIL, f"{ORG}/trust/remove-source/s1", "trust:write"),
    ("detail", DETAIL, f"{ORG}/trust/add-source", "trust:write"),
    ("trust", DETAIL, f"{ORG}/trust/mode", "trust:write"),
    ("trust", DETAIL, f"{ORG}/trust/remove-source/s1", "trust:write"),
    ("trust", DETAIL, f"{ORG}/trust/add-source", "trust:write"),
    # the cards that lead to read pages
    ("detail", DETAIL, f'href="{ORG}/branding"', "branding:read"),
    ("detail", DETAIL, f'href="{ORG}/templates"', "templates:read"),
    ("detail", DETAIL, f'href="{ORG}/clients"', "clients:read"),
    # webhooks
    ("detail", DETAIL, "Webhooks (", "webhooks:read"),
    ("detail", DETAIL, f"{ORG}/webhooks/create", "webhooks:write"),
    ("detail", DETAIL, f"{ORG}/webhooks/w1/toggle", "webhooks:write"),
    ("detail", DETAIL, f"{ORG}/webhooks/w1/rotate-secret", "webhooks:write"),
    ("detail", DETAIL, f"{ORG}/webhooks/w1/delete", "webhooks:delete"),
    # the edit page: settings and custom domain are separate
    ("edit", EDIT, f'action="{ORG}/edit"', "settings:write"),
    ("edit", EDIT, f"{ORG}/email-sender", "settings:write"),
    ("edit", EDIT, f"{ORG}/allowed-scopes", "settings:write"),
    ("edit", EDIT, f'action="{ORG}/domain"', "domain:write"),
    ("edit", EDIT, f"{ORG}/verify-domain", "domain:write"),
    ("edit", EDIT, "Domain Status", "domain:read"),
    ("edit", EDIT, "Failed to poll domain status", "domain:read"),
    ("detail", DETAIL, "Failed to poll domain status", "domain:read"),
    # branding
    (
        "branding",
        {"tenant": TENANT, "tenant_prefix": "", "has_branding": True, "tenant_branding": {}},
        f"{ORG}/branding/reset",
        "branding:write",
    ),
    (
        "branding",
        {"tenant": TENANT, "tenant_prefix": "", "has_branding": True, "tenant_branding": {}},
        "Save Branding",
        "branding:write",
    ),
    # e-mail templates
    ("templates", TEMPLATE_LIST, f"{ORG}/templates/auth/login.html/edit", "templates:write"),
    ("templates", TEMPLATE_LIST, f"{ORG}/templates/auth/login.html/toggle", "templates:write"),
    ("templates", TEMPLATE_LIST, f"{ORG}/templates/auth/login.html/delete", "templates:write"),
    # OAuth2 clients
    (
        "clients/list",
        {"tenant": TENANT, "tenant_prefix": "", "clients": [CLIENT]},
        f"{ORG}/clients/create",
        "clients:write",
    ),
    (
        "clients/list",
        {"tenant": TENANT, "tenant_prefix": "", "clients": [CLIENT]},
        f"{ORG}/clients/c1/disable",
        "clients:write",
    ),
    (
        "clients/detail",
        {"tenant": TENANT, "tenant_prefix": "", "client": CLIENT},
        f"{ORG}/clients/c1/edit",
        "clients:write",
    ),
    (
        "clients/detail",
        {"tenant": TENANT, "tenant_prefix": "", "client": CLIENT},
        f"{ORG}/clients/c1/disable",
        "clients:write",
    ),
    (
        "clients/detail",
        {"tenant": TENANT, "tenant_prefix": "", "client": CLIENT},
        f"{ORG}/clients/c1/rotate-secret",
        "clients:rotate",
    ),
    (
        "clients/detail",
        {"tenant": TENANT, "tenant_prefix": "", "client": CLIENT},
        f"{ORG}/clients/c1/delete",
        "clients:delete",
    ),
    # registration and profile fields
    (
        "registration_fields",
        {"tenant": TENANT, "tenant_prefix": "", "fields": {}},
        "Save Configuration",
        "settings:write",
    ),
    (
        "profile_fields",
        {"tenant": TENANT, "tenant_prefix": "", "fields": {}},
        "Save Configuration",
        "settings:write",
    ),
]


# the webhooks section itself needs webhooks:read, the controls come on top of it
ALSO_NEEDED = {"webhooks:write": ["webhooks:read"], "webhooks:delete": ["webhooks:read"]}


def _can(*scopes):
    role = TenantCustomRole(name="custom", display_name="Custom", scopes=list(scopes))
    return OrgPermissions(TenantMember(custom_role=role))


def _render(template, context, *scopes):
    return ENV.get_template(f"auth/settings/org/{template}.html").render(
        can=_can(*scopes), **context
    )


def _every_scope_but(*excluded):
    """Each organisation scope on its own (no wildcard) except the excluded ones."""
    return [s for s in TENANT_SCOPES if s != "*" and not s.endswith(":*") and s not in excluded]


class TestOrgPermissions:
    def test_it_answers_like_the_guard(self):
        assert _can("idp:write")["idp:write"] is True
        assert _can("idp:write")["idp:delete"] is False
        assert _can("idp:*")["idp:delete"] is True
        assert _can("*")["domain:write"] is True
        assert _can()["members:read"] is False

    def test_settings_scopes_do_not_include_the_custom_domain(self):
        can = _can("settings:*")
        assert can["settings:write"] is True
        assert can["domain:read"] is False
        assert can["domain:write"] is False


@pytest.mark.parametrize(("template", "context", "marker", "scope"), CASES)
def test_a_control_is_shown_with_the_scope_of_its_route(template, context, marker, scope):
    assert marker in _render(template, context, scope, *ALSO_NEEDED.get(scope, []))


@pytest.mark.parametrize(("template", "context", "marker", "scope"), CASES)
def test_a_control_is_hidden_without_the_scope_of_its_route(template, context, marker, scope):
    assert marker not in _render(template, context, *_every_scope_but(scope))


@pytest.mark.parametrize(("template", "context", "marker", "scope"), CASES)
def test_the_owner_sees_every_control(template, context, marker, scope):
    assert marker in _render(template, context, "*")


def test_a_read_only_member_sees_the_pages_but_none_of_the_actions():
    html = _render("detail", DETAIL, "settings:read", "members:read")
    assert "Organization Details" in html
    assert "Corp" in html
    for action in (
        "/members/add",
        "/update-role",
        "/roles/create",
        "/idp/create",
        "/trust/mode",
        "/webhooks/create",
        "/edit",
        "/delete",
    ):
        assert action not in html, action


def test_the_edit_link_needs_settings_or_domain_access():
    link = f'href="{ORG}/edit"'
    assert link not in _render("detail", DETAIL, "settings:read")
    assert link in _render("detail", DETAIL, "settings:write")
    assert link in _render("detail", DETAIL, "domain:read")
    assert link in _render("detail", DETAIL, "domain:write")


def test_settings_write_alone_edits_the_name_but_not_the_domain():
    html = _render("edit", EDIT, "settings:read", "settings:write")
    assert f'action="{ORG}/edit"' in html
    assert "Custom Domain" not in html
    assert 'name="custom_domain"' not in html


def test_domain_write_alone_edits_the_domain_but_not_the_name():
    html = _render("edit", EDIT, "settings:read", "domain:write")
    assert f'action="{ORG}/domain"' in html
    assert 'name="custom_domain"' in html
    assert f'action="{ORG}/edit"' not in html
    assert f"{ORG}/email-sender" not in html


def test_domain_read_shows_the_domain_without_a_form():
    html = _render("edit", EDIT, "settings:read", "domain:read")
    assert "auth.acme.example" in html
    assert 'name="custom_domain"' not in html
    assert f'action="{ORG}/domain"' not in html
    assert f"{ORG}/verify-domain" not in html


@pytest.mark.parametrize("template", ["branding", "registration_fields", "profile_fields"])
def test_a_form_is_read_only_without_its_write_scope(template):
    context = {"tenant": TENANT, "tenant_prefix": "", "fields": {}, "tenant_branding": {}}
    write = "branding:write" if template == "branding" else "settings:write"
    assert "<fieldset disabled" in _render(template, context, write.replace("write", "read"))
    assert "<fieldset disabled" not in _render(template, context, write)


def test_the_account_page_offers_manage_to_members_who_can_open_the_organisation():
    template = ENV.get_template("auth/settings/tenants.html")
    membership = {
        "tenant_id": "t1",
        "tenant_name": "Acme",
        "tenant_slug": "acme",
        "tenant_active": True,
        "role": "support",
        "role_display_name": "Support",
        "linked_idps": [],
        "available_idps": [],
    }
    link = f'href="{ORG}"'
    assert link in template.render(memberships=[{**membership, "can_manage": True}])
    assert link not in template.render(memberships=[{**membership, "can_manage": False}])
