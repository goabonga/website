# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for /api/v1/me/organisations/{org_id}/settings endpoints."""

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
# GET /api/v1/me/organisations/{org_id}/settings/
# ===========================================================================


@pytest.mark.asyncio
async def test_get_settings_success(_make_app):
    """GET settings returns the JSONB settings dict."""
    app, user, mock_db = _make_app()
    tenant = _make_mock_tenant(
        settings={
            "registration_fields": ["email", "name"],
            "allowed_scopes": ["openid", "profile"],
        }
    )
    membership = _make_mock_membership(has_scope=True)

    with patch(
        "auth.api.routes.api.me.organisations.settings.require_org_membership",
        new_callable=AsyncMock,
        return_value=(user, tenant, membership),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/me/organisations/{tenant.id}/settings/")

    assert response.status_code == 200
    data = response.json()
    assert data["settings"]["registration_fields"] == ["email", "name"]
    assert data["settings"]["allowed_scopes"] == ["openid", "profile"]


@pytest.mark.asyncio
async def test_get_settings_empty(_make_app):
    """GET settings with no settings returns empty dict."""
    app, user, mock_db = _make_app()
    tenant = _make_mock_tenant(settings=None)
    membership = _make_mock_membership(has_scope=True)

    with patch(
        "auth.api.routes.api.me.organisations.settings.require_org_membership",
        new_callable=AsyncMock,
        return_value=(user, tenant, membership),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/me/organisations/{tenant.id}/settings/")

    assert response.status_code == 200
    data = response.json()
    assert data["settings"] == {}


@pytest.mark.asyncio
async def test_get_settings_forbidden(_make_app):
    """GET settings without settings:read scope returns 403."""
    from fastapi import HTTPException

    app, user, mock_db = _make_app()
    tenant = _make_mock_tenant()

    with patch(
        "auth.api.routes.api.me.organisations.settings.require_org_membership",
        new_callable=AsyncMock,
        side_effect=HTTPException(
            status_code=403,
            detail="Missing required permission: settings:read",
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/me/organisations/{tenant.id}/settings/")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_settings_not_found(_make_app):
    """GET settings for unknown org returns 404."""
    from fastapi import HTTPException

    app, user, mock_db = _make_app()

    with patch(
        "auth.api.routes.api.me.organisations.settings.require_org_membership",
        new_callable=AsyncMock,
        side_effect=HTTPException(
            status_code=404,
            detail="Organisation not found",
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/me/organisations/{uuid.uuid4()}/settings/")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_settings_unauthenticated():
    """GET settings without token returns 401."""
    from auth.main import app as fastapi_app

    fastapi_app.dependency_overrides.pop(get_current_user_bearer, None)

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    fastapi_app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/me/organisations/{uuid.uuid4()}/settings/")

    assert response.status_code == 401
    fastapi_app.dependency_overrides.clear()


# ===========================================================================
# PATCH /api/v1/me/organisations/{org_id}/settings/
# ===========================================================================


@pytest.mark.asyncio
async def test_update_settings_merge(_make_app):
    """PATCH settings merges new keys into existing settings."""
    app, user, mock_db = _make_app()
    tenant = _make_mock_tenant(
        settings={
            "registration_fields": ["email"],
            "existing_key": "keep_me",
        }
    )
    membership = _make_mock_membership(has_scope=True)

    with patch(
        "auth.api.routes.api.me.organisations.settings.require_org_membership",
        new_callable=AsyncMock,
        return_value=(user, tenant, membership),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.patch(
                f"/api/v1/me/organisations/{tenant.id}/settings/",
                json={
                    "settings": {
                        "registration_fields": ["email", "name"],
                        "new_key": "new_value",
                    }
                },
            )

    assert response.status_code == 200
    data = response.json()
    # Merged: existing_key preserved, registration_fields updated, new_key added
    assert data["settings"]["existing_key"] == "keep_me"
    assert data["settings"]["registration_fields"] == ["email", "name"]
    assert data["settings"]["new_key"] == "new_value"


@pytest.mark.asyncio
async def test_update_settings_from_empty(_make_app):
    """PATCH settings when tenant.settings is None creates dict."""
    app, user, mock_db = _make_app()
    tenant = _make_mock_tenant(settings=None)
    membership = _make_mock_membership(has_scope=True)

    with patch(
        "auth.api.routes.api.me.organisations.settings.require_org_membership",
        new_callable=AsyncMock,
        return_value=(user, tenant, membership),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.patch(
                f"/api/v1/me/organisations/{tenant.id}/settings/",
                json={"settings": {"new_key": "value"}},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["settings"]["new_key"] == "value"


@pytest.mark.asyncio
async def test_update_settings_forbidden(_make_app):
    """PATCH settings without settings:write scope returns 403."""
    from fastapi import HTTPException

    app, user, mock_db = _make_app()
    tenant = _make_mock_tenant()

    with patch(
        "auth.api.routes.api.me.organisations.settings.require_org_membership",
        new_callable=AsyncMock,
        side_effect=HTTPException(
            status_code=403,
            detail="Missing required permission: settings:write",
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.patch(
                f"/api/v1/me/organisations/{tenant.id}/settings/",
                json={"settings": {"key": "val"}},
            )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_settings_validation_error(_make_app):
    """PATCH settings with missing body returns 422."""
    app, user, mock_db = _make_app()
    tenant = _make_mock_tenant()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.patch(
            f"/api/v1/me/organisations/{tenant.id}/settings/",
            json={},
        )

    assert response.status_code == 422
