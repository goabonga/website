# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the custom domain endpoints of /api/v1/organisations and /api/v1/me/organisations."""

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.api.deps import get_db
from auth.api.routes.api.deps import get_current_user_bearer
from auth.db.models.tenant import CustomDomainStatus
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

TASKS = "auth.tasks.custom_domain"
SERVICE = "auth.services.custom_domain"
HELPERS = "auth.api.routes.api.organisations.domain"

# (URL prefix, module whose require_org_membership the route calls)
SURFACES = [
    ("/api/v1/organisations", "auth.api.routes.api.organisations.domain"),
    ("/api/v1/me/organisations", "auth.api.routes.api.me.organisations.domain"),
]


@pytest.fixture(params=SURFACES, ids=["organisations", "me-organisations"])
def surface(request):
    return request.param


def _tenant(domain=None, status=None):
    tenant = MagicMock()
    tenant.id = uuid.uuid4()
    tenant.slug = "acme"
    tenant.display_name = "Acme"
    tenant.is_active = True
    tenant.custom_domain = domain
    tenant.custom_domain_status = status
    tenant.custom_domain_verified_at = None
    tenant.custom_domain_ssl_at = None
    tenant.custom_domain_error = None
    tenant.custom_domain_checked_at = None
    return tenant


@pytest.fixture
def _make_app():
    """Factory yielding (app, user, mock_db) with the dependencies overridden."""
    from auth.main import app as fastapi_app

    def factory():
        user = MagicMock()
        user.id = uuid.uuid4()
        user.is_active = True
        db = AsyncMock()

        async def override_auth():
            return user

        async def override_db():
            yield db

        fastapi_app.dependency_overrides[get_current_user_bearer] = override_auth
        fastapi_app.dependency_overrides[get_db] = override_db
        return fastapi_app, user, db

    yield factory
    fastapi_app.dependency_overrides.clear()


@contextmanager
def _member(module, user, tenant, *, scope_error=None):
    """The caller is a member of ``tenant`` (or is refused with ``scope_error``)."""
    membership = AsyncMock(side_effect=scope_error, return_value=(user, tenant, MagicMock()))
    with patch(f"{module}.require_org_membership", membership) as patched:
        yield patched


@contextmanager
def _background(*, holder=None):
    """The webhook dispatch, the Celery tasks and the lookup of the domain are replaced."""
    with (
        patch(f"{SERVICE}.safe_dispatch", AsyncMock()) as dispatch,
        patch(f"{TASKS}.verify_custom_domain_dns") as verify,
        patch(f"{TASKS}.remove_custom_domain_config") as remove,
        patch(f"{HELPERS}.tenant_service") as tenants,
    ):
        tenants.get_by_custom_domain = AsyncMock(return_value=holder)
        yield MagicMock(dispatch=dispatch, verify=verify, remove=remove, tenants=tenants)


async def _call(app, method, url, **kwargs):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.request(method, url, **kwargs)


def _forbidden(scope):
    return HTTPException(status_code=403, detail=f"Missing required permission: {scope}")


# ===========================================================================
# GET .../domain/
# ===========================================================================


async def test_get_reports_the_state(_make_app, surface):
    prefix, module = surface
    app, user, _db = _make_app()
    moment = datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC)
    tenant = _tenant("auth.acme.example", CustomDomainStatus.ACTIVE)
    tenant.custom_domain_verified_at = tenant.custom_domain_ssl_at = moment
    tenant.custom_domain_checked_at = moment

    with _member(module, user, tenant) as membership:
        response = await _call(app, "GET", f"{prefix}/{tenant.id}/domain/")

    assert response.status_code == 200
    body = response.json()
    assert body["custom_domain"] == "auth.acme.example"
    assert body["status"] == "active"
    assert body["error"] is None
    assert datetime.fromisoformat(body["verified_at"]) == moment
    assert membership.await_args.kwargs["required_scope"] == "domain:read"


async def test_get_without_a_domain(_make_app, surface):
    prefix, module = surface
    app, user, _db = _make_app()
    tenant = _tenant()

    with _member(module, user, tenant):
        response = await _call(app, "GET", f"{prefix}/{tenant.id}/domain/")

    assert response.json() == {
        "custom_domain": None,
        "status": None,
        "error": None,
        "verified_at": None,
        "ssl_at": None,
        "checked_at": None,
    }


async def test_get_needs_domain_read(_make_app, surface):
    prefix, module = surface
    app, user, _db = _make_app()
    tenant = _tenant()

    with _member(module, user, tenant, scope_error=_forbidden("domain:read")):
        response = await _call(app, "GET", f"{prefix}/{tenant.id}/domain/")

    assert response.status_code == 403
    assert response.json()["detail"] == "Missing required permission: domain:read"


# ===========================================================================
# PUT .../domain/
# ===========================================================================


async def test_put_sets_the_domain_like_the_settings_page(_make_app, surface):
    prefix, module = surface
    app, user, db = _make_app()
    tenant = _tenant()

    with _member(module, user, tenant) as membership, _background() as bg:
        response = await _call(
            app,
            "PUT",
            f"{prefix}/{tenant.id}/domain/",
            json={"custom_domain": "  Auth.Acme.Example "},
        )

    assert response.status_code == 200
    assert response.json()["custom_domain"] == "auth.acme.example"
    assert response.json()["status"] == "pending"
    assert membership.await_args.kwargs["required_scope"] == "domain:write"
    assert tenant.custom_domain_status is CustomDomainStatus.PENDING
    # the tenant.updated event of the page, then the commit, then the DNS verification
    event = bg.dispatch.await_args.kwargs
    assert event["event"].value == "tenant.updated"
    assert event["data"]["custom_domain"] == "auth.acme.example"
    assert event["data"]["actor_id"] == str(user.id)
    db.commit.assert_awaited_once()
    bg.verify.delay.assert_called_once_with(str(tenant.id), "auth.acme.example", "acme")
    bg.remove.delay.assert_not_called()


async def test_put_the_current_domain_changes_nothing(_make_app, surface):
    prefix, module = surface
    app, user, db = _make_app()
    tenant = _tenant("auth.acme.example", CustomDomainStatus.ACTIVE)

    with _member(module, user, tenant), _background(holder=tenant) as bg:
        response = await _call(
            app,
            "PUT",
            f"{prefix}/{tenant.id}/domain/",
            json={"custom_domain": "auth.acme.example"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "active"
    bg.dispatch.assert_not_awaited()
    db.commit.assert_not_awaited()
    bg.verify.delay.assert_not_called()


async def test_put_refuses_a_domain_of_another_organisation(_make_app, surface):
    prefix, module = surface
    app, user, db = _make_app()
    tenant = _tenant()

    with _member(module, user, tenant), _background(holder=_tenant("taken.example")) as bg:
        response = await _call(
            app, "PUT", f"{prefix}/{tenant.id}/domain/", json={"custom_domain": "taken.example"}
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "This domain is already used by another organisation"
    assert tenant.custom_domain is None
    bg.verify.delay.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.parametrize("domain", ["localhost", "-bad.example", "a b.example", "x/y.example"])
async def test_put_refuses_a_malformed_host_name(_make_app, surface, domain):
    prefix, module = surface
    app, user, db = _make_app()
    tenant = _tenant()

    with _member(module, user, tenant), _background() as bg:
        response = await _call(
            app, "PUT", f"{prefix}/{tenant.id}/domain/", json={"custom_domain": domain}
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid domain name"
    bg.verify.delay.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.parametrize("body", [{}, {"custom_domain": ""}, {"custom_domain": None}])
async def test_put_needs_a_domain(_make_app, surface, body):
    prefix, module = surface
    app, user, _db = _make_app()
    tenant = _tenant()

    with _member(module, user, tenant), _background():
        response = await _call(app, "PUT", f"{prefix}/{tenant.id}/domain/", json=body)

    assert response.status_code == 422


async def test_put_needs_domain_write(_make_app, surface):
    prefix, module = surface
    app, user, db = _make_app()
    tenant = _tenant()

    with _member(module, user, tenant, scope_error=_forbidden("domain:write")), _background():
        response = await _call(
            app, "PUT", f"{prefix}/{tenant.id}/domain/", json={"custom_domain": "acme.example"}
        )

    assert response.status_code == 403
    assert tenant.custom_domain is None
    db.commit.assert_not_awaited()


# ===========================================================================
# DELETE .../domain/
# ===========================================================================


async def test_delete_removes_the_domain(_make_app, surface):
    prefix, module = surface
    app, user, db = _make_app()
    tenant = _tenant("auth.acme.example", CustomDomainStatus.ACTIVE)

    with _member(module, user, tenant) as membership, _background() as bg:
        response = await _call(app, "DELETE", f"{prefix}/{tenant.id}/domain/")

    assert response.status_code == 204
    assert membership.await_args.kwargs["required_scope"] == "domain:write"
    assert tenant.custom_domain is None
    assert tenant.custom_domain_status is None
    assert bg.dispatch.await_args.kwargs["data"]["custom_domain"] is None
    db.commit.assert_awaited_once()
    bg.remove.delay.assert_called_once_with("auth.acme.example", "acme")
    bg.verify.delay.assert_not_called()


async def test_delete_without_a_domain_changes_nothing(_make_app, surface):
    prefix, module = surface
    app, user, db = _make_app()
    tenant = _tenant()

    with _member(module, user, tenant), _background() as bg:
        response = await _call(app, "DELETE", f"{prefix}/{tenant.id}/domain/")

    assert response.status_code == 204
    bg.dispatch.assert_not_awaited()
    db.commit.assert_not_awaited()
    bg.remove.delay.assert_not_called()


async def test_delete_needs_domain_write(_make_app, surface):
    prefix, module = surface
    app, user, db = _make_app()
    tenant = _tenant("auth.acme.example")

    with _member(module, user, tenant, scope_error=_forbidden("domain:write")), _background():
        response = await _call(app, "DELETE", f"{prefix}/{tenant.id}/domain/")

    assert response.status_code == 403
    assert tenant.custom_domain == "auth.acme.example"
    db.commit.assert_not_awaited()


# ===========================================================================
# POST .../domain/verify
# ===========================================================================


@pytest.mark.parametrize("state", [None, CustomDomainStatus.PENDING, CustomDomainStatus.FAILED])
async def test_verify_queues_the_dns_verification(_make_app, surface, state):
    prefix, module = surface
    app, user, db = _make_app()
    tenant = _tenant("auth.acme.example", state)
    tenant.custom_domain_error = "no CNAME"

    with _member(module, user, tenant) as membership, _background() as bg:
        response = await _call(app, "POST", f"{prefix}/{tenant.id}/domain/verify")

    assert response.status_code == 202
    assert response.json()["status"] == "pending"
    assert response.json()["error"] is None
    assert membership.await_args.kwargs["required_scope"] == "domain:write"
    db.commit.assert_awaited_once()
    bg.verify.delay.assert_called_once_with(str(tenant.id), "auth.acme.example", "acme")


async def test_verify_an_active_domain_is_returned_as_it_is(_make_app, surface):
    prefix, module = surface
    app, user, db = _make_app()
    tenant = _tenant("auth.acme.example", CustomDomainStatus.ACTIVE)

    with _member(module, user, tenant), _background() as bg:
        response = await _call(app, "POST", f"{prefix}/{tenant.id}/domain/verify")

    assert response.status_code == 200
    assert response.json()["status"] == "active"
    bg.verify.delay.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.parametrize(
    "state", [CustomDomainStatus.DNS_VERIFYING, CustomDomainStatus.SSL_PROVISIONING]
)
async def test_verify_refuses_while_a_verification_runs(_make_app, surface, state):
    prefix, module = surface
    app, user, _db = _make_app()
    tenant = _tenant("auth.acme.example", state)

    with _member(module, user, tenant), _background() as bg:
        response = await _call(app, "POST", f"{prefix}/{tenant.id}/domain/verify")

    assert response.status_code == 409
    assert response.json()["detail"] == "Domain verification already in progress"
    bg.verify.delay.assert_not_called()


async def test_verify_without_a_domain(_make_app, surface):
    prefix, module = surface
    app, user, _db = _make_app()
    tenant = _tenant()

    with _member(module, user, tenant), _background() as bg:
        response = await _call(app, "POST", f"{prefix}/{tenant.id}/domain/verify")

    assert response.status_code == 400
    assert response.json()["detail"] == "No custom domain configured"
    bg.verify.delay.assert_not_called()


async def test_verify_needs_domain_write(_make_app, surface):
    prefix, module = surface
    app, user, db = _make_app()
    tenant = _tenant("auth.acme.example")

    with _member(module, user, tenant, scope_error=_forbidden("domain:write")), _background() as bg:
        response = await _call(app, "POST", f"{prefix}/{tenant.id}/domain/verify")

    assert response.status_code == 403
    bg.verify.delay.assert_not_called()
    db.commit.assert_not_awaited()


# ===========================================================================
# Membership and scopes, with the real guard
# ===========================================================================


def _membership_guard_app(_make_app, *, scopes):
    """The real require_org_membership, with a member that holds ``scopes``."""
    app, user, db = _make_app()
    tenant = _tenant("auth.acme.example", CustomDomainStatus.PENDING)
    member = MagicMock()
    member.has_scope = lambda required: required in scopes
    tenants = MagicMock()
    tenants.get_active_by_id = AsyncMock(return_value=tenant)
    tenants.get_member = AsyncMock(return_value=member)
    return app, tenant, patch("auth.api.routes.api.deps._tenant_service", tenants)


@pytest.mark.parametrize(
    ("method", "path", "scope"),
    [
        ("GET", "/domain/", "domain:read"),
        ("PUT", "/domain/", "domain:write"),
        ("DELETE", "/domain/", "domain:write"),
        ("POST", "/domain/verify", "domain:write"),
    ],
)
async def test_each_operation_checks_its_own_scope(_make_app, surface, method, path, scope):
    prefix, _module = surface
    other = "domain:read" if scope == "domain:write" else "domain:write"
    kwargs = {"json": {"custom_domain": "acme.example"}} if method == "PUT" else {}

    app, tenant, guard = _membership_guard_app(_make_app, scopes={other, "settings:write"})
    with guard, _background():
        refused = await _call(app, method, f"{prefix}/{tenant.id}{path}", **kwargs)
    assert refused.status_code == 403
    assert refused.json()["detail"] == f"Missing required permission: {scope}"

    app, tenant, guard = _membership_guard_app(_make_app, scopes={scope})
    with guard, _background():
        allowed = await _call(app, method, f"{prefix}/{tenant.id}{path}", **kwargs)
    assert allowed.status_code in (200, 202, 204)


async def test_a_stranger_is_refused(_make_app, surface):
    prefix, _module = surface
    app, user, _db = _make_app()
    tenants = MagicMock()
    tenants.get_active_by_id = AsyncMock(return_value=_tenant())
    tenants.get_member = AsyncMock(return_value=None)

    with patch("auth.api.routes.api.deps._tenant_service", tenants):
        response = await _call(app, "GET", f"{prefix}/{uuid.uuid4()}/domain/")

    assert response.status_code == 403
    assert response.json()["detail"] == "You are not a member of this organisation"
