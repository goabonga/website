# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for /api/v1/organisations/{org_id}/branding endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.api.deps import get_branding_service
from auth.api.routes.api.deps import get_current_user_bearer
from httpx import ASGITransport, AsyncClient


def _make_mock_tenant(tenant_id: uuid.UUID | None = None) -> MagicMock:
    """Build a mock Tenant."""
    tenant = MagicMock()
    tenant.id = tenant_id or uuid.uuid4()
    tenant.slug = "test-org"
    tenant.display_name = "Test Organisation"
    tenant.is_active = True
    return tenant


def _make_mock_membership(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    scope: str = "branding:read",
) -> MagicMock:
    """Build a mock TenantMember with has_scope support."""
    member = MagicMock()
    member.tenant_id = tenant_id
    member.user_id = user_id

    def has_scope(s: str) -> bool:
        # Accept wildcard or exact match
        return s.startswith("branding:") or s == "*"

    member.has_scope = MagicMock(side_effect=has_scope)
    return member


def _make_mock_branding(tenant_id: uuid.UUID) -> MagicMock:
    """Build a mock TenantBranding."""
    branding = MagicMock()
    branding.id = uuid.uuid4()
    branding.tenant_id = tenant_id
    branding.logo_url = None
    branding.logo_dark_url = None
    branding.favicon_url = None
    branding.primary_color = "#007bff"
    branding.secondary_color = "#6c757d"
    branding.accent_color = "#28a745"
    branding.background_color = "#f5f5f5"
    branding.surface_color = "#ffffff"
    branding.text_color = "#333333"
    branding.text_muted_color = "#6c757d"
    branding.error_color = "#dc3545"
    branding.success_color = "#28a745"
    branding.border_color = "#0f3460"
    branding.warning_color = "#fdcb6e"
    branding.info_color = "#74b9ff"
    branding.input_background_color = None
    branding.input_focus_background_color = None
    branding.input_border_color = None
    branding.input_focus_border_color = None
    branding.input_text_color = None
    branding.font_family = "sans-serif"
    branding.font_url = None
    branding.custom_css = None
    branding.custom_js = None
    branding.show_powered_by = True
    branding.created_at = datetime.now(UTC)
    branding.updated_at = datetime.now(UTC)
    return branding


def _make_mock_branding_service(
    *,
    get_result: MagicMock | None = None,
    save_result: MagicMock | None = None,
    delete_result: bool = True,
) -> MagicMock:
    """Build a mock BrandingService with the three methods used by the route."""
    svc = MagicMock()
    svc.get_branding_record = AsyncMock(return_value=get_result)
    svc.save_branding = AsyncMock(return_value=save_result)
    svc.delete_branding = AsyncMock(return_value=delete_result)
    return svc


@pytest.fixture
def _make_app():
    """Return a factory that yields (app, user) with mocked auth."""
    from auth.main import app as fastapi_app

    created = []

    def factory(user: MagicMock | None = None):
        if user is None:
            user_ = MagicMock()
            user_.id = uuid.uuid4()
            user_.is_active = True
        else:
            user_ = user

        async def override_auth():
            return user_

        fastapi_app.dependency_overrides[get_current_user_bearer] = override_auth
        created.append(fastapi_app)
        return fastapi_app, user_

    yield factory

    for a in created:
        a.dependency_overrides.clear()


# ===========================================================================
# GET /api/v1/organisations/{org_id}/branding/
# ===========================================================================


@pytest.mark.asyncio
async def test_get_branding_success(_make_app):
    """GET branding returns 200 with branding data."""
    from auth.api.deps import get_db

    app, user = _make_app()
    tenant_id = uuid.uuid4()
    tenant = _make_mock_tenant(tenant_id)
    membership = _make_mock_membership(tenant_id, user.id)
    branding = _make_mock_branding(tenant_id)

    mock_db = AsyncMock()

    # require_org_membership: tenant query, membership query
    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_branding_service] = lambda: _make_mock_branding_service(
        get_result=branding
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/organisations/{tenant_id}/branding/")

    assert response.status_code == 200
    data = response.json()
    assert data["tenant_id"] == str(tenant_id)
    assert data["primary_color"] == "#007bff"
    assert data["show_powered_by"] is True


@pytest.mark.asyncio
async def test_get_branding_not_found(_make_app):
    """GET branding returns 404 when no branding configured."""
    from auth.api.deps import get_db

    app, user = _make_app()
    tenant_id = uuid.uuid4()
    tenant = _make_mock_tenant(tenant_id)
    membership = _make_mock_membership(tenant_id, user.id)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_branding_service] = lambda: _make_mock_branding_service(
        get_result=None
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/organisations/{tenant_id}/branding/")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_branding_not_member(_make_app):
    """GET branding returns 403 when user is not a member."""
    from auth.api.deps import get_db

    app, user = _make_app()
    tenant_id = uuid.uuid4()
    tenant = _make_mock_tenant(tenant_id)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = None  # not a member

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_branding_service] = lambda: _make_mock_branding_service()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/organisations/{tenant_id}/branding/")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_branding_org_not_found(_make_app):
    """GET branding returns 404 when org does not exist."""
    from auth.api.deps import get_db

    app, user = _make_app()

    mock_db = AsyncMock()
    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=tenant_result)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_branding_service] = lambda: _make_mock_branding_service()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/organisations/{uuid.uuid4()}/branding/")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_branding_unauthenticated():
    """GET branding without token returns 401."""
    from auth.main import app as fastapi_app

    fastapi_app.dependency_overrides.pop(get_current_user_bearer, None)

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/organisations/{uuid.uuid4()}/branding/")

    assert response.status_code == 401
    fastapi_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_branding_missing_scope(_make_app):
    """GET branding returns 403 when member lacks branding:read scope."""
    from auth.api.deps import get_db

    app, user = _make_app()
    tenant_id = uuid.uuid4()
    tenant = _make_mock_tenant(tenant_id)

    # Member without branding scope
    membership = MagicMock()
    membership.tenant_id = tenant_id
    membership.user_id = user.id
    membership.has_scope = MagicMock(return_value=False)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_branding_service] = lambda: _make_mock_branding_service()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/organisations/{tenant_id}/branding/")

    assert response.status_code == 403


# ===========================================================================
# PUT /api/v1/organisations/{org_id}/branding/
# ===========================================================================


@pytest.mark.asyncio
async def test_update_branding_create(_make_app):
    """PUT branding creates branding when none exists."""
    from auth.api.deps import get_db

    app, user = _make_app()
    tenant_id = uuid.uuid4()
    tenant = _make_mock_tenant(tenant_id)
    membership = _make_mock_membership(tenant_id, user.id)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result])

    created_branding = _make_mock_branding(tenant_id)
    created_branding.primary_color = "#ff0000"

    async def mock_refresh(obj, *args, **kwargs):
        pass

    mock_db.refresh = AsyncMock(side_effect=mock_refresh)

    svc = _make_mock_branding_service(save_result=created_branding)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_branding_service] = lambda: svc

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.put(
            f"/api/v1/organisations/{tenant_id}/branding/",
            json={"primary_color": "#ff0000"},
        )

    assert response.status_code == 200
    svc.save_branding.assert_awaited_once_with(mock_db, tenant_id, primary_color="#ff0000")
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_update_branding_existing(_make_app):
    """PUT branding updates existing branding."""
    from auth.api.deps import get_db

    app, user = _make_app()
    tenant_id = uuid.uuid4()
    tenant = _make_mock_tenant(tenant_id)
    membership = _make_mock_membership(tenant_id, user.id)
    branding = _make_mock_branding(tenant_id)
    branding.primary_color = "#ff0000"
    branding.font_family = "Roboto"

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result])

    async def mock_refresh(obj, *args, **kwargs):
        pass

    mock_db.refresh = AsyncMock(side_effect=mock_refresh)

    svc = _make_mock_branding_service(save_result=branding)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_branding_service] = lambda: svc

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.put(
            f"/api/v1/organisations/{tenant_id}/branding/",
            json={"primary_color": "#ff0000", "font_family": "Roboto"},
        )

    assert response.status_code == 200
    svc.save_branding.assert_awaited_once_with(
        mock_db, tenant_id, primary_color="#ff0000", font_family="Roboto"
    )
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_update_branding_validation_error(_make_app):
    """PUT branding with invalid color returns 422."""
    from auth.api.deps import get_db

    app, user = _make_app()
    tenant_id = uuid.uuid4()
    tenant = _make_mock_tenant(tenant_id)
    membership = _make_mock_membership(tenant_id, user.id)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_branding_service] = lambda: _make_mock_branding_service()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.put(
            f"/api/v1/organisations/{tenant_id}/branding/",
            json={"primary_color": "x"},  # too short
        )

    assert response.status_code == 422


# ===========================================================================
# DELETE /api/v1/organisations/{org_id}/branding/
# ===========================================================================


@pytest.mark.asyncio
async def test_delete_branding_success(_make_app):
    """DELETE branding returns 204."""
    from auth.api.deps import get_db

    app, user = _make_app()
    tenant_id = uuid.uuid4()
    tenant = _make_mock_tenant(tenant_id)
    membership = _make_mock_membership(tenant_id, user.id)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result])

    svc = _make_mock_branding_service(delete_result=True)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_branding_service] = lambda: svc

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.delete(f"/api/v1/organisations/{tenant_id}/branding/")

    assert response.status_code == 204
    svc.delete_branding.assert_awaited_once_with(mock_db, tenant_id)
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_delete_branding_not_found(_make_app):
    """DELETE branding returns 404 when no branding exists."""
    from auth.api.deps import get_db

    app, user = _make_app()
    tenant_id = uuid.uuid4()
    tenant = _make_mock_tenant(tenant_id)
    membership = _make_mock_membership(tenant_id, user.id)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result])

    svc = _make_mock_branding_service(delete_result=False)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_branding_service] = lambda: svc

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.delete(f"/api/v1/organisations/{tenant_id}/branding/")

    assert response.status_code == 404
