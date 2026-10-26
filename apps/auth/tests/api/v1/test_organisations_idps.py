# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for /api/v1/organisations/{org_id}/idps endpoints."""

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


def _make_mock_idp(
    idp_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    name: str = "Test OIDC",
    provider_type: str = "oidc",
) -> MagicMock:
    idp = MagicMock()
    idp.id = idp_id or uuid.uuid4()
    idp.tenant_id = tenant_id or uuid.uuid4()
    idp.name = name
    idp.provider_type = MagicMock()
    idp.provider_type.value = provider_type
    # Ensure hasattr check works
    idp.discovery_url = "https://idp.example.com/.well-known/openid-configuration"
    idp.authorization_endpoint = None
    idp.token_endpoint = None
    idp.userinfo_endpoint = None
    idp.jwks_uri = None
    idp.client_id = "idp_client_id"
    idp.client_secret_encrypted = b"encrypted"
    idp.scopes = ["openid", "profile", "email"]
    idp.attribute_mapping = {}
    idp.allowed_domains = None
    idp.is_active = True
    idp.is_default = False
    idp.auto_provision = True
    idp.allow_linking = True
    idp.icon_url = None
    idp.button_text = None
    idp.display_order = 0
    idp.created_at = datetime.now(UTC)
    idp.updated_at = datetime.now(UTC)
    return idp


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
# GET /api/v1/organisations/{org_id}/idps/ - List
# ===========================================================================


@pytest.mark.asyncio
async def test_list_idps_success(_make_app):
    """GET /{org_id}/idps/ returns paginated list."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    idp = _make_mock_idp(tenant_id=tenant.id)

    mock_db = AsyncMock()

    # require_org_membership
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
    select_scalars.all.return_value = [idp]
    select_result.scalars.return_value = select_scalars

    mock_db.execute = AsyncMock(
        side_effect=[tenant_result, member_result, count_result, select_result]
    )

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/organisations/{tenant.id}/idps/")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "Test OIDC"
    assert data["items"][0]["provider_type"] == "oidc"


@pytest.mark.asyncio
async def test_list_idps_forbidden(_make_app):
    """GET /{org_id}/idps/ without idp:read scope returns 403."""
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
        response = await ac.get(f"/api/v1/organisations/{tenant.id}/idps/")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_idps_org_not_found(_make_app):
    """GET /{org_id}/idps/ with unknown org returns 404."""
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
        response = await ac.get(f"/api/v1/organisations/{uuid.uuid4()}/idps/")

    assert response.status_code == 404


# ===========================================================================
# POST /api/v1/organisations/{org_id}/idps/ - Create
# ===========================================================================


@pytest.mark.asyncio
async def test_create_idp_success(_make_app):
    """POST /{org_id}/idps/ creates IdP and returns 201."""
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
            if hasattr(obj, "provider_type") and not hasattr(obj, "_id_set"):
                obj.id = uuid.uuid4()
                obj.created_at = now
                obj.updated_at = now
                obj._id_set = True

    mock_db.flush = AsyncMock(side_effect=mock_flush)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.organisations.idps.encrypt_value", return_value=b"enc"):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                f"/api/v1/organisations/{tenant.id}/idps/",
                json={
                    "name": "Google IdP",
                    "provider_type": "google",
                    "client_id": "google_client_id",
                    "client_secret": "google_secret",
                },
            )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Google IdP"
    assert data["provider_type"] == "google"
    assert data["client_id"] == "google_client_id"


@pytest.mark.asyncio
async def test_create_idp_invalid_type(_make_app):
    """POST /{org_id}/idps/ with invalid provider_type returns 400."""
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

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            f"/api/v1/organisations/{tenant.id}/idps/",
            json={
                "name": "Bad IdP",
                "provider_type": "invalid_type",
                "client_id": "some_id",
            },
        )

    assert response.status_code == 400
    assert "invalid provider_type" in response.json()["detail"].lower()


# ===========================================================================
# PATCH /api/v1/organisations/{org_id}/idps/{idp_id} - Update
# ===========================================================================


@pytest.mark.asyncio
async def test_update_idp_success(_make_app):
    """PATCH /{org_id}/idps/{idp_id} updates the IdP."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    idp = _make_mock_idp(tenant_id=tenant.id)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership
    idp_result = MagicMock()
    idp_result.scalar_one_or_none.return_value = idp

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result, idp_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.patch(
            f"/api/v1/organisations/{tenant.id}/idps/{idp.id}",
            json={"name": "Updated OIDC"},
        )

    assert response.status_code == 200
    assert idp.name == "Updated OIDC"


@pytest.mark.asyncio
async def test_update_idp_not_found(_make_app):
    """PATCH /{org_id}/idps/{idp_id} with unknown IdP returns 404."""
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
    idp_result = MagicMock()
    idp_result.scalar_one_or_none.return_value = None

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result, idp_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.patch(
            f"/api/v1/organisations/{tenant.id}/idps/{uuid.uuid4()}",
            json={"name": "Nope"},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_idp_wrong_tenant(_make_app):
    """PATCH /{org_id}/idps/{idp_id} where IdP belongs to another org returns 404."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    other_tenant_id = uuid.uuid4()
    idp = _make_mock_idp(tenant_id=other_tenant_id)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership
    idp_result = MagicMock()
    idp_result.scalar_one_or_none.return_value = idp

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result, idp_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.patch(
            f"/api/v1/organisations/{tenant.id}/idps/{idp.id}",
            json={"name": "Nope"},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_idp_with_secret(_make_app):
    """PATCH /{org_id}/idps/{idp_id} with client_secret encrypts it."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    idp = _make_mock_idp(tenant_id=tenant.id)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership
    idp_result = MagicMock()
    idp_result.scalar_one_or_none.return_value = idp

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result, idp_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch(
        "auth.api.routes.api.organisations.idps.encrypt_value",
        return_value=b"new_encrypted",
    ) as mock_encrypt:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.patch(
                f"/api/v1/organisations/{tenant.id}/idps/{idp.id}",
                json={"client_secret": "new_secret"},
            )

    assert response.status_code == 200
    mock_encrypt.assert_called_once_with("new_secret")
    assert idp.client_secret_encrypted == b"new_encrypted"


# ===========================================================================
# DELETE /api/v1/organisations/{org_id}/idps/{idp_id} - Delete
# ===========================================================================


@pytest.mark.asyncio
async def test_delete_idp_success(_make_app):
    """DELETE /{org_id}/idps/{idp_id} returns 204."""
    from auth.api.deps import get_db

    user = _make_mock_user()
    app, user = _make_app(user)
    tenant = _make_mock_tenant()
    membership = _make_mock_membership(tenant.id, user.id)
    idp = _make_mock_idp(tenant_id=tenant.id)

    mock_db = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = tenant
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = membership
    idp_result = MagicMock()
    idp_result.scalar_one_or_none.return_value = idp

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result, idp_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.delete(f"/api/v1/organisations/{tenant.id}/idps/{idp.id}")

    assert response.status_code == 204
    mock_db.delete.assert_called_once_with(idp)


@pytest.mark.asyncio
async def test_delete_idp_not_found(_make_app):
    """DELETE /{org_id}/idps/{idp_id} with unknown IdP returns 404."""
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
    idp_result = MagicMock()
    idp_result.scalar_one_or_none.return_value = None

    mock_db.execute = AsyncMock(side_effect=[tenant_result, member_result, idp_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.delete(f"/api/v1/organisations/{tenant.id}/idps/{uuid.uuid4()}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_unauthenticated_returns_401():
    """Request without auth token returns 401."""
    from auth.main import app as fastapi_app

    fastapi_app.dependency_overrides.pop(get_current_user_bearer, None)

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/organisations/{uuid.uuid4()}/idps/")

    assert response.status_code == 401
    fastapi_app.dependency_overrides.clear()
