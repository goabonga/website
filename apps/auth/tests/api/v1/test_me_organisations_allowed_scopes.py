# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for /api/v1/me/organisations/{org_id}/allowed-scopes endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.api.deps import get_db
from auth.api.routes.api.deps import get_current_user_bearer
from httpx import ASGITransport, AsyncClient


def _make_mock_user() -> MagicMock:
    """Build a mock authenticated user."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True
    return user


def _make_mock_tenant(
    tenant_id: uuid.UUID | None = None,
    settings: dict | None = None,
) -> MagicMock:
    """Build a mock Tenant."""
    tenant = MagicMock()
    tenant.id = tenant_id or uuid.uuid4()
    tenant.slug = "test-org"
    tenant.display_name = "Test Org"
    tenant.is_active = True
    tenant.settings = settings if settings is not None else {}
    tenant.created_at = datetime.now(UTC)
    tenant.updated_at = datetime.now(UTC)
    return tenant


def _make_mock_membership(has_scope: bool = True) -> MagicMock:
    """Build a mock TenantMember."""
    member = MagicMock()
    member.has_scope = MagicMock(return_value=has_scope)
    return member


@pytest.fixture
def _make_app():
    """Factory that yields (app, user, mock_db) with deps overridden."""
    from auth.main import app as fastapi_app

    created: list = []

    def factory(user: MagicMock | None = None):
        if user is None:
            user = _make_mock_user()

        mock_db = AsyncMock()

        async def override_auth():
            return user

        async def override_db():
            yield mock_db

        fastapi_app.dependency_overrides[get_current_user_bearer] = override_auth
        fastapi_app.dependency_overrides[get_db] = override_db
        created.append(fastapi_app)
        return fastapi_app, user, mock_db

    yield factory

    for a in created:
        a.dependency_overrides.clear()


# ===========================================================================
# GET /api/v1/me/organisations/{org_id}/allowed-scopes/
# ===========================================================================


@pytest.mark.asyncio
async def test_get_allowed_scopes_success(_make_app):
    """GET allowed-scopes returns the configured scopes."""
    app, user, mock_db = _make_app()
    tenant = _make_mock_tenant(settings={"allowed_scopes": ["members:read", "roles:read"]})
    membership = _make_mock_membership(has_scope=True)

    with patch(
        "auth.api.routes.api.me.organisations.allowed_scopes.require_org_membership",
        new_callable=AsyncMock,
        return_value=(user, tenant, membership),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/me/organisations/{tenant.id}/allowed-scopes/")

    assert response.status_code == 200
    data = response.json()
    assert data["allowed_scopes"] == ["members:read", "roles:read"]


@pytest.mark.asyncio
async def test_get_allowed_scopes_none_means_all(_make_app):
    """GET allowed-scopes returns null when all scopes are allowed."""
    app, user, mock_db = _make_app()
    tenant = _make_mock_tenant(settings={})
    membership = _make_mock_membership(has_scope=True)

    with patch(
        "auth.api.routes.api.me.organisations.allowed_scopes.require_org_membership",
        new_callable=AsyncMock,
        return_value=(user, tenant, membership),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/me/organisations/{tenant.id}/allowed-scopes/")

    assert response.status_code == 200
    data = response.json()
    assert data["allowed_scopes"] is None


@pytest.mark.asyncio
async def test_get_allowed_scopes_forbidden(_make_app):
    """GET allowed-scopes without settings:read scope returns 403."""
    from fastapi import HTTPException

    app, user, mock_db = _make_app()
    tenant = _make_mock_tenant()

    with patch(
        "auth.api.routes.api.me.organisations.allowed_scopes.require_org_membership",
        new_callable=AsyncMock,
        side_effect=HTTPException(
            status_code=403,
            detail="Missing required permission: settings:read",
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/me/organisations/{tenant.id}/allowed-scopes/")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_allowed_scopes_not_found(_make_app):
    """GET allowed-scopes for unknown org returns 404."""
    from fastapi import HTTPException

    app, user, mock_db = _make_app()

    with patch(
        "auth.api.routes.api.me.organisations.allowed_scopes.require_org_membership",
        new_callable=AsyncMock,
        side_effect=HTTPException(
            status_code=404,
            detail="Organisation not found",
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/me/organisations/{uuid.uuid4()}/allowed-scopes/")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_allowed_scopes_unauthenticated():
    """GET allowed-scopes without token returns 401."""
    from auth.main import app as fastapi_app

    fastapi_app.dependency_overrides.pop(get_current_user_bearer, None)

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    fastapi_app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/me/organisations/{uuid.uuid4()}/allowed-scopes/")

    assert response.status_code == 401
    fastapi_app.dependency_overrides.clear()


# ===========================================================================
# PATCH /api/v1/me/organisations/{org_id}/allowed-scopes/
# ===========================================================================


@pytest.mark.asyncio
async def test_update_allowed_scopes_success(_make_app):
    """PATCH allowed-scopes updates the scopes list."""
    app, user, mock_db = _make_app()
    tenant = _make_mock_tenant(settings={})
    membership = _make_mock_membership(has_scope=True)

    with (
        patch(
            "auth.api.routes.api.me.organisations.allowed_scopes.require_org_membership",
            new_callable=AsyncMock,
            return_value=(user, tenant, membership),
        ),
        patch(
            "auth.api.routes.api.me.organisations.allowed_scopes.flag_modified",
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.patch(
                f"/api/v1/me/organisations/{tenant.id}/allowed-scopes/",
                json={"allowed_scopes": ["members:read", "roles:read"]},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["allowed_scopes"] == ["members:read", "roles:read"]


@pytest.mark.asyncio
async def test_update_allowed_scopes_set_none(_make_app):
    """PATCH allowed-scopes with null stores None (all allowed)."""
    app, user, mock_db = _make_app()
    tenant = _make_mock_tenant(settings={"allowed_scopes": ["members:read"]})
    membership = _make_mock_membership(has_scope=True)

    with (
        patch(
            "auth.api.routes.api.me.organisations.allowed_scopes.require_org_membership",
            new_callable=AsyncMock,
            return_value=(user, tenant, membership),
        ),
        patch(
            "auth.api.routes.api.me.organisations.allowed_scopes.flag_modified",
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.patch(
                f"/api/v1/me/organisations/{tenant.id}/allowed-scopes/",
                json={"allowed_scopes": None},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["allowed_scopes"] is None


@pytest.mark.asyncio
async def test_update_allowed_scopes_invalid_scope(_make_app):
    """PATCH allowed-scopes with invalid scope returns 400."""
    app, user, mock_db = _make_app()
    tenant = _make_mock_tenant(settings={})
    membership = _make_mock_membership(has_scope=True)

    with (
        patch(
            "auth.api.routes.api.me.organisations.allowed_scopes.require_org_membership",
            new_callable=AsyncMock,
            return_value=(user, tenant, membership),
        ),
        patch(
            "auth.api.routes.api.me.organisations.allowed_scopes.TENANT_SCOPES",
            {"members:read": "Read members", "roles:read": "Read roles"},
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.patch(
                f"/api/v1/me/organisations/{tenant.id}/allowed-scopes/",
                json={"allowed_scopes": ["members:read", "totally:invalid"]},
            )

    assert response.status_code == 400
    assert "totally:invalid" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_allowed_scopes_forbidden(_make_app):
    """PATCH allowed-scopes without settings:write scope returns 403."""
    from fastapi import HTTPException

    app, user, mock_db = _make_app()
    tenant = _make_mock_tenant()

    with patch(
        "auth.api.routes.api.me.organisations.allowed_scopes.require_org_membership",
        new_callable=AsyncMock,
        side_effect=HTTPException(
            status_code=403,
            detail="Missing required permission: settings:write",
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.patch(
                f"/api/v1/me/organisations/{tenant.id}/allowed-scopes/",
                json={"allowed_scopes": ["members:read"]},
            )

    assert response.status_code == 403
