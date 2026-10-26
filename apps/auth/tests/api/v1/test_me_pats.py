# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for /api/v1/me/pats endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.api.deps import get_db, get_pat_service


def _make_pat(**overrides):
    """Create a mock PAT object."""
    pat = MagicMock()
    pat.id = overrides.get("id", uuid.uuid4())
    pat.name = overrides.get("name", "Test Token")
    pat.description = overrides.get("description", "A test token")
    pat.token_suffix = overrides.get("token_suffix", "abc123")
    pat.scopes = overrides.get("scopes", ["read:profile"])
    pat.expires_at = overrides.get("expires_at", datetime(2027, 1, 1, tzinfo=UTC))
    pat.revoked_at = overrides.get("revoked_at")
    pat.last_used_at = overrides.get("last_used_at")
    pat.use_count = overrides.get("use_count", 0)
    pat.created_at = overrides.get("created_at", datetime(2026, 1, 1, tzinfo=UTC))
    return pat


@pytest.fixture
def mock_pat_service():
    """Create a mocked PAT service."""
    return AsyncMock()


@pytest.fixture
def mock_db_session():
    """Create a mocked async database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def tokens_app(app, mock_pat_service, mock_db_session):
    """App with PAT service and DB mocked."""

    async def override_db():
        yield mock_db_session

    app.dependency_overrides[get_pat_service] = lambda: mock_pat_service
    app.dependency_overrides[get_db] = override_db
    return app


@pytest.fixture
async def tokens_client(tokens_app):
    """Async client with PAT service mocked."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=tokens_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- GET /api/v1/me/pats ---


@pytest.mark.asyncio
async def test_list_tokens_success(tokens_client, mock_pat_service):
    """GET /api/v1/me/pats/ returns paginated list."""
    pat = _make_pat()
    mock_pat_service.list_user_tokens.return_value = ([pat], 1)

    response = await tokens_client.get("/api/v1/me/pats/")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "Test Token"


@pytest.mark.asyncio
async def test_list_tokens_empty(tokens_client, mock_pat_service):
    """GET /api/v1/me/pats/ returns empty list."""
    mock_pat_service.list_user_tokens.return_value = ([], 0)

    response = await tokens_client.get("/api/v1/me/pats/")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_list_tokens_pagination(tokens_client, mock_pat_service):
    """GET /api/v1/me/pats/?page=2&page_size=5 passes correct offset."""
    mock_pat_service.list_user_tokens.return_value = ([], 0)

    response = await tokens_client.get("/api/v1/me/pats/?page=2&page_size=5")
    assert response.status_code == 200

    call_args = mock_pat_service.list_user_tokens.call_args
    assert call_args.kwargs.get("offset") == 5 or call_args[1].get("offset") == 5


@pytest.mark.asyncio
async def test_list_tokens_unauthenticated(app):
    """GET /api/v1/me/pats/ without token returns 401."""
    from auth.api.routes.api.deps import get_current_user_bearer
    from httpx import ASGITransport, AsyncClient

    app.dependency_overrides.pop(get_current_user_bearer, None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/me/pats/")
    assert response.status_code == 401


# --- POST /api/v1/me/pats ---


@pytest.mark.asyncio
async def test_create_token_success(tokens_client, mock_pat_service):
    """POST /api/v1/me/pats/ creates a new PAT."""
    pat = _make_pat()
    mock_pat_service.create_token.return_value = (pat, "authp_full_raw_token_value")

    response = await tokens_client.post(
        "/api/v1/me/pats/",
        json={"name": "My Token", "scopes": ["read:profile"]},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Token"
    assert data["token"] == "authp_full_raw_token_value"
    assert data["scopes"] == ["read:profile"]


@pytest.mark.asyncio
async def test_create_token_validation_error(tokens_client):
    """POST /api/v1/me/pats/ with missing name returns 422."""
    response = await tokens_client.post(
        "/api/v1/me/pats/",
        json={"scopes": ["read:profile"]},
    )
    assert response.status_code == 422


# --- GET /api/v1/me/pats/{token_id} ---


@pytest.mark.asyncio
async def test_get_token_success(tokens_client, mock_pat_service):
    """GET /api/v1/me/pats/{id} returns PAT details."""
    pat = _make_pat()
    mock_pat_service.get_token_by_id.return_value = pat

    response = await tokens_client.get(f"/api/v1/me/pats/{pat.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Token"
    assert data["token_suffix"] == "abc123"


@pytest.mark.asyncio
async def test_get_token_not_found(tokens_client, mock_pat_service):
    """GET /api/v1/me/pats/{id} returns 404 when token does not exist."""
    mock_pat_service.get_token_by_id.return_value = None

    response = await tokens_client.get(f"/api/v1/me/pats/{uuid.uuid4()}")
    assert response.status_code == 404


# --- PATCH /api/v1/me/pats/{token_id} ---


@pytest.mark.asyncio
async def test_update_token_scopes_success(tokens_client, mock_pat_service):
    """PATCH /api/v1/me/pats/{id} updates scopes."""
    pat = _make_pat(scopes=["read:profile", "write:profile"])
    mock_pat_service.update_token_scopes.return_value = pat

    response = await tokens_client.patch(
        f"/api/v1/me/pats/{pat.id}",
        json={"scopes": ["read:profile", "write:profile"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["scopes"] == ["read:profile", "write:profile"]


@pytest.mark.asyncio
async def test_update_token_scopes_not_found(tokens_client, mock_pat_service):
    """PATCH /api/v1/me/pats/{id} returns 404 when token not found or revoked."""
    mock_pat_service.update_token_scopes.return_value = None

    response = await tokens_client.patch(
        f"/api/v1/me/pats/{uuid.uuid4()}",
        json={"scopes": ["read:profile"]},
    )
    assert response.status_code == 404


# --- DELETE /api/v1/me/pats/{token_id} ---


@pytest.mark.asyncio
async def test_revoke_token_success(tokens_client, mock_pat_service):
    """DELETE /api/v1/me/pats/{id} revokes the token."""
    mock_pat_service.revoke_token.return_value = True

    response = await tokens_client.delete(f"/api/v1/me/pats/{uuid.uuid4()}")
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_revoke_token_not_found(tokens_client, mock_pat_service):
    """DELETE /api/v1/me/pats/{id} returns 404 when token not found."""
    mock_pat_service.revoke_token.return_value = False

    response = await tokens_client.delete(f"/api/v1/me/pats/{uuid.uuid4()}")
    assert response.status_code == 404


# --- POST /api/v1/me/pats/{token_id}/regenerate ---


@pytest.mark.asyncio
async def test_regenerate_token_success(tokens_client, mock_pat_service):
    """POST /api/v1/me/pats/{id}/regenerate returns new token."""
    new_pat = _make_pat(name="Regenerated Token")
    mock_pat_service.regenerate_token.return_value = (new_pat, "authp_new_raw_token")

    response = await tokens_client.post(f"/api/v1/me/pats/{uuid.uuid4()}/regenerate")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Regenerated Token"
    assert data["token"] == "authp_new_raw_token"


@pytest.mark.asyncio
async def test_regenerate_token_not_found(tokens_client, mock_pat_service):
    """POST /api/v1/me/pats/{id}/regenerate returns 404 when not found."""
    mock_pat_service.regenerate_token.return_value = None

    response = await tokens_client.post(f"/api/v1/me/pats/{uuid.uuid4()}/regenerate")
    assert response.status_code == 404
