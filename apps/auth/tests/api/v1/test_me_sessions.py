# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for GET /api/v1/me/sessions and DELETE /api/v1/me/sessions/{id}."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.api.deps import get_db, get_session_service
from auth.api.routes.api.deps import get_current_user_bearer


def _make_mock_session(user_id: uuid.UUID) -> MagicMock:
    """Create a mock session object."""
    session = MagicMock()
    session.id = uuid.uuid4()
    session.user_id = user_id
    session.ip_address = "127.0.0.1"
    session.user_agent = "TestAgent/1.0"
    session.created_at = datetime.now(UTC)
    session.expires_at = datetime.now(UTC) + timedelta(hours=1)
    return session


@pytest.mark.asyncio
async def test_list_sessions_success(client, mock_user, app):
    """GET /api/v1/me/sessions returns list of sessions."""
    mock_db = AsyncMock()
    mock_session_service = AsyncMock()
    sessions = [_make_mock_session(mock_user.id), _make_mock_session(mock_user.id)]
    mock_session_service.get_user_sessions.return_value = sessions

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_session_service] = lambda: mock_session_service

    response = await client.get("/api/v1/me/sessions")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert "id" in data[0]
    assert "ip_address" in data[0]
    assert "user_agent" in data[0]
    assert "created_at" in data[0]
    assert "expires_at" in data[0]


@pytest.mark.asyncio
async def test_revoke_session_success(client, mock_user, app):
    """DELETE /api/v1/me/sessions/{id} revokes session and returns 204."""
    mock_db = AsyncMock()
    mock_session_service = AsyncMock()
    mock_session_service.revoke_session_by_id.return_value = True

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_session_service] = lambda: mock_session_service

    session_id = uuid.uuid4()
    response = await client.delete(f"/api/v1/me/sessions/{session_id}")

    assert response.status_code == 204
    mock_session_service.revoke_session_by_id.assert_awaited_once()


@pytest.mark.asyncio
async def test_revoke_session_not_found(client, mock_user, app):
    """DELETE /api/v1/me/sessions/{id} returns 404 when session not found."""
    mock_db = AsyncMock()
    mock_session_service = AsyncMock()
    mock_session_service.revoke_session_by_id.return_value = False

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_session_service] = lambda: mock_session_service

    session_id = uuid.uuid4()
    response = await client.delete(f"/api/v1/me/sessions/{session_id}")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_list_sessions_unauthenticated(app):
    """GET /api/v1/me/sessions without token returns 401."""
    from httpx import ASGITransport, AsyncClient

    app.dependency_overrides.pop(get_current_user_bearer, None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/me/sessions")
    assert response.status_code == 401
