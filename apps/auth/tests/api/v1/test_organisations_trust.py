# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for /api/v1/organisations/{org_id}/trust endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.api.deps import get_db, get_trust_service
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
) -> MagicMock:
    """Build a mock Tenant."""
    tenant = MagicMock()
    tenant.id = tenant_id or uuid.uuid4()
    tenant.slug = "test-org"
    tenant.display_name = "Test Org"
    tenant.is_active = True
    tenant.trust_mode = MagicMock()
    tenant.trust_mode.value = "none"
    tenant.settings = {}
    tenant.created_at = datetime.now(UTC)
    tenant.updated_at = datetime.now(UTC)
    return tenant


def _make_mock_membership(has_scope: bool = True) -> MagicMock:
    """Build a mock TenantMember."""
    member = MagicMock()
    member.has_scope = MagicMock(return_value=has_scope)
    return member


def _trust_config(mode: str = "none", sources: list | None = None) -> dict:
    """Build a raw trust config dict as returned by TrustPolicyService."""
    return {
        "trust_mode": mode,
        "trusted_sources": sources or [],
    }


@pytest.fixture
def _make_app():
    """Factory that yields (app, user, mock_db, mock_trust_svc) with deps overridden."""
    from auth.main import app as fastapi_app

    created: list = []

    def factory(user: MagicMock | None = None):
        if user is None:
            user = _make_mock_user()

        mock_db = AsyncMock()
        mock_trust_svc = MagicMock()

        async def override_auth():
            return user

        async def override_db():
            yield mock_db

        fastapi_app.dependency_overrides[get_current_user_bearer] = override_auth
        fastapi_app.dependency_overrides[get_db] = override_db
        fastapi_app.dependency_overrides[get_trust_service] = lambda: mock_trust_svc
        created.append(fastapi_app)
        return fastapi_app, user, mock_db, mock_trust_svc

    yield factory

    for a in created:
        a.dependency_overrides.clear()


# ===========================================================================
# GET /api/v1/organisations/{org_id}/trust/
# ===========================================================================


@pytest.mark.asyncio
async def test_get_trust_config_success(_make_app):
    """GET trust config returns mode and sources."""
    app, user, mock_db, mock_trust_svc = _make_app()
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(has_scope=True)

    source_id = uuid.uuid4()
    trusted_tid = uuid.uuid4()
    config = _trust_config(
        mode="specific",
        sources=[
            {
                "id": str(source_id),
                "trusted_tenant_id": str(trusted_tid),
                "trusted_tenant_name": "Partner Org",
                "trusted_tenant_slug": "partner",
                "is_platform": False,
                "description": None,
            }
        ],
    )

    mock_trust_svc.get_tenant_trust_config = AsyncMock(return_value=config)

    with patch(
        "auth.api.routes.api.organisations.trust.require_org_membership",
        new_callable=AsyncMock,
        return_value=(user, tenant, membership),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/organisations/{tenant.id}/trust/")

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "specific"
    assert len(data["trusted_sources"]) == 1
    assert data["trusted_sources"][0]["trusted_tenant_slug"] == "partner"


@pytest.mark.asyncio
async def test_get_trust_config_empty(_make_app):
    """GET trust config with no sources returns empty list."""
    app, user, mock_db, mock_trust_svc = _make_app()
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(has_scope=True)

    config = _trust_config(mode="none", sources=[])
    mock_trust_svc.get_tenant_trust_config = AsyncMock(return_value=config)

    with patch(
        "auth.api.routes.api.organisations.trust.require_org_membership",
        new_callable=AsyncMock,
        return_value=(user, tenant, membership),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/organisations/{tenant.id}/trust/")

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "none"
    assert data["trusted_sources"] == []


@pytest.mark.asyncio
async def test_get_trust_config_forbidden(_make_app):
    """GET trust config without trust:read scope returns 403."""
    from fastapi import HTTPException

    app, user, mock_db, mock_trust_svc = _make_app()
    tenant = _make_mock_tenant()

    with patch(
        "auth.api.routes.api.organisations.trust.require_org_membership",
        new_callable=AsyncMock,
        side_effect=HTTPException(
            status_code=403,
            detail="Missing required permission: trust:read",
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/organisations/{tenant.id}/trust/")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_trust_config_not_found(_make_app):
    """GET trust config for unknown org returns 404 when service returns None."""
    app, user, mock_db, mock_trust_svc = _make_app()
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(has_scope=True)

    mock_trust_svc.get_tenant_trust_config = AsyncMock(return_value=None)

    with patch(
        "auth.api.routes.api.organisations.trust.require_org_membership",
        new_callable=AsyncMock,
        return_value=(user, tenant, membership),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/organisations/{uuid.uuid4()}/trust/")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_trust_config_unauthenticated():
    """GET trust config without token returns 401."""
    from auth.main import app as fastapi_app

    fastapi_app.dependency_overrides.pop(get_current_user_bearer, None)

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    fastapi_app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/organisations/{uuid.uuid4()}/trust/")

    assert response.status_code == 401
    fastapi_app.dependency_overrides.clear()


# ===========================================================================
# PUT /api/v1/organisations/{org_id}/trust/
# ===========================================================================


@pytest.mark.asyncio
async def test_update_trust_mode_success(_make_app):
    """PUT trust mode updates and returns new config."""
    app, user, mock_db, mock_trust_svc = _make_app()
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(has_scope=True)

    updated_config = _trust_config(mode="all", sources=[])
    mock_trust_svc.update_trust_mode = AsyncMock(return_value=True)
    mock_trust_svc.get_tenant_trust_config = AsyncMock(return_value=updated_config)

    with patch(
        "auth.api.routes.api.organisations.trust.require_org_membership",
        new_callable=AsyncMock,
        return_value=(user, tenant, membership),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.put(
                f"/api/v1/organisations/{tenant.id}/trust/",
                json={"mode": "all"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "all"


@pytest.mark.asyncio
async def test_update_trust_mode_invalid(_make_app):
    """PUT trust mode with invalid value returns 400."""
    app, user, mock_db, mock_trust_svc = _make_app()
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(has_scope=True)

    with patch(
        "auth.api.routes.api.organisations.trust.require_org_membership",
        new_callable=AsyncMock,
        return_value=(user, tenant, membership),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.put(
                f"/api/v1/organisations/{tenant.id}/trust/",
                json={"mode": "invalid_mode"},
            )

    assert response.status_code == 400
    assert "Invalid trust mode" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_trust_mode_forbidden(_make_app):
    """PUT trust mode without trust:write scope returns 403."""
    from fastapi import HTTPException

    app, user, mock_db, mock_trust_svc = _make_app()
    tenant = _make_mock_tenant()

    with patch(
        "auth.api.routes.api.organisations.trust.require_org_membership",
        new_callable=AsyncMock,
        side_effect=HTTPException(
            status_code=403,
            detail="Missing required permission: trust:write",
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.put(
                f"/api/v1/organisations/{tenant.id}/trust/",
                json={"mode": "all"},
            )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_trust_mode_validation_error(_make_app):
    """PUT trust mode with empty body returns 422."""
    app, user, mock_db, mock_trust_svc = _make_app()
    tenant = _make_mock_tenant()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.put(
            f"/api/v1/organisations/{tenant.id}/trust/",
            json={},
        )

    assert response.status_code == 422


# ===========================================================================
# POST /api/v1/organisations/{org_id}/trust/sources
# ===========================================================================


@pytest.mark.asyncio
async def test_add_trusted_source_success(_make_app):
    """POST trusted source returns 201 with updated config."""
    app, user, mock_db, mock_trust_svc = _make_app()
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(has_scope=True)

    source_tenant_id = uuid.uuid4()
    source_id = uuid.uuid4()
    new_source = MagicMock()
    new_source.id = source_id

    updated_config = _trust_config(
        mode="specific",
        sources=[
            {
                "id": str(source_id),
                "trusted_tenant_id": str(source_tenant_id),
                "trusted_tenant_name": "New Partner",
                "trusted_tenant_slug": "new-partner",
                "is_platform": False,
                "description": None,
            }
        ],
    )

    mock_trust_svc.add_trusted_source = AsyncMock(return_value=new_source)
    mock_trust_svc.get_tenant_trust_config = AsyncMock(return_value=updated_config)

    with patch(
        "auth.api.routes.api.organisations.trust.require_org_membership",
        new_callable=AsyncMock,
        return_value=(user, tenant, membership),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                f"/api/v1/organisations/{tenant.id}/trust/sources",
                json={"source_tenant_id": str(source_tenant_id)},
            )

    assert response.status_code == 201
    data = response.json()
    assert data["mode"] == "specific"
    assert len(data["trusted_sources"]) == 1


@pytest.mark.asyncio
async def test_add_trusted_source_conflict(_make_app):
    """POST trusted source that already exists returns 409."""
    app, user, mock_db, mock_trust_svc = _make_app()
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(has_scope=True)

    mock_trust_svc.add_trusted_source = AsyncMock(return_value=None)

    with patch(
        "auth.api.routes.api.organisations.trust.require_org_membership",
        new_callable=AsyncMock,
        return_value=(user, tenant, membership),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                f"/api/v1/organisations/{tenant.id}/trust/sources",
                json={"source_tenant_id": str(uuid.uuid4())},
            )

    assert response.status_code == 409
    assert "already" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_add_trusted_source_forbidden(_make_app):
    """POST trusted source without trust:write scope returns 403."""
    from fastapi import HTTPException

    app, user, mock_db, mock_trust_svc = _make_app()
    tenant = _make_mock_tenant()

    with patch(
        "auth.api.routes.api.organisations.trust.require_org_membership",
        new_callable=AsyncMock,
        side_effect=HTTPException(
            status_code=403,
            detail="Missing required permission: trust:write",
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                f"/api/v1/organisations/{tenant.id}/trust/sources",
                json={"source_tenant_id": str(uuid.uuid4())},
            )

    assert response.status_code == 403


# ===========================================================================
# DELETE /api/v1/organisations/{org_id}/trust/sources/{source_id}
# ===========================================================================


@pytest.mark.asyncio
async def test_remove_trusted_source_success(_make_app):
    """DELETE trusted source returns 204."""
    app, user, mock_db, mock_trust_svc = _make_app()
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(has_scope=True)
    source_id = uuid.uuid4()

    mock_trust_svc.remove_trusted_source = AsyncMock(return_value=True)

    with patch(
        "auth.api.routes.api.organisations.trust.require_org_membership",
        new_callable=AsyncMock,
        return_value=(user, tenant, membership),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(
                f"/api/v1/organisations/{tenant.id}/trust/sources/{source_id}",
            )

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_remove_trusted_source_not_found(_make_app):
    """DELETE trusted source that doesn't exist returns 404."""
    app, user, mock_db, mock_trust_svc = _make_app()
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(has_scope=True)
    source_id = uuid.uuid4()

    mock_trust_svc.remove_trusted_source = AsyncMock(return_value=False)

    with patch(
        "auth.api.routes.api.organisations.trust.require_org_membership",
        new_callable=AsyncMock,
        return_value=(user, tenant, membership),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(
                f"/api/v1/organisations/{tenant.id}/trust/sources/{source_id}",
            )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_remove_trusted_source_forbidden(_make_app):
    """DELETE trusted source without trust:write scope returns 403."""
    from fastapi import HTTPException

    app, user, mock_db, mock_trust_svc = _make_app()
    tenant = _make_mock_tenant()
    source_id = uuid.uuid4()

    with patch(
        "auth.api.routes.api.organisations.trust.require_org_membership",
        new_callable=AsyncMock,
        side_effect=HTTPException(
            status_code=403,
            detail="Missing required permission: trust:write",
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(
                f"/api/v1/organisations/{tenant.id}/trust/sources/{source_id}",
            )

    assert response.status_code == 403
