# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for /api/v1/organisations/{org_id}/roles endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.api.routes.api.deps import get_current_user_bearer
from httpx import ASGITransport, AsyncClient

# Module path for patching
_ROM_PATH = "auth.api.routes.api.organisations.roles.require_org_membership"
_SVC_PATH = "auth.api.routes.api.organisations.roles.tenant_role_service"


def _make_mock_tenant(tenant_id: uuid.UUID | None = None) -> MagicMock:
    """Build a mock Tenant."""
    tenant = MagicMock()
    tenant.id = tenant_id or uuid.uuid4()
    tenant.slug = "test-org"
    tenant.display_name = "Test Organisation"
    tenant.is_active = True
    tenant.settings = {}
    return tenant


def _make_mock_membership(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    role_name: str = "owner",
    scopes: list[str] | None = None,
) -> MagicMock:
    """Build a mock TenantMember with role."""
    member = MagicMock()
    member.id = uuid.uuid4()
    member.tenant_id = tenant_id
    member.user_id = user_id
    member.role_id = uuid.uuid4()

    _scopes = scopes if scopes is not None else ["*"]

    role = MagicMock()
    role.name = role_name
    role.scopes = _scopes
    member.custom_role = role

    def has_scope(scope: str) -> bool:
        if "*" in _scopes:
            return True
        resource = scope.split(":")[0] if ":" in scope else scope
        return scope in _scopes or f"{resource}:*" in _scopes

    member.has_scope = MagicMock(side_effect=has_scope)
    return member


def _make_mock_role(
    tenant_id: uuid.UUID,
    role_id: uuid.UUID | None = None,
    name: str = "editor",
    display_name: str = "Editor",
    is_system: bool = False,
    is_default: bool = False,
) -> MagicMock:
    """Build a mock TenantCustomRole."""
    role = MagicMock()
    role.id = role_id or uuid.uuid4()
    role.tenant_id = tenant_id
    role.name = name
    role.display_name = display_name
    role.description = f"Description for {name}"
    role.scopes = ["members:read", "settings:read"]
    role.is_system = is_system
    role.is_default = is_default
    role.display_order = 3
    role.created_at = datetime.now(UTC)
    role.updated_at = datetime.now(UTC)
    return role


@pytest.fixture
def _make_app():
    """Return a factory that yields (app, user) with auth override."""
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
# GET /api/v1/organisations/{org_id}/roles/
# ===========================================================================


@pytest.mark.asyncio
async def test_list_roles_success(_make_app):
    """GET returns list of roles for the organisation."""
    from auth.api.deps import get_db

    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True
    app, user = _make_app(user=user)

    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)

    role1 = _make_mock_role(tenant.id, name="owner", display_name="Owner", is_system=True)
    role2 = _make_mock_role(tenant.id, name="editor", display_name="Editor")

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with (
        patch(_ROM_PATH, new_callable=AsyncMock) as mock_rom,
        patch(_SVC_PATH) as mock_svc,
    ):
        mock_rom.return_value = (user, tenant, membership)
        mock_svc.get_tenant_roles = AsyncMock(return_value=[role1, role2])

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/organisations/{tenant.id}/roles/")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["name"] == "owner"
    assert data[1]["name"] == "editor"


@pytest.mark.asyncio
async def test_list_roles_forbidden(_make_app):
    """GET returns 403 when user lacks roles:read scope."""
    from auth.api.deps import get_db

    app, user = _make_app()

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    from fastapi import HTTPException, status

    with patch(_ROM_PATH, new_callable=AsyncMock) as mock_rom:
        mock_rom.side_effect = HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing required permission: roles:read",
        )

        transport = ASGITransport(app=app)
        tenant_id = uuid.uuid4()
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/organisations/{tenant_id}/roles/")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_roles_org_not_found(_make_app):
    """GET returns 404 when org does not exist."""
    from auth.api.deps import get_db

    app, user = _make_app()

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    from fastapi import HTTPException, status

    with patch(_ROM_PATH, new_callable=AsyncMock) as mock_rom:
        mock_rom.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organisation not found",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/organisations/{uuid.uuid4()}/roles/")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_roles_unauthenticated():
    """GET returns 401 without bearer token."""
    from auth.main import app as fastapi_app

    fastapi_app.dependency_overrides.pop(get_current_user_bearer, None)

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/organisations/{uuid.uuid4()}/roles/")

    assert response.status_code == 401
    fastapi_app.dependency_overrides.clear()


# ===========================================================================
# POST /api/v1/organisations/{org_id}/roles/
# ===========================================================================


@pytest.mark.asyncio
async def test_create_role_success(_make_app):
    """POST creates a custom role and returns 201."""
    from auth.api.deps import get_db

    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True
    app, user = _make_app(user=user)

    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)

    new_role = _make_mock_role(tenant.id, name="reviewer", display_name="Reviewer")

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with (
        patch(_ROM_PATH, new_callable=AsyncMock) as mock_rom,
        patch(_SVC_PATH) as mock_svc,
    ):
        mock_rom.return_value = (user, tenant, membership)
        mock_svc.create_role = AsyncMock(return_value=new_role)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                f"/api/v1/organisations/{tenant.id}/roles/",
                json={
                    "name": "reviewer",
                    "display_name": "Reviewer",
                    "description": "Can review content",
                    "scopes": ["members:read", "settings:read"],
                },
            )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "reviewer"
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_create_role_duplicate_name(_make_app):
    """POST returns 400 when role name already exists."""
    from auth.api.deps import get_db

    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True
    app, user = _make_app(user=user)

    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with (
        patch(_ROM_PATH, new_callable=AsyncMock) as mock_rom,
        patch(_SVC_PATH) as mock_svc,
    ):
        mock_rom.return_value = (user, tenant, membership)
        mock_svc.create_role = AsyncMock(side_effect=ValueError("Role 'editor' already exists"))

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                f"/api/v1/organisations/{tenant.id}/roles/",
                json={
                    "name": "editor",
                    "display_name": "Editor",
                    "scopes": ["members:read"],
                },
            )

    assert response.status_code == 400
    assert "already exists" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_role_forbidden(_make_app):
    """POST returns 403 when user lacks roles:write scope."""
    from auth.api.deps import get_db

    app, user = _make_app()

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    from fastapi import HTTPException, status

    with patch(_ROM_PATH, new_callable=AsyncMock) as mock_rom:
        mock_rom.side_effect = HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing required permission: roles:write",
        )

        transport = ASGITransport(app=app)
        tenant_id = uuid.uuid4()
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                f"/api/v1/organisations/{tenant_id}/roles/",
                json={
                    "name": "editor",
                    "display_name": "Editor",
                    "scopes": ["members:read"],
                },
            )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_role_invalid_body(_make_app):
    """POST returns 422 with invalid request body."""
    from auth.api.deps import get_db

    app, user = _make_app()

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            f"/api/v1/organisations/{uuid.uuid4()}/roles/",
            json={"name": "x"},  # missing required fields
        )

    assert response.status_code == 422


# ===========================================================================
# PATCH /api/v1/organisations/{org_id}/roles/{role_id}
# ===========================================================================


@pytest.mark.asyncio
async def test_update_role_success(_make_app):
    """PATCH updates a role and returns 200."""
    from auth.api.deps import get_db

    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True
    app, user = _make_app(user=user)

    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    role = _make_mock_role(tenant.id)

    updated_role = _make_mock_role(tenant.id, role_id=role.id, display_name="Updated Editor")

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with (
        patch(_ROM_PATH, new_callable=AsyncMock) as mock_rom,
        patch(_SVC_PATH) as mock_svc,
    ):
        mock_rom.return_value = (user, tenant, membership)
        mock_svc.get_role_by_id = AsyncMock(return_value=role)
        mock_svc.update_role = AsyncMock(return_value=updated_role)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.patch(
                f"/api/v1/organisations/{tenant.id}/roles/{role.id}",
                json={"display_name": "Updated Editor"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["display_name"] == "Updated Editor"
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_update_role_not_found(_make_app):
    """PATCH returns 404 when role does not exist."""
    from auth.api.deps import get_db

    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True
    app, user = _make_app(user=user)

    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with (
        patch(_ROM_PATH, new_callable=AsyncMock) as mock_rom,
        patch(_SVC_PATH) as mock_svc,
    ):
        mock_rom.return_value = (user, tenant, membership)
        mock_svc.get_role_by_id = AsyncMock(return_value=None)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.patch(
                f"/api/v1/organisations/{tenant.id}/roles/{uuid.uuid4()}",
                json={"display_name": "Nope"},
            )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_system_role_scopes_error(_make_app):
    """PATCH returns 400 when attempting to modify system role scopes."""
    from auth.api.deps import get_db

    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True
    app, user = _make_app(user=user)

    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    role = _make_mock_role(tenant.id, name="owner", is_system=True)

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with (
        patch(_ROM_PATH, new_callable=AsyncMock) as mock_rom,
        patch(_SVC_PATH) as mock_svc,
    ):
        mock_rom.return_value = (user, tenant, membership)
        mock_svc.get_role_by_id = AsyncMock(return_value=role)
        mock_svc.update_role = AsyncMock(
            side_effect=ValueError("Cannot modify scopes of system roles")
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.patch(
                f"/api/v1/organisations/{tenant.id}/roles/{role.id}",
                json={"scopes": ["members:read"]},
            )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_update_role_toggle_is_default(_make_app):
    """PATCH is_default=true calls set_default_role on the service."""
    from auth.api.deps import get_db

    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True
    app, user = _make_app(user=user)

    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    role = _make_mock_role(tenant.id, is_default=False)

    # After set_default_role runs, the flag flips to True in-place so the
    # response reflects the new state.
    def _set_default_side_effect(_db, _tenant_id, _role_id):
        role.is_default = True
        return role

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with (
        patch(_ROM_PATH, new_callable=AsyncMock) as mock_rom,
        patch(_SVC_PATH) as mock_svc,
    ):
        mock_rom.return_value = (user, tenant, membership)
        mock_svc.get_role_by_id = AsyncMock(return_value=role)
        mock_svc.update_role = AsyncMock(return_value=role)
        mock_svc.set_default_role = AsyncMock(side_effect=_set_default_side_effect)
        mock_svc.clear_default_role = AsyncMock()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.patch(
                f"/api/v1/organisations/{tenant.id}/roles/{role.id}",
                json={"is_default": True},
            )

    assert response.status_code == 200
    assert response.json()["is_default"] is True
    mock_svc.set_default_role.assert_awaited_once_with(mock_db, tenant.id, role.id)
    mock_svc.clear_default_role.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_role_clear_is_default(_make_app):
    """PATCH is_default=false on a default role clears it."""
    from auth.api.deps import get_db

    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True
    app, user = _make_app(user=user)

    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    role = _make_mock_role(tenant.id, is_default=True)

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with (
        patch(_ROM_PATH, new_callable=AsyncMock) as mock_rom,
        patch(_SVC_PATH) as mock_svc,
    ):
        mock_rom.return_value = (user, tenant, membership)
        mock_svc.get_role_by_id = AsyncMock(return_value=role)
        mock_svc.update_role = AsyncMock(return_value=role)
        mock_svc.set_default_role = AsyncMock()
        mock_svc.clear_default_role = AsyncMock()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.patch(
                f"/api/v1/organisations/{tenant.id}/roles/{role.id}",
                json={"is_default": False},
            )

    assert response.status_code == 200
    mock_svc.clear_default_role.assert_awaited_once_with(mock_db, tenant.id)
    mock_svc.set_default_role.assert_not_awaited()


# ===========================================================================
# DELETE /api/v1/organisations/{org_id}/roles/{role_id}
# ===========================================================================


@pytest.mark.asyncio
async def test_delete_role_success(_make_app):
    """DELETE removes a role and returns 204."""
    from auth.api.deps import get_db

    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True
    app, user = _make_app(user=user)

    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    role = _make_mock_role(tenant.id)

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with (
        patch(_ROM_PATH, new_callable=AsyncMock) as mock_rom,
        patch(_SVC_PATH) as mock_svc,
    ):
        mock_rom.return_value = (user, tenant, membership)
        mock_svc.get_role_by_id = AsyncMock(return_value=role)
        mock_svc.delete_role = AsyncMock(return_value=None)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(f"/api/v1/organisations/{tenant.id}/roles/{role.id}")

    assert response.status_code == 204
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_delete_role_not_found(_make_app):
    """DELETE returns 404 when role does not exist."""
    from auth.api.deps import get_db

    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True
    app, user = _make_app(user=user)

    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with (
        patch(_ROM_PATH, new_callable=AsyncMock) as mock_rom,
        patch(_SVC_PATH) as mock_svc,
    ):
        mock_rom.return_value = (user, tenant, membership)
        mock_svc.get_role_by_id = AsyncMock(return_value=None)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(f"/api/v1/organisations/{tenant.id}/roles/{uuid.uuid4()}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_system_role_error(_make_app):
    """DELETE returns 400 when attempting to delete system role."""
    from auth.api.deps import get_db

    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True
    app, user = _make_app(user=user)

    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    role = _make_mock_role(tenant.id, name="owner", is_system=True)

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with (
        patch(_ROM_PATH, new_callable=AsyncMock) as mock_rom,
        patch(_SVC_PATH) as mock_svc,
    ):
        mock_rom.return_value = (user, tenant, membership)
        mock_svc.get_role_by_id = AsyncMock(return_value=role)
        mock_svc.delete_role = AsyncMock(side_effect=ValueError("Cannot delete system roles"))

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(f"/api/v1/organisations/{tenant.id}/roles/{role.id}")

    assert response.status_code == 400
    assert "system" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_role_forbidden(_make_app):
    """DELETE returns 403 when user lacks roles:delete scope."""
    from auth.api.deps import get_db

    app, user = _make_app()

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    from fastapi import HTTPException, status

    with patch(_ROM_PATH, new_callable=AsyncMock) as mock_rom:
        mock_rom.side_effect = HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing required permission: roles:delete",
        )

        transport = ASGITransport(app=app)
        tenant_id = uuid.uuid4()
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(f"/api/v1/organisations/{tenant_id}/roles/{uuid.uuid4()}")

    assert response.status_code == 403
