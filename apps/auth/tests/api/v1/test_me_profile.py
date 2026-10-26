# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for GET/PUT /api/v1/me."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.api.routes.api.deps import get_current_user_bearer
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_get_profile_success(client, mock_user):
    """GET /api/v1/me/ returns user profile."""
    response = await client.get("/api/v1/me/")
    assert response.status_code == 200
    data = response.json()
    assert data["sub"] == str(mock_user.id)
    assert data["nickname"] == "testuser"
    assert data["given_name"] == "Test"
    assert data["family_name"] == "User"


@pytest.mark.asyncio
async def test_get_profile_unauthenticated(app):
    """GET /api/v1/me/ without token returns 401."""
    app.dependency_overrides.pop(get_current_user_bearer, None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/me/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_profile_success(client, mock_user, app):
    """PUT /api/v1/me/ updates profile fields."""
    from auth.api.deps import get_db, get_profile_service

    mock_db = AsyncMock()
    mock_profile_service = AsyncMock()
    mock_profile_service.update_profile.return_value = mock_user.profile

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_profile_service] = lambda: mock_profile_service

    response = await client.put(
        "/api/v1/me/",
        json={"nickname": "updated", "given_name": "Updated"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["sub"] == str(mock_user.id)


@pytest.mark.asyncio
async def test_update_profile_validation_error(client):
    """PUT /api/v1/me/ with invalid body returns 422."""
    response = await client.put("/api/v1/me/", content="not json")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Pairwise sub integration
# ---------------------------------------------------------------------------


def _make_pairwise_auth_override(mock_user: MagicMock, pairwise_sub: str):
    """Create an auth dependency override that sets request.state.pairwise_sub."""
    from fastapi import Request as _Request

    async def override(request: _Request):
        request.state.pairwise_sub = pairwise_sub
        request.state.auth_scopes = ["openid", "profile"]
        request.state.auth_type = "bearer"
        return mock_user

    return override


@pytest.mark.asyncio
async def test_get_profile_returns_pairwise_sub(mock_user):
    """GET /api/v1/me/ returns pairwise sub when set on request.state."""
    from auth.main import app as fastapi_app

    pairwise_sub = str(uuid.uuid4())
    fastapi_app.dependency_overrides[get_current_user_bearer] = _make_pairwise_auth_override(
        mock_user, pairwise_sub
    )

    try:
        transport = ASGITransport(app=fastapi_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/v1/me/")
        assert response.status_code == 200
        data = response.json()
        assert data["sub"] == pairwise_sub
        assert data["sub"] != str(mock_user.id)
    finally:
        fastapi_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_update_profile_returns_pairwise_sub(mock_user):
    """PUT /api/v1/me/ returns pairwise sub when set on request.state."""
    from auth.api.deps import get_db, get_profile_service
    from auth.main import app as fastapi_app

    pairwise_sub = str(uuid.uuid4())

    mock_db = AsyncMock()
    mock_profile_service = AsyncMock()
    mock_profile_service.update_profile.return_value = mock_user.profile

    async def override_db():
        yield mock_db

    fastapi_app.dependency_overrides[get_current_user_bearer] = _make_pairwise_auth_override(
        mock_user, pairwise_sub
    )
    fastapi_app.dependency_overrides[get_db] = override_db
    fastapi_app.dependency_overrides[get_profile_service] = lambda: mock_profile_service

    try:
        transport = ASGITransport(app=fastapi_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.put(
                "/api/v1/me/",
                json={"nickname": "pw_user"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["sub"] == pairwise_sub
    finally:
        fastapi_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_profile_falls_back_to_user_id_without_pairwise(client, mock_user):
    """GET /api/v1/me/ falls back to str(user.id) when pairwise_sub is not set."""
    response = await client.get("/api/v1/me/")
    assert response.status_code == 200
    data = response.json()
    # Default conftest override does not set request.state.pairwise_sub
    assert data["sub"] == str(mock_user.id)
