# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for /api/v1/roles admin endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.api.routes.api.deps import get_current_user_bearer
from httpx import ASGITransport, AsyncClient


def _make_mock_scope(
    scope_id: uuid.UUID | None = None,
    name: str = "users:read",
    is_active: bool = True,
) -> MagicMock:
    """Build a mock Scope object."""
    scope = MagicMock()
    scope.id = scope_id or uuid.uuid4()
    scope.name = name
    scope.is_active = is_active
    return scope


def _make_mock_role_scope(scope: MagicMock) -> MagicMock:
    """Build a mock RoleScope object."""
    rs = MagicMock()
    rs.scope = scope
    return rs


def _make_mock_role(
    role_id: uuid.UUID | None = None,
    name: str = "test_role",
    description: str = "A test role",
    is_system: bool = False,
    scope_names: list[str] | None = None,
) -> MagicMock:
    """Build a mock Role with role_scopes."""
    role = MagicMock()
    role.id = role_id or uuid.uuid4()
    role.name = name
    role.description = description
    role.is_system = is_system
    role.created_at = datetime.now(UTC)
    role.updated_at = datetime.now(UTC)

    # Build role_scopes from scope_names
    if scope_names is None:
        scope_names = ["users:read", "users:write"]
    role_scopes = []
    for sn in scope_names:
        scope = _make_mock_scope(name=sn)
        role_scopes.append(_make_mock_role_scope(scope))
    role.role_scopes = role_scopes

    def get_all_scope_names():
        return [rs.scope.name for rs in role.role_scopes if rs.scope and rs.scope.is_active]

    role.get_all_scope_names = MagicMock(side_effect=get_all_scope_names)

    return role


@pytest.fixture
def _make_app():
    """Return a factory that yields (app, user) with the specified scopes."""
    from auth.main import app as fastapi_app

    created = []

    def factory(scopes: list[str], user: MagicMock | None = None):
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
        return fastapi_app, user_, scopes

    yield factory

    for a in created:
        a.dependency_overrides.clear()


# ===========================================================================
# GET /api/v1/roles/ - List
# ===========================================================================


@pytest.mark.asyncio
async def test_list_roles_success(_make_app):
    """GET /api/v1/roles/ returns paginated list."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["roles:read"])
    role = _make_mock_role()

    mock_db = AsyncMock()
    count_result = MagicMock()
    count_result.scalar.return_value = 1

    select_result = MagicMock()
    select_scalars = MagicMock()
    select_scalars.all.return_value = [role]
    select_result.scalars.return_value = select_scalars

    mock_db.execute = AsyncMock(side_effect=[count_result, select_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/v1/roles/")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "test_role"
    assert "users:read" in data["items"][0]["scopes"]
    assert "users:write" in data["items"][0]["scopes"]


@pytest.mark.asyncio
async def test_list_roles_forbidden(_make_app):
    """GET /api/v1/roles/ without roles:read scope returns 403."""
    from auth.api.deps import get_db

    app, _, _ = _make_app([])
    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=False):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/v1/roles/")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_roles_unauthenticated():
    """GET /api/v1/roles/ without token returns 401."""
    from auth.main import app as fastapi_app

    fastapi_app.dependency_overrides.pop(get_current_user_bearer, None)

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/roles/")

    assert response.status_code == 401
    fastapi_app.dependency_overrides.clear()


# ===========================================================================
# POST /api/v1/roles/ - Create
# ===========================================================================


@pytest.mark.asyncio
async def test_create_role_success(_make_app):
    """POST /api/v1/roles/ creates role and returns 201."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["roles:write"])
    role_id = uuid.uuid4()

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    created_role = _make_mock_role(role_id=role_id, name="new_role", scope_names=[])

    with (
        patch("auth.api.routes.api.deps.token_has_scope", return_value=True),
        patch(
            "auth.api.routes.api.roles._role_service.create_role",
            new_callable=AsyncMock,
            return_value=created_role,
        ),
        patch(
            "auth.api.routes.api.roles._role_service.get_by_id",
            new_callable=AsyncMock,
            return_value=created_role,
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/roles/",
                json={"name": "new_role", "description": "A new role"},
            )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "new_role"
    assert data["is_system"] is False


@pytest.mark.asyncio
async def test_create_role_duplicate_name(_make_app):
    """POST /api/v1/roles/ with duplicate name returns 409."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["roles:write"])

    mock_db = AsyncMock()
    name_check = MagicMock()
    name_check.scalar_one_or_none.return_value = MagicMock()  # exists
    mock_db.execute = AsyncMock(return_value=name_check)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/roles/",
                json={"name": "existing_role", "description": "dup"},
            )

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_role_forbidden(_make_app):
    """POST /api/v1/roles/ without roles:write returns 403."""
    from auth.api.deps import get_db

    app, _, _ = _make_app([])
    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=False):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/roles/",
                json={"name": "nope", "description": "no"},
            )

    assert response.status_code == 403


# ===========================================================================
# GET /api/v1/roles/{role_id} - Get one
# ===========================================================================


@pytest.mark.asyncio
async def test_get_role_success(_make_app):
    """GET /api/v1/roles/{id} returns role with scopes."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["roles:read"])
    role = _make_mock_role(scope_names=["users:read", "sessions:revoke"])

    mock_db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = role
    mock_db.execute = AsyncMock(return_value=result)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/roles/{role.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "test_role"
    assert "users:read" in data["scopes"]
    assert "sessions:revoke" in data["scopes"]


@pytest.mark.asyncio
async def test_get_role_not_found(_make_app):
    """GET /api/v1/roles/{id} with unknown ID returns 404."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["roles:read"])

    mock_db = AsyncMock()
    no_result = MagicMock()
    no_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=no_result)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/roles/{uuid.uuid4()}")

    assert response.status_code == 404


# ===========================================================================
# PATCH /api/v1/roles/{role_id} - Update
# ===========================================================================


@pytest.mark.asyncio
async def test_update_role_success(_make_app):
    """PATCH /api/v1/roles/{id} updates role fields."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["roles:write"])
    role = _make_mock_role()
    updated_role = _make_mock_role(role_id=role.id, name="updated_role")
    updated_role.description = "Updated description"

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    # service.get_by_id is called twice: once for the 404 check, once for the reload after update
    get_by_id_mock = AsyncMock(side_effect=[role, updated_role])

    with (
        patch("auth.api.routes.api.deps.token_has_scope", return_value=True),
        patch("auth.api.routes.api.roles._role_service.get_by_id", get_by_id_mock),
        patch(
            "auth.api.routes.api.roles._role_service.update_role",
            new_callable=AsyncMock,
            return_value=updated_role,
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.patch(
                f"/api/v1/roles/{role.id}",
                json={"name": "updated_role", "description": "Updated description"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "updated_role"


@pytest.mark.asyncio
async def test_update_role_not_found(_make_app):
    """PATCH /api/v1/roles/{id} with unknown ID returns 404."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["roles:write"])

    mock_db = AsyncMock()
    no_result = MagicMock()
    no_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=no_result)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.patch(
                f"/api/v1/roles/{uuid.uuid4()}",
                json={"name": "nope"},
            )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_role_duplicate_name(_make_app):
    """PATCH /api/v1/roles/{id} with duplicate name returns 409."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["roles:write"])
    role = _make_mock_role(name="original")

    mock_db = AsyncMock()

    load_result = MagicMock()
    load_result.scalar_one_or_none.return_value = role

    dup_result = MagicMock()
    dup_result.scalar_one_or_none.return_value = MagicMock()  # exists

    mock_db.execute = AsyncMock(side_effect=[load_result, dup_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.patch(
                f"/api/v1/roles/{role.id}",
                json={"name": "taken_name"},
            )

    assert response.status_code == 409


# ===========================================================================
# DELETE /api/v1/roles/{role_id} - Delete
# ===========================================================================


@pytest.mark.asyncio
async def test_delete_role_success(_make_app):
    """DELETE /api/v1/roles/{id} returns 204."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["roles:delete"])
    role = _make_mock_role(is_system=False)

    mock_db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = role
    mock_db.execute = AsyncMock(return_value=result)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(f"/api/v1/roles/{role.id}")

    assert response.status_code == 204
    mock_db.delete.assert_called_once_with(role)
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_delete_role_system_forbidden(_make_app):
    """DELETE /api/v1/roles/{id} on system role returns 400."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["roles:delete"])
    role = _make_mock_role(is_system=True)

    mock_db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = role
    mock_db.execute = AsyncMock(return_value=result)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(f"/api/v1/roles/{role.id}")

    assert response.status_code == 400
    assert "system" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_role_not_found(_make_app):
    """DELETE /api/v1/roles/{id} with unknown ID returns 404."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["roles:delete"])

    mock_db = AsyncMock()
    no_result = MagicMock()
    no_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=no_result)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(f"/api/v1/roles/{uuid.uuid4()}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_role_forbidden(_make_app):
    """DELETE /api/v1/roles/{id} without roles:delete returns 403."""
    from auth.api.deps import get_db

    app, _, _ = _make_app([])
    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=False):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(f"/api/v1/roles/{uuid.uuid4()}")

    assert response.status_code == 403


# ===========================================================================
# POST /api/v1/roles/seed - Seed default roles
# ===========================================================================


@pytest.mark.asyncio
async def test_seed_roles_success(_make_app):
    """POST /api/v1/roles/seed returns 200 with created roles."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["roles:write"])

    mock_db = AsyncMock()
    mock_db.add = MagicMock()

    # Every role existence check returns None (not found)
    no_result = MagicMock()
    no_result.scalar_one_or_none.return_value = None

    async def mock_execute(stmt, *args, **kwargs):
        return no_result

    mock_db.execute = AsyncMock(side_effect=mock_execute)

    # Override flush to assign IDs to added roles
    def capture_add(obj):
        if hasattr(obj, "name") and hasattr(obj, "is_system"):
            obj.id = uuid.uuid4()

    mock_db.add = MagicMock(side_effect=capture_add)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post("/api/v1/roles/seed")

    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "created_roles" in data


@pytest.mark.asyncio
async def test_seed_roles_forbidden(_make_app):
    """POST /api/v1/roles/seed without roles:write returns 403."""
    from auth.api.deps import get_db

    app, _, _ = _make_app([])
    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=False):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post("/api/v1/roles/seed")

    assert response.status_code == 403


# ===========================================================================
# POST /api/v1/roles/{role_id}/users - Assign role to user
# ===========================================================================


@pytest.mark.asyncio
async def test_assign_role_to_user_success(_make_app):
    """POST /api/v1/roles/{role_id}/users returns 201."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["roles:assign"])
    role = _make_mock_role()
    target_user = MagicMock()
    target_user.id = uuid.uuid4()

    mock_db = AsyncMock()
    mock_db.add = MagicMock()

    role_result = MagicMock()
    role_result.scalar_one_or_none.return_value = role

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = target_user

    no_existing = MagicMock()
    no_existing.scalar_one_or_none.return_value = None

    mock_db.execute = AsyncMock(side_effect=[role_result, user_result, no_existing])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                f"/api/v1/roles/{role.id}/users",
                json={"user_id": str(target_user.id)},
            )

    assert response.status_code == 201
    assert "message" in response.json()


@pytest.mark.asyncio
async def test_assign_role_to_user_role_not_found(_make_app):
    """POST /api/v1/roles/{role_id}/users with unknown role returns 404."""
    from auth.api.deps import get_db

    app, _, _ = _make_app(["roles:assign"])

    mock_db = AsyncMock()
    no_result = MagicMock()
    no_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=no_result)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                f"/api/v1/roles/{uuid.uuid4()}/users",
                json={"user_id": str(uuid.uuid4())},
            )

    assert response.status_code == 404
    assert "role" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_assign_role_to_user_conflict(_make_app):
    """POST /api/v1/roles/{role_id}/users with existing assignment returns 409."""
    from auth.api.deps import get_db

    app, _, _ = _make_app(["roles:assign"])
    role = _make_mock_role()
    target_user = MagicMock()
    target_user.id = uuid.uuid4()

    mock_db = AsyncMock()

    role_result = MagicMock()
    role_result.scalar_one_or_none.return_value = role

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = target_user

    existing_result = MagicMock()
    existing_result.scalar_one_or_none.return_value = MagicMock()

    mock_db.execute = AsyncMock(side_effect=[role_result, user_result, existing_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                f"/api/v1/roles/{role.id}/users",
                json={"user_id": str(target_user.id)},
            )

    assert response.status_code == 409


# ===========================================================================
# DELETE /api/v1/roles/{role_id}/users/{user_id} - Remove role from user
# ===========================================================================


@pytest.mark.asyncio
async def test_remove_role_from_user_success(_make_app):
    """DELETE /api/v1/roles/{role_id}/users/{user_id} returns 204."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["roles:assign"])
    role_id = uuid.uuid4()
    target_user_id = uuid.uuid4()
    user_role = MagicMock()

    mock_db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = user_role
    mock_db.execute = AsyncMock(return_value=result)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(
                f"/api/v1/roles/{role_id}/users/{target_user_id}",
            )

    assert response.status_code == 204
    mock_db.delete.assert_called_once_with(user_role)


@pytest.mark.asyncio
async def test_remove_role_from_user_not_found(_make_app):
    """DELETE /api/v1/roles/{role_id}/users/{user_id} with no assignment returns 404."""
    from auth.api.deps import get_db

    app, _, _ = _make_app(["roles:assign"])

    mock_db = AsyncMock()
    no_result = MagicMock()
    no_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=no_result)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(
                f"/api/v1/roles/{uuid.uuid4()}/users/{uuid.uuid4()}",
            )

    assert response.status_code == 404


# ===========================================================================
# POST /api/v1/roles/{role_id}/scopes/{scope_id} - Assign scope to role
# ===========================================================================


@pytest.mark.asyncio
async def test_assign_scope_to_role_success(_make_app):
    """POST /api/v1/roles/{role_id}/scopes/{scope_id} returns 201."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["roles:write"])
    role = _make_mock_role()
    scope = _make_mock_scope(name="sessions:read")

    mock_db = AsyncMock()
    mock_db.add = MagicMock()

    role_result = MagicMock()
    role_result.scalar_one_or_none.return_value = role

    scope_result = MagicMock()
    scope_result.scalar_one_or_none.return_value = scope

    no_existing = MagicMock()
    no_existing.scalar_one_or_none.return_value = None

    mock_db.execute = AsyncMock(side_effect=[role_result, scope_result, no_existing])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                f"/api/v1/roles/{role.id}/scopes/{scope.id}",
            )

    assert response.status_code == 201
    assert "message" in response.json()


@pytest.mark.asyncio
async def test_assign_scope_to_role_role_not_found(_make_app):
    """POST /api/v1/roles/{role_id}/scopes/{scope_id} with unknown role returns 404."""
    from auth.api.deps import get_db

    app, _, _ = _make_app(["roles:write"])

    mock_db = AsyncMock()
    no_result = MagicMock()
    no_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=no_result)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                f"/api/v1/roles/{uuid.uuid4()}/scopes/{uuid.uuid4()}",
            )

    assert response.status_code == 404
    assert "role" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_assign_scope_to_role_conflict(_make_app):
    """POST /api/v1/roles/{role_id}/scopes/{scope_id} with existing returns 409."""
    from auth.api.deps import get_db

    app, _, _ = _make_app(["roles:write"])
    role = _make_mock_role()
    scope = _make_mock_scope()

    mock_db = AsyncMock()

    role_result = MagicMock()
    role_result.scalar_one_or_none.return_value = role

    scope_result = MagicMock()
    scope_result.scalar_one_or_none.return_value = scope

    existing_result = MagicMock()
    existing_result.scalar_one_or_none.return_value = MagicMock()

    mock_db.execute = AsyncMock(side_effect=[role_result, scope_result, existing_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                f"/api/v1/roles/{role.id}/scopes/{scope.id}",
            )

    assert response.status_code == 409


# ===========================================================================
# DELETE /api/v1/roles/{role_id}/scopes/{scope_id} - Remove scope from role
# ===========================================================================


@pytest.mark.asyncio
async def test_remove_scope_from_role_success(_make_app):
    """DELETE /api/v1/roles/{role_id}/scopes/{scope_id} returns 204."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["roles:write"])
    role_scope = MagicMock()

    mock_db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = role_scope
    mock_db.execute = AsyncMock(return_value=result)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(
                f"/api/v1/roles/{uuid.uuid4()}/scopes/{uuid.uuid4()}",
            )

    assert response.status_code == 204
    mock_db.delete.assert_called_once_with(role_scope)


@pytest.mark.asyncio
async def test_remove_scope_from_role_not_found(_make_app):
    """DELETE /api/v1/roles/{role_id}/scopes/{scope_id} with no assignment returns 404."""
    from auth.api.deps import get_db

    app, _, _ = _make_app(["roles:write"])

    mock_db = AsyncMock()
    no_result = MagicMock()
    no_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=no_result)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(
                f"/api/v1/roles/{uuid.uuid4()}/scopes/{uuid.uuid4()}",
            )

    assert response.status_code == 404
