# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for /api/v1/users admin endpoints."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.api.routes.api.deps import get_current_user_bearer
from auth.main import app as fastapi_app
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def _make_app():
    """Create app with admin user having given scopes."""

    def factory(scopes: list[str]):
        admin_user = MagicMock()
        admin_user.id = uuid.uuid4()
        admin_user.is_active = True

        async def override_auth():
            return admin_user

        fastapi_app.dependency_overrides[get_current_user_bearer] = override_auth
        return fastapi_app, admin_user, scopes

    yield factory
    fastapi_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_users_unauthenticated():
    """GET /api/v1/users/ without auth returns 401."""
    fastapi_app.dependency_overrides.clear()
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/users/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_users_forbidden(_make_app):
    """GET /api/v1/users/ without users:read returns 403."""
    app, _, _ = _make_app(["clients:read"])

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/users/")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_users_success(_make_app):
    """GET /api/v1/users/ returns paginated users."""
    app, _, _ = _make_app(["users:read"])

    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()
    mock_user.is_active = True
    mock_user.registration_source = "direct"
    mock_user.created_at = MagicMock()
    mock_user.created_at.isoformat.return_value = "2024-01-01T00:00:00"
    mock_user.updated_at = MagicMock()
    mock_user.updated_at.isoformat.return_value = "2024-01-01T00:00:00"
    email = MagicMock()
    email.email = "user@example.com"
    email.is_primary = True
    mock_user.emails = [email]
    mock_user.profile = None

    mock_db = AsyncMock()
    count_result = MagicMock()
    count_result.scalar.return_value = 1
    list_result = MagicMock()
    scalars = MagicMock()
    unique = MagicMock()
    unique.all.return_value = [mock_user]
    scalars.unique.return_value = unique
    list_result.scalars.return_value = scalars
    mock_db.execute = AsyncMock(side_effect=[count_result, list_result])

    from auth.api.deps import get_db

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/v1/users/")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1


# ===========================================================================
# DELETE /api/v1/users/{user_id}/sessions - Revoke all sessions
# ===========================================================================


@pytest.mark.asyncio
async def test_revoke_user_sessions_success(_make_app):
    """DELETE /api/v1/users/{user_id}/sessions returns 204."""
    app, _, _ = _make_app(["users:write"])

    target_user_id = uuid.uuid4()

    mock_user = MagicMock()
    mock_user.id = target_user_id
    mock_user.is_active = True
    email = MagicMock()
    email.email = "user@example.com"
    email.is_primary = True
    mock_user.emails = [email]

    mock_db = AsyncMock()
    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = mock_user
    mock_db.execute = AsyncMock(return_value=user_result)

    from auth.api.deps import get_db

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with (
        patch("auth.api.routes.api.deps.token_has_scope", return_value=True),
        patch(
            "auth.api.routes.api.users._session_service.revoke_all_user_sessions",
            new_callable=AsyncMock,
            return_value=3,
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(f"/api/v1/users/{target_user_id}/sessions")

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_revoke_user_sessions_not_found(_make_app):
    """DELETE /api/v1/users/{user_id}/sessions with unknown user returns 404."""
    app, _, _ = _make_app(["users:write"])

    mock_db = AsyncMock()
    no_result = MagicMock()
    no_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=no_result)

    from auth.api.deps import get_db

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(f"/api/v1/users/{uuid.uuid4()}/sessions")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_revoke_user_sessions_forbidden(_make_app):
    """DELETE /api/v1/users/{user_id}/sessions without users:write returns 403."""
    app, _, _ = _make_app([])

    mock_db = AsyncMock()

    from auth.api.deps import get_db

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=False):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(f"/api/v1/users/{uuid.uuid4()}/sessions")

    assert response.status_code == 403


# ===========================================================================
# PATCH /api/v1/users/{user_id} - profile fields propagation
# ===========================================================================


def _make_user_row(
    user_id: uuid.UUID,
    *,
    name: str | None = None,
    given_name: str | None = None,
    family_name: str | None = None,
    nickname: str | None = None,
    with_profile: bool = True,
):
    """Build a MagicMock resembling a loaded User row."""
    user_obj = MagicMock()
    user_obj.id = user_id
    user_obj.is_active = True
    user_obj.registration_source = "direct"
    user_obj.created_at = MagicMock()
    user_obj.created_at.isoformat.return_value = "2024-01-01T00:00:00"
    user_obj.updated_at = MagicMock()
    user_obj.updated_at.isoformat.return_value = "2024-01-01T00:00:00"

    email = MagicMock()
    email.email = "user@example.com"
    email.is_primary = True
    user_obj.emails = [email]

    if with_profile:
        profile = MagicMock()
        profile.name = name
        profile.given_name = given_name
        profile.family_name = family_name
        profile.nickname = nickname
        user_obj.profile = profile
    else:
        user_obj.profile = None

    return user_obj


@pytest.mark.asyncio
async def test_update_user_profile_fields_success(_make_app):
    """PATCH /api/v1/users/{id} with profile fields updates the profile."""
    app, _, _ = _make_app(["users:write"])

    target_user_id = uuid.uuid4()
    # First load: no profile yet; reload after update: reflects new values.
    initial_user = _make_user_row(target_user_id, with_profile=False)
    reloaded_user = _make_user_row(
        target_user_id,
        name="Alice Doe",
        given_name="Alice",
        family_name="Doe",
        nickname="ali",
    )

    mock_db = AsyncMock()
    initial_result = MagicMock()
    initial_result.scalar_one_or_none.return_value = initial_user
    reloaded_result = MagicMock()
    reloaded_result.scalar_one_or_none.return_value = reloaded_user
    mock_db.execute = AsyncMock(side_effect=[initial_result, reloaded_result])

    from auth.api.deps import get_db

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    update_profile_mock = AsyncMock()

    with (
        patch("auth.api.routes.api.deps.token_has_scope", return_value=True),
        patch(
            "auth.api.routes.api.users._profile_service.update_profile",
            update_profile_mock,
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.patch(
                f"/api/v1/users/{target_user_id}",
                json={
                    "given_name": "Alice",
                    "family_name": "Doe",
                    "nickname": "ali",
                    "name": "Alice Doe",
                },
            )

    assert response.status_code == 200
    body = response.json()
    assert body["given_name"] == "Alice"
    assert body["family_name"] == "Doe"
    assert body["nickname"] == "ali"
    assert body["name"] == "Alice Doe"

    # ProfileService was called exactly once with all four profile fields.
    update_profile_mock.assert_awaited_once()
    args, kwargs = update_profile_mock.await_args
    assert args[1] == str(target_user_id)
    profile_data = args[2]
    assert profile_data.given_name == "Alice"
    assert profile_data.family_name == "Doe"
    assert profile_data.nickname == "ali"
    assert profile_data.name == "Alice Doe"


@pytest.mark.asyncio
async def test_update_user_is_active_only_no_profile_call(_make_app):
    """PATCH with only is_active does not invoke ProfileService."""
    app, _, _ = _make_app(["users:write"])

    target_user_id = uuid.uuid4()
    user_row = _make_user_row(target_user_id, with_profile=False)

    mock_db = AsyncMock()
    first = MagicMock()
    first.scalar_one_or_none.return_value = user_row
    second = MagicMock()
    second.scalar_one_or_none.return_value = user_row
    mock_db.execute = AsyncMock(side_effect=[first, second])

    from auth.api.deps import get_db

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    update_profile_mock = AsyncMock()

    with (
        patch("auth.api.routes.api.deps.token_has_scope", return_value=True),
        patch(
            "auth.api.routes.api.users._profile_service.update_profile",
            update_profile_mock,
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.patch(
                f"/api/v1/users/{target_user_id}",
                json={"is_active": False},
            )

    assert response.status_code == 200
    update_profile_mock.assert_not_called()
    assert user_row.is_active is False


@pytest.mark.asyncio
async def test_update_user_explicit_null_profile_field_is_ignored(_make_app):
    """PATCH with an explicit null profile field does not touch the profile."""
    app, _, _ = _make_app(["users:write"])

    target_user_id = uuid.uuid4()
    user_row = _make_user_row(
        target_user_id,
        name="Alice",
        given_name="Alice",
    )

    mock_db = AsyncMock()
    first = MagicMock()
    first.scalar_one_or_none.return_value = user_row
    second = MagicMock()
    second.scalar_one_or_none.return_value = user_row
    mock_db.execute = AsyncMock(side_effect=[first, second])

    from auth.api.deps import get_db

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    update_profile_mock = AsyncMock()

    with (
        patch("auth.api.routes.api.deps.token_has_scope", return_value=True),
        patch(
            "auth.api.routes.api.users._profile_service.update_profile",
            update_profile_mock,
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.patch(
                f"/api/v1/users/{target_user_id}",
                json={"given_name": None, "nickname": None},
            )

    assert response.status_code == 200
    # Explicit null == leave untouched, matches admin sparse-update semantics.
    update_profile_mock.assert_not_called()


@pytest.mark.asyncio
async def test_get_user_returns_profile_fields(_make_app):
    """GET /api/v1/users/{id} exposes name/given_name/family_name/nickname."""
    app, _, _ = _make_app(["users:read"])

    target_user_id = uuid.uuid4()
    user_row = _make_user_row(
        target_user_id,
        name="Bob Smith",
        given_name="Bob",
        family_name="Smith",
        nickname="bobby",
    )

    mock_db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = user_row
    mock_db.execute = AsyncMock(return_value=result)

    from auth.api.deps import get_db

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/users/{target_user_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Bob Smith"
    assert body["given_name"] == "Bob"
    assert body["family_name"] == "Smith"
    assert body["nickname"] == "bobby"


@pytest.mark.asyncio
async def test_get_user_without_profile_returns_null_profile_fields(_make_app):
    """GET /api/v1/users/{id} returns null profile fields when no profile."""
    app, _, _ = _make_app(["users:read"])

    target_user_id = uuid.uuid4()
    user_row = _make_user_row(target_user_id, with_profile=False)

    mock_db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = user_row
    mock_db.execute = AsyncMock(return_value=result)

    from auth.api.deps import get_db

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/users/{target_user_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] is None
    assert body["given_name"] is None
    assert body["family_name"] is None
    assert body["nickname"] is None
