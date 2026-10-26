# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for /api/v1/pats admin endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.api.deps import get_db, get_pat_service
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


@pytest.mark.asyncio
async def test_list_pats_unauthenticated():
    """GET /api/v1/pats/ without auth returns 401."""
    fastapi_app.dependency_overrides.clear()
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/pats/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_pats_forbidden(_make_app):
    """GET /api/v1/pats/ without pats:read returns 403."""
    app, _, _ = _make_app(["users:read"])

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/pats/")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_revoke_pat_unauthenticated():
    """DELETE /api/v1/pats/{id} without auth returns 401."""
    fastapi_app.dependency_overrides.clear()
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.delete(f"/api/v1/pats/{uuid.uuid4()}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_revoke_pat_forbidden(_make_app):
    """DELETE /api/v1/pats/{id} without pats:revoke returns 403."""
    app, _, _ = _make_app(["pats:read"])

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.delete(f"/api/v1/pats/{uuid.uuid4()}")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_revoke_all_pats_unauthenticated():
    """DELETE /api/v1/pats/ without auth returns 401."""
    fastapi_app.dependency_overrides.clear()
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.delete("/api/v1/pats/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_revoke_all_pats_forbidden(_make_app):
    """DELETE /api/v1/pats/ without pats:revoke returns 403."""
    app, _, _ = _make_app(["pats:read"])

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.delete("/api/v1/pats/")
    assert response.status_code == 403


# ===========================================================================
# GET /api/v1/pats/{id} - Get single PAT (admin)
# ===========================================================================


def _make_mock_pat(
    pat_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> MagicMock:
    """Build a MagicMock mimicking a PersonalAccessToken row."""
    pat = MagicMock()
    pat.id = pat_id or uuid.uuid4()
    pat.user_id = user_id or uuid.uuid4()
    pat.tenant_id = None
    pat.target_client_id = None
    pat.name = "CI token"
    pat.token_suffix = "abcd"
    pat.scopes = ["users:read"]
    pat.description = "desc"
    pat.expires_at = None
    pat.revoked_at = None
    pat.last_used_at = None
    pat.last_used_ip = None
    pat.use_count = 3
    pat.created_at = datetime.now(UTC)
    return pat


@pytest.mark.asyncio
async def test_get_pat_unauthenticated():
    """GET /api/v1/pats/{id} without auth returns 401."""
    fastapi_app.dependency_overrides.clear()
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/pats/{uuid.uuid4()}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_pat_forbidden(_make_app):
    """GET /api/v1/pats/{id} without pats:read returns 403."""
    app, _, _ = _make_app(["users:read"])

    with patch("auth.api.routes.api.deps.token_has_scope", return_value=False):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/pats/{uuid.uuid4()}")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_pat_success(_make_app):
    """GET /api/v1/pats/{id} returns the PAT with user_email."""
    app, _, _ = _make_app(["pats:read"])

    pat_id = uuid.uuid4()
    user_id = uuid.uuid4()
    pat = _make_mock_pat(pat_id=pat_id, user_id=user_id)

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    mock_pat_service = MagicMock()
    mock_pat_service.get_token_by_id = AsyncMock(return_value=pat)

    def override_pat_service():
        return mock_pat_service

    email_obj = MagicMock()
    email_obj.email = "owner@example.com"
    email_obj.is_primary = True
    mock_owner = MagicMock()
    mock_owner.emails = [email_obj]

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_pat_service] = override_pat_service

    try:
        with (
            patch("auth.api.routes.api.deps.token_has_scope", return_value=True),
            patch(
                "auth.api.routes.api.pats._user_service.get_by_id",
                new_callable=AsyncMock,
                return_value=mock_owner,
            ),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.get(f"/api/v1/pats/{pat_id}")
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_pat_service, None)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(pat_id)
    assert data["user_id"] == str(user_id)
    assert data["user_email"] == "owner@example.com"
    assert data["name"] == "CI token"
    assert data["scopes"] == ["users:read"]
    mock_pat_service.get_token_by_id.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_pat_not_found(_make_app):
    """GET /api/v1/pats/{id} returns 404 when the PAT does not exist."""
    app, _, _ = _make_app(["pats:read"])

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    mock_pat_service = MagicMock()
    mock_pat_service.get_token_by_id = AsyncMock(return_value=None)

    def override_pat_service():
        return mock_pat_service

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_pat_service] = override_pat_service

    try:
        with patch("auth.api.routes.api.deps.token_has_scope", return_value=True):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.get(f"/api/v1/pats/{uuid.uuid4()}")
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_pat_service, None)

    assert response.status_code == 404
    assert response.json()["detail"] == "Token not found"


# ===========================================================================
# DELETE /api/v1/pats/ - Bulk revoke (with optional user_id filter)
# ===========================================================================


@pytest.mark.asyncio
async def test_revoke_all_pats_no_filter(_make_app):
    """DELETE /api/v1/pats/ without user_id revokes all active tokens via bulk_revoke_all."""
    app, _, _ = _make_app(["pats:revoke"])

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    mock_pat_service = MagicMock()
    mock_pat_service.bulk_revoke = AsyncMock()
    mock_pat_service.bulk_revoke_all = AsyncMock(return_value=2)

    def override_pat_service():
        return mock_pat_service

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_pat_service] = override_pat_service

    try:
        with (
            patch("auth.api.routes.api.deps.token_has_scope", return_value=True),
            patch("auth.services.pat.dispatch_webhook_event", new_callable=AsyncMock),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.delete("/api/v1/pats/")
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_pat_service, None)

    assert response.status_code == 200
    assert response.json()["message"] == "Revoked 2 token(s)"
    mock_pat_service.bulk_revoke_all.assert_awaited_once()
    # bulk_revoke (user-scoped) NOT called in the unfiltered path.
    mock_pat_service.bulk_revoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_revoke_all_pats_with_user_id(_make_app):
    """DELETE /api/v1/pats/?user_id=... delegates to bulk_revoke for that user."""
    app, admin_user, _ = _make_app(["pats:revoke"])

    target_user_id = uuid.uuid4()

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    mock_pat_service = MagicMock()
    mock_pat_service.bulk_revoke = AsyncMock(return_value=4)

    def override_pat_service():
        return mock_pat_service

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_pat_service] = override_pat_service

    try:
        with (
            patch("auth.api.routes.api.deps.token_has_scope", return_value=True),
            patch("auth.services.pat.dispatch_webhook_event", new_callable=AsyncMock),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.delete(
                    f"/api/v1/pats/?user_id={target_user_id}&reason=offboarding"
                )
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_pat_service, None)

    assert response.status_code == 200
    assert response.json()["message"] == "Revoked 4 token(s)"
    mock_pat_service.bulk_revoke.assert_awaited_once()
    call_args = mock_pat_service.bulk_revoke.await_args
    assert call_args.args[1] == target_user_id
    assert call_args.kwargs["revoked_by"] == admin_user.id
    assert call_args.kwargs["reason"] == "offboarding"
    # Direct DB scan path MUST NOT run when user_id is provided.
    mock_db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_revoke_all_pats_with_user_id_default_reason(_make_app):
    """DELETE /api/v1/pats/?user_id=... uses the default reason when none provided."""
    app, admin_user, _ = _make_app(["pats:revoke"])

    target_user_id = uuid.uuid4()

    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    mock_pat_service = MagicMock()
    mock_pat_service.bulk_revoke = AsyncMock(return_value=0)

    def override_pat_service():
        return mock_pat_service

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_pat_service] = override_pat_service

    try:
        with (
            patch("auth.api.routes.api.deps.token_has_scope", return_value=True),
            patch("auth.services.pat.dispatch_webhook_event", new_callable=AsyncMock),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.delete(f"/api/v1/pats/?user_id={target_user_id}")
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_pat_service, None)

    assert response.status_code == 200
    assert response.json()["message"] == "Revoked 0 token(s)"
    call_args = mock_pat_service.bulk_revoke.await_args
    assert call_args.kwargs["reason"] == "admin_user_bulk_revocation"
