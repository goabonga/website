# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for /api/v1/me/applications endpoints."""

import pytest


@pytest.mark.asyncio
async def test_list_authorized_applications(client, mock_user, app):
    """GET /api/v1/me/applications/ returns authorized apps."""
    from unittest.mock import AsyncMock

    from auth.api.deps import get_db, get_token_service

    mock_db = AsyncMock()
    mock_token_svc = AsyncMock()
    mock_token_svc.get_user_authorized_clients.return_value = [
        {
            "client_id": "client-1",
            "name": "Test App",
            "description": "A test application",
            "homepage_url": "https://example.com",
            "scopes": ["openid", "profile"],
        },
        {
            "client_id": "client-2",
            "name": "Another App",
            "description": None,
            "homepage_url": None,
            "scopes": ["openid"],
        },
    ]

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_token_service] = lambda: mock_token_svc

    response = await client.get("/api/v1/me/applications/")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 2
    assert data[0]["client_id"] == "client-1"
    assert data[0]["name"] == "Test App"
    assert data[0]["scopes"] == ["openid", "profile"]
    assert data[1]["client_id"] == "client-2"

    mock_token_svc.get_user_authorized_clients.assert_called_once_with(mock_db, mock_user.id)


@pytest.mark.asyncio
async def test_list_authorized_applications_empty(client, mock_user, app):
    """GET /api/v1/me/applications/ returns empty list when no apps authorized."""
    from unittest.mock import AsyncMock

    from auth.api.deps import get_db, get_token_service

    mock_db = AsyncMock()
    mock_token_svc = AsyncMock()
    mock_token_svc.get_user_authorized_clients.return_value = []

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_token_service] = lambda: mock_token_svc

    response = await client.get("/api/v1/me/applications/")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_revoke_application_access(client, mock_user, app):
    """DELETE /api/v1/me/applications/{client_id} revokes access and returns 204."""
    from unittest.mock import AsyncMock

    from auth.api.deps import get_db, get_token_service

    mock_db = AsyncMock()
    mock_token_svc = AsyncMock()
    mock_token_svc.revoke_client_access.return_value = 3

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_token_service] = lambda: mock_token_svc

    response = await client.delete("/api/v1/me/applications/client-1")
    assert response.status_code == 204

    mock_token_svc.revoke_client_access.assert_called_once_with(mock_db, mock_user.id, "client-1")
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_revoke_application_not_found(client, mock_user, app):
    """DELETE /api/v1/me/applications/{client_id} returns 404 when no tokens found."""
    from unittest.mock import AsyncMock

    from auth.api.deps import get_db, get_token_service

    mock_db = AsyncMock()
    mock_token_svc = AsyncMock()
    mock_token_svc.revoke_client_access.return_value = 0

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_token_service] = lambda: mock_token_svc

    response = await client.delete("/api/v1/me/applications/nonexistent")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_list_applications_unauthenticated(app):
    """GET /api/v1/me/applications/ without token returns 401."""
    from auth.api.routes.api.deps import get_current_user_bearer
    from httpx import ASGITransport, AsyncClient

    app.dependency_overrides.pop(get_current_user_bearer, None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/me/applications/")
    assert response.status_code == 401
