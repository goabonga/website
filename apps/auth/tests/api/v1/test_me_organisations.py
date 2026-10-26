# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for /api/v1/me/organisations endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_list_organisations(client, mock_user, app):
    """GET /api/v1/me/organisations/ returns user's organisations."""
    from auth.api.deps import get_db

    tenant_id = uuid.uuid4()
    now = datetime.now(UTC)

    # Build mock membership with tenant and role
    mock_tenant = MagicMock()
    mock_tenant.id = tenant_id
    mock_tenant.slug = "my-org"
    mock_tenant.display_name = "My Organisation"
    mock_tenant.is_active = True

    mock_role = MagicMock()
    mock_role.name = "owner"
    mock_role.display_name = "Owner"

    mock_member = MagicMock()
    mock_member.tenant = mock_tenant
    mock_member.custom_role = mock_role
    mock_member.role_name = "owner"
    mock_member.role_display_name = "Owner"
    mock_member.joined_at = now

    # Mock DB session and query chain
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [mock_member]
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_result

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    response = await client.get("/api/v1/me/organisations/")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == str(tenant_id)
    assert data[0]["slug"] == "my-org"
    assert data[0]["display_name"] == "My Organisation"
    assert data[0]["role_name"] == "owner"
    assert data[0]["role_display_name"] == "Owner"


@pytest.mark.asyncio
async def test_list_organisations_empty(client, mock_user, app):
    """GET /api/v1/me/organisations/ returns empty list when no memberships."""
    from auth.api.deps import get_db

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_result

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    response = await client.get("/api/v1/me/organisations/")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_organisations_excludes_inactive(client, mock_user, app):
    """GET /api/v1/me/organisations/ excludes inactive tenants."""
    from auth.api.deps import get_db

    mock_inactive_tenant = MagicMock()
    mock_inactive_tenant.is_active = False

    mock_member = MagicMock()
    mock_member.tenant = mock_inactive_tenant

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [mock_member]
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_result

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    response = await client.get("/api/v1/me/organisations/")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_create_organisation(client, mock_user, app):
    """POST /api/v1/me/organisations/ creates org and returns 201."""
    from auth.api.deps import get_db

    tenant_id = uuid.uuid4()
    now = datetime.now(UTC)

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    mock_tenant = MagicMock()
    mock_tenant.id = tenant_id
    mock_tenant.slug = "new-org"
    mock_tenant.display_name = "New Organisation"

    mock_member = MagicMock()
    mock_member.role_name = "owner"
    mock_member.role_display_name = "Owner"
    mock_member.joined_at = now

    with patch(
        "auth.api.routes.api.me.organisations._tenant_service.create_organisation_with_owner",
        new=AsyncMock(return_value=(mock_tenant, mock_member)),
    ):
        response = await client.post(
            "/api/v1/me/organisations/",
            json={"slug": "new-org", "display_name": "New Organisation"},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["id"] == str(tenant_id)
    assert data["slug"] == "new-org"
    assert data["display_name"] == "New Organisation"
    assert data["role_name"] == "owner"
    assert data["role_display_name"] == "Owner"
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_create_organisation_duplicate_slug(client, mock_user, app):
    """POST /api/v1/me/organisations/ with duplicate slug returns 409."""
    from auth.api.deps import get_db

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = MagicMock()  # Existing tenant
    mock_db.execute.return_value = mock_result

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    response = await client.post(
        "/api/v1/me/organisations/",
        json={"slug": "existing-org", "display_name": "Duplicate Org"},
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_organisation_invalid_slug(client, mock_user):
    """POST /api/v1/me/organisations/ with invalid slug returns 422."""
    response = await client.post(
        "/api/v1/me/organisations/",
        json={"slug": "INVALID SLUG!", "display_name": "Bad Org"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_organisations_unauthenticated(app):
    """GET /api/v1/me/organisations/ without token returns 401."""
    from auth.api.routes.api.deps import get_current_user_bearer
    from httpx import ASGITransport, AsyncClient

    app.dependency_overrides.pop(get_current_user_bearer, None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/me/organisations/")
    assert response.status_code == 401
