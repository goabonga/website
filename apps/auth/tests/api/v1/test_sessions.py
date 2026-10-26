# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for /api/v1/sessions admin endpoints."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.api.deps import get_db
from auth.api.routes.api.deps import get_current_user_bearer
from auth.main import app as fastapi_app
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def _make_app():
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


def _make_mock_session(
    user_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    revoked: bool = False,
    expired: bool = False,
    primary_email: str | None = "user@example.com",
) -> MagicMock:
    """Build a mock Session with a user relationship and emails."""
    session = MagicMock()
    session.id = session_id or uuid.uuid4()
    session.user_id = user_id or uuid.uuid4()
    session.ip_address = "127.0.0.1"
    session.user_agent = "TestAgent/1.0"
    session.created_at = datetime.now(UTC) - timedelta(hours=1)
    session.expires_at = (
        datetime.now(UTC) - timedelta(hours=1)
        if expired
        else datetime.now(UTC) + timedelta(hours=1)
    )
    session.revoked_at = datetime.now(UTC) if revoked else None

    user = MagicMock()
    user.id = session.user_id
    if primary_email is None:
        user.emails = []
    else:
        email = MagicMock()
        email.email = primary_email
        email.is_primary = True
        user.emails = [email]
    session.user = user

    return session


# ---------------------------------------------------------------------------
# Auth / permission failures
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_sessions_unauthenticated():
    """GET /api/v1/sessions/ without auth returns 401."""
    fastapi_app.dependency_overrides.clear()
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/sessions/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_sessions_forbidden(_make_app):
    """GET /api/v1/sessions/ without sessions:read returns 403."""
    app, _, _ = _make_app(["users:read"])

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/sessions/")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_session_unauthenticated():
    """GET /api/v1/sessions/{id} without auth returns 401."""
    fastapi_app.dependency_overrides.clear()
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/sessions/{uuid.uuid4()}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_session_forbidden(_make_app):
    """GET /api/v1/sessions/{id} without sessions:read returns 403."""
    app, _, _ = _make_app(["users:read"])

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/sessions/{uuid.uuid4()}")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_revoke_session_unauthenticated():
    """DELETE /api/v1/sessions/{id} without auth returns 401."""
    fastapi_app.dependency_overrides.clear()
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.delete(f"/api/v1/sessions/{uuid.uuid4()}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_revoke_session_forbidden(_make_app):
    """DELETE /api/v1/sessions/{id} without sessions:revoke returns 403."""
    app, _, _ = _make_app(["sessions:read"])

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.delete(f"/api/v1/sessions/{uuid.uuid4()}")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_revoke_all_sessions_unauthenticated():
    """DELETE /api/v1/sessions/ without auth returns 401."""
    fastapi_app.dependency_overrides.clear()
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.delete("/api/v1/sessions/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_revoke_all_sessions_forbidden(_make_app):
    """DELETE /api/v1/sessions/ without sessions:revoke returns 403."""
    app, _, _ = _make_app(["sessions:read"])

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.delete("/api/v1/sessions/")
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/v1/sessions/ - list with filters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_sessions_success(_make_app):
    """GET /api/v1/sessions/ returns paginated list for admin with sessions:read."""
    app, _, _ = _make_app(["sessions:read"])

    session_1 = _make_mock_session(primary_email="alice@example.com")
    session_2 = _make_mock_session(primary_email="bob@example.com")

    count_result = MagicMock()
    count_result.scalar.return_value = 2

    list_scalars = MagicMock()
    list_scalars.all.return_value = [session_1, session_2]
    list_result = MagicMock()
    list_result.scalars.return_value = list_scalars

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[count_result, list_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/v1/sessions/")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert len(data["items"]) == 2
    assert data["items"][0]["user_email"] == "alice@example.com"
    assert data["items"][1]["user_email"] == "bob@example.com"


@pytest.mark.asyncio
async def test_list_sessions_filter_by_user_id(_make_app):
    """GET /api/v1/sessions/?user_id=X filters sessions for that user."""
    app, _, _ = _make_app(["sessions:read"])

    target_user_id = uuid.uuid4()
    session_1 = _make_mock_session(user_id=target_user_id, primary_email="target@example.com")

    count_result = MagicMock()
    count_result.scalar.return_value = 1
    list_scalars = MagicMock()
    list_scalars.all.return_value = [session_1]
    list_result = MagicMock()
    list_result.scalars.return_value = list_scalars

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[count_result, list_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/sessions/?user_id={target_user_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["user_id"] == str(target_user_id)


@pytest.mark.asyncio
async def test_list_sessions_active_only(_make_app):
    """GET /api/v1/sessions/?active_only=true filters out revoked/expired sessions."""
    app, _, _ = _make_app(["sessions:read"])

    active_session = _make_mock_session()

    count_result = MagicMock()
    count_result.scalar.return_value = 1
    list_scalars = MagicMock()
    list_scalars.all.return_value = [active_session]
    list_result = MagicMock()
    list_result.scalars.return_value = list_scalars

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[count_result, list_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/v1/sessions/?active_only=true")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    # Two ``where`` clauses added (revoked is null, expires_at > now) → we don't
    # assert on the SQL, but we assert the endpoint accepts the flag.
    assert mock_db.execute.await_count == 2


@pytest.mark.asyncio
async def test_list_sessions_user_id_and_active_only(_make_app):
    """GET /api/v1/sessions/?user_id=X&active_only=true combines filters."""
    app, _, _ = _make_app(["sessions:read"])

    target_user_id = uuid.uuid4()
    active_session = _make_mock_session(user_id=target_user_id)

    count_result = MagicMock()
    count_result.scalar.return_value = 1
    list_scalars = MagicMock()
    list_scalars.all.return_value = [active_session]
    list_result = MagicMock()
    list_result.scalars.return_value = list_scalars

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[count_result, list_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/sessions/?user_id={target_user_id}&active_only=true")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["user_id"] == str(target_user_id)


# ---------------------------------------------------------------------------
# GET /api/v1/sessions/{id} - single session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_session_success(_make_app):
    """GET /api/v1/sessions/{id} returns the session with user_email."""
    app, _, _ = _make_app(["sessions:read"])

    session = _make_mock_session(primary_email="alice@example.com")

    get_result = MagicMock()
    get_result.scalar_one_or_none.return_value = session

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[get_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/sessions/{session.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(session.id)
    assert data["user_id"] == str(session.user_id)
    assert data["user_email"] == "alice@example.com"
    assert data["ip_address"] == "127.0.0.1"


@pytest.mark.asyncio
async def test_get_session_not_found(_make_app):
    """GET /api/v1/sessions/{id} returns 404 when session does not exist."""
    app, _, _ = _make_app(["sessions:read"])

    get_result = MagicMock()
    get_result.scalar_one_or_none.return_value = None

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[get_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/sessions/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found"


@pytest.mark.asyncio
async def test_get_session_fallback_email_lookup(_make_app):
    """GET /api/v1/sessions/{id} falls back to UserEmail lookup when user relation has no email."""
    app, _, _ = _make_app(["sessions:read"])

    session = _make_mock_session(primary_email=None)

    get_result = MagicMock()
    get_result.scalar_one_or_none.return_value = session

    fallback_result = MagicMock()
    fallback_result.scalar_one_or_none.return_value = "fallback@example.com"

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[get_result, fallback_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/sessions/{session.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["user_email"] == "fallback@example.com"


# ---------------------------------------------------------------------------
# DELETE /api/v1/sessions/ - revoke all, with/without user_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_all_sessions_success(_make_app):
    """DELETE /api/v1/sessions/ revokes every active session and returns count."""
    app, _, _ = _make_app(["sessions:revoke"])

    session_1 = _make_mock_session()
    session_2 = _make_mock_session()

    list_scalars = MagicMock()
    list_scalars.all.return_value = [session_1, session_2]
    list_result = MagicMock()
    list_result.scalars.return_value = list_scalars

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[list_result])
    mock_db.flush = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete("/api/v1/sessions/")

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Revoked 2 session(s)"
    # Each session had revoked_at set
    assert session_1.revoked_at is not None
    assert session_2.revoked_at is not None


@pytest.mark.asyncio
async def test_revoke_all_sessions_filter_by_user_id(_make_app):
    """DELETE /api/v1/sessions/?user_id=X revokes only that user's sessions."""
    app, _, _ = _make_app(["sessions:revoke"])

    target_user_id = uuid.uuid4()
    session_1 = _make_mock_session(user_id=target_user_id)

    list_scalars = MagicMock()
    list_scalars.all.return_value = [session_1]
    list_result = MagicMock()
    list_result.scalars.return_value = list_scalars

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[list_result])
    mock_db.flush = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(f"/api/v1/sessions/?user_id={target_user_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Revoked 1 session(s)"
    assert session_1.revoked_at is not None


@pytest.mark.asyncio
async def test_revoke_all_sessions_no_matches(_make_app):
    """DELETE /api/v1/sessions/?user_id=X with no active sessions returns 0."""
    app, _, _ = _make_app(["sessions:revoke"])

    list_scalars = MagicMock()
    list_scalars.all.return_value = []
    list_result = MagicMock()
    list_result.scalars.return_value = list_scalars

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[list_result])
    mock_db.flush = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete(f"/api/v1/sessions/?user_id={uuid.uuid4()}")

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Revoked 0 session(s)"
