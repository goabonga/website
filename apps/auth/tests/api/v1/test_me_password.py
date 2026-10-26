# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for PUT /api/v1/me/password."""

from unittest.mock import AsyncMock

import pytest
from auth.api.deps import get_auth_service, get_db, get_password_service
from auth.api.routes.api.deps import get_current_user_bearer


@pytest.mark.asyncio
async def test_change_password_success(client, mock_user, app):
    """PUT /api/v1/me/password with correct current password succeeds."""
    mock_db = AsyncMock()
    mock_pw_service = AsyncMock()
    mock_pw_service.change_password.return_value = (True, None)
    mock_auth_service = AsyncMock()
    mock_auth_service.verify_credentials.return_value = mock_user

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_password_service] = lambda: mock_pw_service
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    response = await client.put(
        "/api/v1/me/password",
        json={"current_password": "OldPass123", "new_password": "NewPass123"},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Password changed successfully"
    mock_auth_service.verify_credentials.assert_awaited_once()
    mock_pw_service.change_password.assert_awaited_once()


@pytest.mark.asyncio
async def test_change_password_wrong_current(client, mock_user, app):
    """PUT /api/v1/me/password with wrong current password returns 400."""
    mock_db = AsyncMock()
    mock_auth_service = AsyncMock()
    mock_auth_service.verify_credentials.return_value = None

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    response = await client.put(
        "/api/v1/me/password",
        json={"current_password": "WrongPass1", "new_password": "NewPass123"},
    )

    assert response.status_code == 400
    assert "incorrect" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_change_password_unauthenticated(app):
    """PUT /api/v1/me/password without token returns 401."""
    from httpx import ASGITransport, AsyncClient

    app.dependency_overrides.pop(get_current_user_bearer, None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.put(
            "/api/v1/me/password",
            json={"current_password": "OldPass123", "new_password": "NewPass123"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_change_password_validation_error(client):
    """PUT /api/v1/me/password with weak password returns 422."""
    response = await client.put(
        "/api/v1/me/password",
        json={"current_password": "OldPass123", "new_password": "short"},
    )
    assert response.status_code == 422
