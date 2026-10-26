# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for /api/v1/me/organisations/{org_id}/clients endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.api.routes.api.deps import get_current_user_bearer
from httpx import ASGITransport, AsyncClient


def _make_mock_user(user_id: uuid.UUID | None = None) -> MagicMock:
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.is_active = True
    return user


def _make_mock_tenant(tenant_id: uuid.UUID | None = None) -> MagicMock:
    tenant = MagicMock()
    tenant.id = tenant_id or uuid.uuid4()
    tenant.slug = "test-org"
    tenant.display_name = "Test Organisation"
    tenant.is_active = True
    return tenant


def _make_mock_membership(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    has_scope: bool = True,
) -> MagicMock:
    member = MagicMock()
    member.tenant_id = tenant_id
    member.user_id = user_id
    member.has_scope = MagicMock(return_value=has_scope)
    role = MagicMock()
    role.name = "owner"
    member.custom_role = role
    member.role = role
    return member


def _make_mock_client(
    client_uuid: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    client_id: str = "abc123",
    name: str = "Test Client",
    is_confidential: bool = True,
) -> MagicMock:
    client = MagicMock()
    client.id = client_uuid or uuid.uuid4()
    client.client_id = client_id
    client.name = name
    client.description = None
    client.homepage_url = None
    client.redirect_uris = ["https://example.com/callback"]
    client.allowed_scopes = ["openid", "profile"]
    client.allowed_grant_types = ["authorization_code"]
    client.token_endpoint_auth_method = "client_secret_basic"
    client.is_confidential = is_confidential
    client.is_active = True
    client.require_pkce = True
    client.require_consent = True
    client.jwks_uri = None
    client.allowed_origins = None
    client.access_token_expiry_seconds = None
    client.refresh_token_expiry_seconds = None
    client.tenant_id = tenant_id or uuid.uuid4()
    client.client_secret_hash = "hash" if is_confidential else None
    client.created_at = datetime.now(UTC)
    client.updated_at = datetime.now(UTC)
    return client


@pytest.fixture
def _make_app():
    """Return a factory that creates (app, user) with overridden auth."""
    from auth.main import app as fastapi_app

    created = []

    def factory(user: MagicMock | None = None):
        if user is None:
            user = _make_mock_user()

        async def override_auth():
            return user

        fastapi_app.dependency_overrides[get_current_user_bearer] = override_auth
        created.append(fastapi_app)
        return fastapi_app, user

    yield factory

    for a in created:
        a.dependency_overrides.clear()


# ===========================================================================
# GET /api/v1/me/organisations/{org_id}/clients/ - List
# ===========================================================================


@pytest.mark.asyncio
async def test_list_clients_success(_make_app):
    """GET /{org_id}/clients/ returns paginated list."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    client_obj = _make_mock_client(tenant_id=tenant.id)

    mock_db = AsyncMock()

    # require_org_membership: tenant query, membership query
    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership

    # Count query
    count_result = MagicMock()
    count_result.scalar.return_value = 1

    # Select query
    select_result = MagicMock()
    select_scalars = MagicMock()
    select_scalars.all.return_value = [client_obj]
    select_result.scalars.return_value = select_scalars

    mock_db.execute = AsyncMock(
        side_effect=[tenant_result, member_result, count_result, select_result]
    )

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/me/organisations/{tenant.id}/clients/")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["client_id"] == "abc123"


@pytest.mark.asyncio
async def test_list_clients_forbidden(_make_app):
    """GET /{org_id}/clients/ without clients:read scope returns 403."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id, has_scope=False)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/me/organisations/{tenant.id}/clients/")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_clients_org_not_found(_make_app):
    """GET /{org_id}/clients/ with unknown org returns 404."""
    from auth.api.deps import get_db

    app, user = _make_app()

    mock_db = AsyncMock()
    no_result = MagicMock()
    no_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=no_result)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/me/organisations/{uuid.uuid4()}/clients/")

    assert response.status_code == 404


# ===========================================================================
# POST /api/v1/me/organisations/{org_id}/clients/ - Create
# ===========================================================================


@pytest.mark.asyncio
async def test_create_client_success(_make_app):
    """POST /{org_id}/clients/ creates client and returns 201."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)

    mock_db = AsyncMock()
    mock_db.add = MagicMock()

    # require_org_membership
    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result])

    now = datetime.now(UTC)
    added_objects: list = []

    def capture_add(obj):
        added_objects.append(obj)

    mock_db.add = MagicMock(side_effect=capture_add)

    async def mock_flush():
        for obj in added_objects:
            if hasattr(obj, "client_id") and not hasattr(obj, "_id_set"):
                obj.id = uuid.uuid4()
                obj.created_at = now
                obj.updated_at = now
                obj._id_set = True

    mock_db.flush = AsyncMock(side_effect=mock_flush)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with (
        patch(
            "auth.api.routes.api.me.organisations.clients.generate_client_id",
            return_value="gen_client_id",
        ),
        patch(
            "auth.api.routes.api.me.organisations.clients.generate_client_secret",
            return_value="gen_client_secret",
        ),
        patch("auth.api.routes.api.me.organisations.clients._hasher") as mock_hasher,
    ):
        mock_hasher.hash.return_value = "argon2_hash"

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                f"/api/v1/me/organisations/{tenant.id}/clients/",
                json={
                    "name": "New Client",
                    "redirect_uris": ["https://example.com/cb"],
                },
            )

    assert response.status_code == 201
    data = response.json()
    assert data["client_id"] == "gen_client_id"
    assert data["name"] == "New Client"
    assert data["client_secret"] == "gen_client_secret"


@pytest.mark.asyncio
async def test_create_client_public_no_secret(_make_app):
    """POST /{org_id}/clients/ with is_confidential=false returns no secret."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)

    mock_db = AsyncMock()
    mock_db.add = MagicMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result])

    now = datetime.now(UTC)
    added_objects: list = []

    def capture_add(obj):
        added_objects.append(obj)

    mock_db.add = MagicMock(side_effect=capture_add)

    async def mock_flush():
        for obj in added_objects:
            if hasattr(obj, "client_id") and not hasattr(obj, "_id_set"):
                obj.id = uuid.uuid4()
                obj.created_at = now
                obj.updated_at = now
                obj._id_set = True

    mock_db.flush = AsyncMock(side_effect=mock_flush)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch(
        "auth.api.routes.api.me.organisations.clients.generate_client_id",
        return_value="pub_client_id",
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                f"/api/v1/me/organisations/{tenant.id}/clients/",
                json={
                    "name": "Public Client",
                    "is_confidential": False,
                },
            )

    assert response.status_code == 201
    data = response.json()
    assert "client_secret" not in data
    assert data["is_confidential"] is False


# ===========================================================================
# GET /api/v1/me/organisations/{org_id}/clients/{client_uuid} - Get one
# ===========================================================================


@pytest.mark.asyncio
async def test_get_client_success(_make_app):
    """GET /{org_id}/clients/{uuid} returns the client."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    client_obj = _make_mock_client(tenant_id=tenant.id)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership
    client_result = MagicMock()
    client_result.scalar_one_or_none.return_value = client_obj

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result, client_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/me/organisations/{tenant.id}/clients/{client_obj.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["client_id"] == "abc123"


@pytest.mark.asyncio
async def test_get_client_not_found(_make_app):
    """GET /{org_id}/clients/{uuid} with wrong UUID returns 404."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership
    client_result = MagicMock()
    client_result.scalar_one_or_none.return_value = None

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result, client_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/me/organisations/{tenant.id}/clients/{uuid.uuid4()}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_client_wrong_tenant(_make_app):
    """GET /{org_id}/clients/{uuid} where client belongs to another org returns 404."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    other_tenant_id = uuid.uuid4()
    client_obj = _make_mock_client(tenant_id=other_tenant_id)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership
    client_result = MagicMock()
    client_result.scalar_one_or_none.return_value = client_obj

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result, client_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/me/organisations/{tenant.id}/clients/{client_obj.id}")

    assert response.status_code == 404


# ===========================================================================
# PATCH /api/v1/me/organisations/{org_id}/clients/{client_uuid} - Update
# ===========================================================================


@pytest.mark.asyncio
async def test_update_client_success(_make_app):
    """PATCH /{org_id}/clients/{uuid} updates the client."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    client_obj = _make_mock_client(tenant_id=tenant.id)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership
    client_result = MagicMock()
    client_result.scalar_one_or_none.return_value = client_obj

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result, client_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.patch(
            f"/api/v1/me/organisations/{tenant.id}/clients/{client_obj.id}",
            json={"name": "Updated Client"},
        )

    assert response.status_code == 200
    assert client_obj.name == "Updated Client"


# ===========================================================================
# DELETE /api/v1/me/organisations/{org_id}/clients/{client_uuid} - Delete
# ===========================================================================


@pytest.mark.asyncio
async def test_delete_client_success(_make_app):
    """DELETE /{org_id}/clients/{uuid} returns 204."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    client_obj = _make_mock_client(tenant_id=tenant.id)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership
    client_result = MagicMock()
    client_result.scalar_one_or_none.return_value = client_obj

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result, client_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.delete(f"/api/v1/me/organisations/{tenant.id}/clients/{client_obj.id}")

    assert response.status_code == 204
    mock_db.delete.assert_called_once_with(client_obj)


@pytest.mark.asyncio
async def test_delete_client_not_found(_make_app):
    """DELETE /{org_id}/clients/{uuid} with unknown client returns 404."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership
    client_result = MagicMock()
    client_result.scalar_one_or_none.return_value = None

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result, client_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.delete(f"/api/v1/me/organisations/{tenant.id}/clients/{uuid.uuid4()}")

    assert response.status_code == 404


# ===========================================================================
# POST /{org_id}/clients/{uuid}/rotate-secret
# ===========================================================================


@pytest.mark.asyncio
async def test_rotate_secret_success(_make_app):
    """POST /{org_id}/clients/{uuid}/rotate-secret returns new secret."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    client_obj = _make_mock_client(tenant_id=tenant.id, is_confidential=True)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership
    client_result = MagicMock()
    client_result.scalar_one_or_none.return_value = client_obj

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result, client_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with (
        patch(
            "auth.api.routes.api.me.organisations.clients.generate_client_secret",
            return_value="rotated_secret",
        ),
        patch("auth.api.routes.api.me.organisations.clients._hasher") as mock_hasher,
    ):
        mock_hasher.hash.return_value = "new_argon2_hash"

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                f"/api/v1/me/organisations/{tenant.id}/clients/{client_obj.id}/rotate-secret"
            )

    assert response.status_code == 200
    data = response.json()
    assert data["client_secret"] == "rotated_secret"
    assert data["client_id"] == "abc123"
    assert client_obj.client_secret_hash == "new_argon2_hash"


@pytest.mark.asyncio
async def test_rotate_secret_public_client_fails(_make_app):
    """POST /{org_id}/clients/{uuid}/rotate-secret on public client returns 400."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    client_obj = _make_mock_client(tenant_id=tenant.id, is_confidential=False)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership
    client_result = MagicMock()
    client_result.scalar_one_or_none.return_value = client_obj

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result, client_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            f"/api/v1/me/organisations/{tenant.id}/clients/{client_obj.id}/rotate-secret"
        )

    assert response.status_code == 400
    assert "public" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_unauthenticated_returns_401():
    """Request without auth token returns 401."""
    from auth.main import app as fastapi_app

    fastapi_app.dependency_overrides.pop(get_current_user_bearer, None)

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/me/organisations/{uuid.uuid4()}/clients/")

    assert response.status_code == 401
    fastapi_app.dependency_overrides.clear()
