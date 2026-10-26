# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for /api/v1/scopes admin endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.api.routes.api.deps import get_current_user_bearer
from httpx import ASGITransport, AsyncClient


def _make_mock_scope(
    scope_id: uuid.UUID | None = None,
    name: str = "users:read",
    description: str = "View users",
    resource: str = "users",
    action: str = "read",
    category: str = "admin",
    is_system: bool = False,
    is_active: bool = True,
) -> MagicMock:
    """Build a mock Scope object."""
    scope = MagicMock()
    scope.id = scope_id or uuid.uuid4()
    scope.name = name
    scope.description = description
    scope.resource = resource
    scope.action = action
    scope.category = category
    scope.is_system = is_system
    scope.is_active = is_active
    scope.created_at = datetime.now(UTC)
    scope.updated_at = datetime.now(UTC)
    return scope


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
# GET /api/v1/scopes/ - List
# ===========================================================================


@pytest.mark.asyncio
async def test_list_scopes_success(_make_app):
    """GET /api/v1/scopes/ returns paginated list."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["scopes:read"])
    scope = _make_mock_scope()

    mock_db = AsyncMock()
    count_result = MagicMock()
    count_result.scalar.return_value = 1

    select_result = MagicMock()
    select_scalars = MagicMock()
    select_scalars.all.return_value = [scope]
    select_result.scalars.return_value = select_scalars

    mock_db.execute = AsyncMock(side_effect=[count_result, select_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/v1/scopes/")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "users:read"
    assert data["items"][0]["resource"] == "users"
    assert data["items"][0]["action"] == "read"


@pytest.mark.asyncio
async def test_list_scopes_forbidden(_make_app):
    """GET /api/v1/scopes/ without scopes:read scope returns 403."""
    from auth.api.deps import get_db

    app, _, _ = _make_app([])
    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=False):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/v1/scopes/")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_scopes_unauthenticated():
    """GET /api/v1/scopes/ without token returns 401."""
    from auth.main import app as fastapi_app

    fastapi_app.dependency_overrides.pop(get_current_user_bearer, None)

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/scopes/")

    assert response.status_code == 401
    fastapi_app.dependency_overrides.clear()


# ===========================================================================
# GET /api/v1/scopes/{scope_id} - Get one
# ===========================================================================


@pytest.mark.asyncio
async def test_get_scope_success(_make_app):
    """GET /api/v1/scopes/{id} returns scope detail."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["scopes:read"])
    scope = _make_mock_scope()

    mock_db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = scope
    mock_db.execute = AsyncMock(return_value=result)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/scopes/{scope.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "users:read"
    assert data["resource"] == "users"
    assert data["action"] == "read"


@pytest.mark.asyncio
async def test_get_scope_not_found(_make_app):
    """GET /api/v1/scopes/{id} with unknown ID returns 404."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["scopes:read"])

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
            response = await ac.get(f"/api/v1/scopes/{uuid.uuid4()}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_scope_forbidden(_make_app):
    """GET /api/v1/scopes/{id} without scopes:read returns 403."""
    from auth.api.deps import get_db

    app, _, _ = _make_app([])
    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=False):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/scopes/{uuid.uuid4()}")

    assert response.status_code == 403


# ===========================================================================
# POST /api/v1/scopes/ - Create
# ===========================================================================


@pytest.mark.asyncio
async def test_create_scope_success(_make_app):
    """POST /api/v1/scopes/ creates scope and returns 201."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["scopes:write"])
    scope_id = uuid.uuid4()

    mock_db = AsyncMock()
    mock_db.add = MagicMock()

    # Uniqueness check - no existing
    name_check = MagicMock()
    name_check.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=name_check)

    added_objects: list = []

    def capture_add(obj):
        added_objects.append(obj)

    mock_db.add = MagicMock(side_effect=capture_add)

    now = datetime.now(UTC)

    async def mock_refresh(obj, *args, **kwargs):
        obj.id = scope_id
        obj.created_at = now
        obj.updated_at = now
        obj.is_system = False
        obj.is_active = True

    mock_db.refresh = AsyncMock(side_effect=mock_refresh)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/scopes/",
                json={
                    "name": "custom:action",
                    "description": "A custom scope",
                    "resource": "custom",
                    "action": "action",
                    "category": "custom",
                },
            )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "custom:action"
    assert data["resource"] == "custom"
    assert data["action"] == "action"
    assert data["category"] == "custom"
    assert data["is_system"] is False


@pytest.mark.asyncio
async def test_create_scope_duplicate_name(_make_app):
    """POST /api/v1/scopes/ with duplicate name returns 409."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["scopes:write"])

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
                "/api/v1/scopes/",
                json={
                    "name": "existing:scope",
                    "resource": "existing",
                    "action": "scope",
                },
            )

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_scope_forbidden(_make_app):
    """POST /api/v1/scopes/ without scopes:write returns 403."""
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
                "/api/v1/scopes/",
                json={
                    "name": "nope:scope",
                    "resource": "nope",
                    "action": "scope",
                },
            )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_scope_validation_error(_make_app):
    """POST /api/v1/scopes/ with missing required fields returns 422."""
    app, _, _ = _make_app(["scopes:write"])

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/scopes/",
                json={"name": "incomplete"},
            )

    assert response.status_code == 422


# ===========================================================================
# PATCH /api/v1/scopes/{scope_id} - Update
# ===========================================================================


@pytest.mark.asyncio
async def test_update_scope_success(_make_app):
    """PATCH /api/v1/scopes/{id} updates scope fields."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["scopes:write"])
    scope = _make_mock_scope()

    mock_db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = scope
    mock_db.execute = AsyncMock(return_value=result)

    async def mock_refresh(obj, *args, **kwargs):
        pass

    mock_db.refresh = AsyncMock(side_effect=mock_refresh)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.patch(
                f"/api/v1/scopes/{scope.id}",
                json={"description": "Updated description"},
            )

    assert response.status_code == 200
    assert scope.description == "Updated description"


@pytest.mark.asyncio
async def test_update_scope_not_found(_make_app):
    """PATCH /api/v1/scopes/{id} with unknown ID returns 404."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["scopes:write"])

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
                f"/api/v1/scopes/{uuid.uuid4()}",
                json={"description": "nope"},
            )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_scope_duplicate_name(_make_app):
    """PATCH /api/v1/scopes/{id} with duplicate name returns 409."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["scopes:write"])
    scope = _make_mock_scope(name="original:scope")

    mock_db = AsyncMock()

    load_result = MagicMock()
    load_result.scalar_one_or_none.return_value = scope

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
                f"/api/v1/scopes/{scope.id}",
                json={"name": "taken:name"},
            )

    assert response.status_code == 409


# ===========================================================================
# DELETE /api/v1/scopes/{scope_id} - Delete
# ===========================================================================


@pytest.mark.asyncio
async def test_delete_scope_success(_make_app):
    """DELETE /api/v1/scopes/{id} returns 204."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["scopes:delete"])
    scope = _make_mock_scope(is_system=False)

    mock_db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = scope
    mock_db.execute = AsyncMock(return_value=result)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(f"/api/v1/scopes/{scope.id}")

    assert response.status_code == 204
    mock_db.delete.assert_called_once_with(scope)
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_delete_scope_system_forbidden(_make_app):
    """DELETE /api/v1/scopes/{id} on system scope returns 400."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["scopes:delete"])
    scope = _make_mock_scope(is_system=True)

    mock_db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = scope
    mock_db.execute = AsyncMock(return_value=result)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(f"/api/v1/scopes/{scope.id}")

    assert response.status_code == 400
    assert "system" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_scope_not_found(_make_app):
    """DELETE /api/v1/scopes/{id} with unknown ID returns 404."""
    from auth.api.deps import get_db

    app, admin_user, _ = _make_app(["scopes:delete"])

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
            response = await ac.delete(f"/api/v1/scopes/{uuid.uuid4()}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_scope_forbidden(_make_app):
    """DELETE /api/v1/scopes/{id} without scopes:delete returns 403."""
    from auth.api.deps import get_db

    app, _, _ = _make_app([])
    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=False):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(f"/api/v1/scopes/{uuid.uuid4()}")

    assert response.status_code == 403
