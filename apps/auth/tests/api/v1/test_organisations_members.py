# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for /api/v1/organisations/{org_id}/members endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.api.routes.api.deps import get_current_user_bearer
from httpx import ASGITransport, AsyncClient

# Module path for patching require_org_membership within the members route module
_ROM_PATH = "auth.api.routes.api.organisations.members.require_org_membership"
_SVC_PATH = "auth.api.routes.api.organisations.members.tenant_role_service"


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
    member.role_name = role_name
    member.role_display_name = role_name.capitalize()
    member.joined_at = datetime.now(UTC)
    member.created_at = datetime.now(UTC)
    member.updated_at = datetime.now(UTC)

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
# GET /api/v1/organisations/{org_id}/members/
# ===========================================================================


@pytest.mark.asyncio
async def test_list_members_success(_make_app):
    """GET returns paginated member list for user with members:read scope."""
    from auth.api.deps import get_db

    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True
    app, user = _make_app(user=user)

    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    target_member = _make_mock_membership(tenant.id, uuid.uuid4(), role_name="member")

    mock_db = AsyncMock()

    # count query
    count_result = MagicMock()
    count_result.scalar.return_value = 2

    # select members query
    select_result = MagicMock()
    select_scalars = MagicMock()
    select_scalars.all.return_value = [membership, target_member]
    select_result.scalars.return_value = select_scalars

    mock_db.execute = AsyncMock(side_effect=[count_result, select_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch(_ROM_PATH, new_callable=AsyncMock) as mock_rom:
        mock_rom.return_value = (user, tenant, membership)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/organisations/{tenant.id}/members/")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert data["page"] == 1


@pytest.mark.asyncio
async def test_list_members_forbidden_no_scope(_make_app):
    """GET returns 403 when user lacks members:read scope."""
    from auth.api.deps import get_db

    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True
    app, user = _make_app(user=user)

    tenant = _make_mock_tenant()

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    from fastapi import HTTPException, status

    with patch(_ROM_PATH, new_callable=AsyncMock) as mock_rom:
        mock_rom.side_effect = HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing required permission: members:read",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/organisations/{tenant.id}/members/")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_members_not_member(_make_app):
    """GET returns 403 when user is not a member of the org."""
    from auth.api.deps import get_db

    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True
    app, user = _make_app(user=user)

    tenant = _make_mock_tenant()

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    from fastapi import HTTPException, status

    with patch(_ROM_PATH, new_callable=AsyncMock) as mock_rom:
        mock_rom.side_effect = HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organisation",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/organisations/{tenant.id}/members/")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_members_org_not_found(_make_app):
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
            response = await ac.get(f"/api/v1/organisations/{uuid.uuid4()}/members/")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_members_unauthenticated():
    """GET returns 401 without bearer token."""
    from auth.main import app as fastapi_app

    fastapi_app.dependency_overrides.pop(get_current_user_bearer, None)

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/organisations/{uuid.uuid4()}/members/")

    assert response.status_code == 401
    fastapi_app.dependency_overrides.clear()


# ===========================================================================
# POST /api/v1/organisations/{org_id}/members/
# ===========================================================================


@pytest.mark.asyncio
async def test_add_member_success(_make_app):
    """POST creates a new member and returns 201."""
    from auth.api.deps import get_db

    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True
    app, user = _make_app(user=user)

    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    target_user_id = uuid.uuid4()

    new_member = _make_mock_membership(tenant.id, target_user_id, role_name="member")

    mock_db = AsyncMock()
    mock_db.add = MagicMock()

    # Check existing membership (tenant_service.get_member -> find_member)
    existing_check = MagicMock()
    existing_check.scalar_one_or_none.return_value = None

    # Reload after insert (tenant_service.get_member_by_id -> find_member_by_id)
    reload_result = MagicMock()
    reload_result.scalar_one_or_none.return_value = new_member

    mock_db.execute = AsyncMock(side_effect=[existing_check, reload_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with (
        patch(_ROM_PATH, new_callable=AsyncMock) as mock_rom,
        patch(_SVC_PATH) as mock_role_svc,
    ):
        mock_rom.return_value = (user, tenant, membership)
        mock_role = MagicMock()
        mock_role.id = uuid.uuid4()
        mock_role.tenant_id = tenant.id
        mock_role_svc.get_role_by_name = AsyncMock(return_value=mock_role)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                f"/api/v1/organisations/{tenant.id}/members/",
                json={"user_id": str(target_user_id)},
            )

    assert response.status_code == 201
    data = response.json()
    assert data["user_id"] == str(target_user_id)
    assert data["role_name"] == "member"


@pytest.mark.asyncio
async def test_add_member_already_exists(_make_app):
    """POST returns 409 when user is already a member."""
    from auth.api.deps import get_db

    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True
    app, user = _make_app(user=user)

    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)

    mock_db = AsyncMock()

    existing_check = MagicMock()
    existing_check.scalar_one_or_none.return_value = MagicMock()  # already exists

    mock_db.execute = AsyncMock(side_effect=[existing_check])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch(_ROM_PATH, new_callable=AsyncMock) as mock_rom:
        mock_rom.return_value = (user, tenant, membership)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                f"/api/v1/organisations/{tenant.id}/members/",
                json={"user_id": str(uuid.uuid4())},
            )

    assert response.status_code == 409
    assert "already a member" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_add_member_forbidden(_make_app):
    """POST returns 403 when user lacks members:invite scope."""
    from auth.api.deps import get_db

    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True
    app, user = _make_app(user=user)

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    from fastapi import HTTPException, status

    with patch(_ROM_PATH, new_callable=AsyncMock) as mock_rom:
        mock_rom.side_effect = HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing required permission: members:invite",
        )

        transport = ASGITransport(app=app)
        tenant_id = uuid.uuid4()
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                f"/api/v1/organisations/{tenant_id}/members/",
                json={"user_id": str(uuid.uuid4())},
            )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_add_member_invalid_body(_make_app):
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
            f"/api/v1/organisations/{uuid.uuid4()}/members/",
            json={"bad_field": "invalid"},
        )

    assert response.status_code == 422


# ===========================================================================
# PATCH /api/v1/organisations/{org_id}/members/{user_id}
# ===========================================================================


@pytest.mark.asyncio
async def test_update_member_success(_make_app):
    """PATCH updates member role and returns 200."""
    from auth.api.deps import get_db

    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True
    app, user = _make_app(user=user)

    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    target_user_id = uuid.uuid4()
    target_member = _make_mock_membership(tenant.id, target_user_id, role_name="member")

    new_role_id = uuid.uuid4()
    updated_member = _make_mock_membership(tenant.id, target_user_id, role_name="admin")

    mock_db = AsyncMock()

    # Find target member (tenant_service.get_member -> find_member)
    target_result = MagicMock()
    target_result.scalar_one_or_none.return_value = target_member

    # Reload after update (tenant_service.get_member_by_id -> find_member_by_id)
    reload_result = MagicMock()
    reload_result.scalar_one_or_none.return_value = updated_member

    mock_db.execute = AsyncMock(side_effect=[target_result, reload_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with (
        patch(_ROM_PATH, new_callable=AsyncMock) as mock_rom,
        patch(_SVC_PATH) as mock_role_svc,
    ):
        mock_rom.return_value = (user, tenant, membership)
        mock_role = MagicMock()
        mock_role.id = new_role_id
        mock_role.tenant_id = tenant.id
        mock_role.name = "admin"
        mock_role_svc.get_role_by_id = AsyncMock(return_value=mock_role)
        mock_role_svc.assign_role = AsyncMock(return_value=target_member)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.patch(
                f"/api/v1/organisations/{tenant.id}/members/{target_user_id}",
                json={"role_id": str(new_role_id)},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["role_name"] == "admin"


@pytest.mark.asyncio
async def test_update_member_not_found(_make_app):
    """PATCH returns 404 when target member does not exist."""
    from auth.api.deps import get_db

    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True
    app, user = _make_app(user=user)

    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)

    mock_db = AsyncMock()

    target_result = MagicMock()
    target_result.scalar_one_or_none.return_value = None

    mock_db.execute = AsyncMock(side_effect=[target_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch(_ROM_PATH, new_callable=AsyncMock) as mock_rom:
        mock_rom.return_value = (user, tenant, membership)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.patch(
                f"/api/v1/organisations/{tenant.id}/members/{uuid.uuid4()}",
                json={"role_id": str(uuid.uuid4())},
            )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_member_bad_role(_make_app):
    """PATCH returns 400 when role does not belong to the org."""
    from auth.api.deps import get_db

    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True
    app, user = _make_app(user=user)

    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    target_user_id = uuid.uuid4()
    target_member = _make_mock_membership(tenant.id, target_user_id, role_name="member")

    mock_db = AsyncMock()

    target_result = MagicMock()
    target_result.scalar_one_or_none.return_value = target_member

    mock_db.execute = AsyncMock(side_effect=[target_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with (
        patch(_ROM_PATH, new_callable=AsyncMock) as mock_rom,
        patch(_SVC_PATH) as mock_role_svc,
    ):
        mock_rom.return_value = (user, tenant, membership)
        mock_role_svc.get_role_by_id = AsyncMock(return_value=None)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.patch(
                f"/api/v1/organisations/{tenant.id}/members/{target_user_id}",
                json={"role_id": str(uuid.uuid4())},
            )

    assert response.status_code == 400


# ===========================================================================
# DELETE /api/v1/organisations/{org_id}/members/{user_id}
# ===========================================================================


@pytest.mark.asyncio
async def test_remove_member_success(_make_app):
    """DELETE removes member and returns 204."""
    from auth.api.deps import get_db

    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True
    app, user = _make_app(user=user)

    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    target_user_id = uuid.uuid4()
    target_member = _make_mock_membership(tenant.id, target_user_id, role_name="member")

    mock_db = AsyncMock()

    target_result = MagicMock()
    target_result.scalar_one_or_none.return_value = target_member

    mock_db.execute = AsyncMock(side_effect=[target_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch(_ROM_PATH, new_callable=AsyncMock) as mock_rom:
        mock_rom.return_value = (user, tenant, membership)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(
                f"/api/v1/organisations/{tenant.id}/members/{target_user_id}"
            )

    assert response.status_code == 204
    mock_db.delete.assert_called_once_with(target_member)
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_remove_member_not_found(_make_app):
    """DELETE returns 404 when member does not exist."""
    from auth.api.deps import get_db

    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True
    app, user = _make_app(user=user)

    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)

    mock_db = AsyncMock()

    target_result = MagicMock()
    target_result.scalar_one_or_none.return_value = None

    mock_db.execute = AsyncMock(side_effect=[target_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch(_ROM_PATH, new_callable=AsyncMock) as mock_rom:
        mock_rom.return_value = (user, tenant, membership)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(f"/api/v1/organisations/{tenant.id}/members/{uuid.uuid4()}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_remove_member_forbidden(_make_app):
    """DELETE returns 403 when user lacks members:remove scope."""
    from auth.api.deps import get_db

    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True
    app, user = _make_app(user=user)

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    from fastapi import HTTPException, status

    with patch(_ROM_PATH, new_callable=AsyncMock) as mock_rom:
        mock_rom.side_effect = HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing required permission: members:remove",
        )

        transport = ASGITransport(app=app)
        tenant_id = uuid.uuid4()
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(f"/api/v1/organisations/{tenant_id}/members/{uuid.uuid4()}")

    assert response.status_code == 403
