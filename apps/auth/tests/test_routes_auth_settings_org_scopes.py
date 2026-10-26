# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Scope enforcement of the /auth/settings/org/{tenant_id}/* handlers.

Every organisation settings route names the organisation scope it requires, the
same one as the matching route of the REST API (``members:invite``,
``branding:write``, ``idp:delete``...). The tests drive each handler with the real
``require_tenant_manager`` guard and a member whose role holds chosen scopes:
the guard must answer 403 to a member lacking the exact scope (``settings:read``
alone never lets a member mutate) and let through a member holding it, directly
or through a wildcard.
"""

import inspect
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.api.routes.auth import settings as settings_module
from auth.db.models.tenant import TenantCustomRole, TenantMember
from fastapi import HTTPException

MODULE = "auth.api.routes.auth.settings"

# endpoint name -> organisation scope the route requires
EXPECTED_SCOPES = {
    # organisation settings
    "org_detail_page": "settings:read",
    "org_edit_page": "settings:read",
    "org_edit_submit": "settings:write",
    "org_email_sender_submit": "settings:write",
    "org_allowed_scopes_submit": "settings:write",
    # the custom domain has its own scopes, settings:write does not reach it
    "org_domain_submit": "domain:write",
    "org_verify_domain": "domain:write",
    "org_domain_status": "domain:read",
    "org_registration_fields_page": "settings:read",
    "org_registration_fields_submit": "settings:write",
    "org_profile_fields_page": "settings:read",
    "org_profile_fields_submit": "settings:write",
    # members
    "org_add_member_submit": "members:invite",
    "org_update_member_role_submit": "members:update",
    "org_remove_member_submit": "members:remove",
    # roles
    "org_roles_page": "roles:read",
    "org_role_create_page": "roles:write",
    "org_role_create_submit": "roles:write",
    "org_role_edit_page": "roles:write",
    "org_role_edit_submit": "roles:write",
    "org_role_delete_submit": "roles:delete",
    # identity providers
    "org_idp_create_page": "idp:write",
    "org_idp_create_submit": "idp:write",
    "org_idp_edit_page": "idp:write",
    "org_idp_edit_submit": "idp:write",
    "org_idp_toggle_submit": "idp:write",
    "org_idp_delete_submit": "idp:delete",
    # branding
    "org_branding_page": "branding:read",
    "org_branding_submit": "branding:write",
    "org_branding_reset": "branding:write",
    # OAuth2 clients
    "org_clients_page": "clients:read",
    "org_client_create_page": "clients:write",
    "org_client_create_submit": "clients:write",
    "org_client_detail_page": "clients:read",
    "org_client_edit_page": "clients:write",
    "org_client_edit_submit": "clients:write",
    "org_client_disable": "clients:write",
    "org_client_enable": "clients:write",
    "org_client_rotate_secret": "clients:rotate",
    "org_client_delete": "clients:delete",
    # templates
    "org_templates_page": "templates:read",
    "org_template_edit_page": "templates:write",
    "org_template_edit_submit": "templates:write",
    "org_template_delete": "templates:write",
    "org_template_toggle": "templates:write",
    # trust policy
    "org_trust_page": "trust:read",
    "org_trust_mode_submit": "trust:write",
    "org_trust_add_source_submit": "trust:write",
    "org_trust_remove_source_submit": "trust:write",
    # webhooks
    "org_webhook_create_submit": "webhooks:write",
    "org_webhook_update_submit": "webhooks:write",
    "org_webhook_toggle": "webhooks:write",
    "org_webhook_rotate_secret": "webhooks:write",
    "org_webhook_test": "webhooks:write",
    "org_webhook_delete": "webhooks:delete",
    "org_webhook_replay_delivery": "webhooks:write",
}


class _Authorised(Exception):
    """Raised by the guard spy once the real guard let the member through."""


def _org_handlers():
    """The endpoint of every route of the organisation settings, by name."""
    return {
        route.endpoint.__name__: route.endpoint
        for route in settings_module.router.routes
        if "/org/{tenant_id}" in route.path
    }


def _member(user, *scopes):
    role = TenantCustomRole(name="custom", display_name="Custom", scopes=list(scopes))
    return TenantMember(user_id=user.id, custom_role=role)


async def _drive(name, *scopes):
    """Call a handler through the real guard for a member holding ``scopes``.

    Returns the scope the handler asked for when the guard let the member through
    (the spy then stops the handler); an ``HTTPException`` from the guard propagates.
    """
    handler = _org_handlers()[name]
    real_guard = settings_module.require_tenant_manager
    user = MagicMock()
    user.id = uuid.uuid4()
    tenant = MagicMock()
    tenant.members = [_member(user, *scopes)]
    session_service = AsyncMock()
    session_service.get_user_by_session_token = AsyncMock(return_value=user)
    request = MagicMock()
    request.cookies = {"session": "tok"}

    async def guard(request, tenant_id, db, session_service, required_scope):
        await real_guard(request, tenant_id, db, session_service, required_scope=required_scope)
        raise _Authorised(required_scope)

    known = {
        "request": request,
        "tenant_id": str(uuid.uuid4()),
        "db": AsyncMock(),
        "session_service": session_service,
        "templates": MagicMock(),
        "trust_service": AsyncMock(),
    }
    kwargs = {
        param: known.get(param, str(uuid.uuid4()))
        for param in inspect.signature(handler).parameters
    }
    with (
        patch(f"{MODULE}.require_tenant_manager", guard),
        patch(f"{MODULE}.get_session_cookie_name", return_value="session"),
        patch(
            f"{MODULE}.tenant_service.get_by_id_with_all_relations",
            AsyncMock(return_value=tenant),
        ),
    ):
        try:
            await handler(**kwargs)
        except _Authorised as authorised:
            return str(authorised)
    raise AssertionError(f"{name} did not call require_tenant_manager first")


def test_every_organisation_route_is_covered_by_the_table():
    assert set(_org_handlers()) == set(EXPECTED_SCOPES)


def test_the_guard_has_no_default_scope_and_no_owner_alias():
    parameter = inspect.signature(settings_module.require_tenant_manager).parameters[
        "required_scope"
    ]
    assert parameter.default is inspect.Parameter.empty
    assert not hasattr(settings_module, "require_tenant_owner")


@pytest.mark.parametrize(("name", "scope"), sorted(EXPECTED_SCOPES.items()))
class TestEachRouteRequiresItsScope:
    async def test_a_member_holding_exactly_the_scope_is_let_through(self, name, scope):
        assert await _drive(name, scope) == scope

    async def test_a_member_holding_the_resource_wildcard_is_let_through(self, name, scope):
        resource = scope.split(":")[0]
        assert await _drive(name, f"{resource}:*") == scope

    async def test_the_owner_wildcard_is_let_through(self, name, scope):
        assert await _drive(name, "*") == scope

    async def test_a_member_without_any_scope_gets_403(self, name, scope):
        with pytest.raises(HTTPException) as exc:
            await _drive(name)
        assert exc.value.status_code == 403
        assert scope in exc.value.detail

    async def test_settings_read_alone_cannot_go_beyond_settings_read(self, name, scope):
        if scope == "settings:read":
            assert await _drive(name, "settings:read") == scope
            return
        with pytest.raises(HTTPException) as exc:
            await _drive(name, "settings:read")
        assert exc.value.status_code == 403
        assert scope in exc.value.detail

    async def test_another_resource_scope_is_refused(self, name, scope):
        resource, action = scope.split(":")
        other = "branding" if resource != "branding" else "trust"
        with pytest.raises(HTTPException) as exc:
            await _drive(name, f"{other}:{action}", f"{other}:*")
        assert exc.value.status_code == 403


@pytest.mark.parametrize(
    ("name", "scope"),
    sorted((n, s) for n, s in EXPECTED_SCOPES.items() if not s.endswith(":read")),
)
async def test_a_read_only_member_cannot_mutate(name, scope):
    resource = scope.split(":")[0]
    with pytest.raises(HTTPException) as exc:
        await _drive(name, f"{resource}:read")
    assert exc.value.status_code == 403
    assert scope in exc.value.detail


DOMAIN_ROUTES = ("org_domain_submit", "org_verify_domain", "org_domain_status")


@pytest.mark.parametrize("name", DOMAIN_ROUTES)
async def test_settings_scopes_never_reach_the_custom_domain(name):
    """Holding the whole settings resource is not enough for the custom domain."""
    with pytest.raises(HTTPException) as exc:
        await _drive(name, "settings:*", "settings:read", "settings:write")
    assert exc.value.status_code == 403
    assert "domain:" in exc.value.detail


@pytest.mark.parametrize("name", ["org_domain_submit", "org_verify_domain"])
async def test_domain_read_alone_cannot_change_the_domain(name):
    with pytest.raises(HTTPException) as exc:
        await _drive(name, "domain:read")
    assert exc.value.status_code == 403
    assert "domain:write" in exc.value.detail


async def test_domain_write_alone_does_not_open_the_settings_forms():
    """The members who manage the domain do not get the organisation settings with it."""
    for name in ("org_edit_submit", "org_email_sender_submit", "org_allowed_scopes_submit"):
        with pytest.raises(HTTPException) as exc:
            await _drive(name, "domain:*")
        assert exc.value.status_code == 403
        assert "settings:write" in exc.value.detail
