# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for /api/v1/me/mfa endpoints."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.api.deps import get_db, get_mfa_service


@pytest.fixture
def mock_mfa_service():
    """Create a mocked MFA service."""
    return AsyncMock()


@pytest.fixture
def mock_db_session():
    """Create a mocked async database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def mfa_app(app, mock_mfa_service, mock_db_session):
    """App with MFA service and DB mocked."""

    async def override_db():
        yield mock_db_session

    app.dependency_overrides[get_mfa_service] = lambda: mock_mfa_service
    app.dependency_overrides[get_db] = override_db
    return app


@pytest.fixture
async def mfa_client(mfa_app):
    """Async client with MFA service mocked."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=mfa_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- GET /api/v1/me/mfa ---


@pytest.mark.asyncio
async def test_get_mfa_status_disabled(mfa_client, mock_mfa_service):
    """GET /api/v1/me/mfa/ returns disabled status when no MFA."""
    mock_mfa_service.get_user_mfa.return_value = None

    response = await mfa_client.get("/api/v1/me/mfa/")
    assert response.status_code == 200
    data = response.json()
    assert data["totp_enabled"] is False
    assert data["backup_codes_remaining"] is None
    assert data["backup_codes_total"] is None


@pytest.mark.asyncio
async def test_get_mfa_status_enabled(mfa_client, mock_mfa_service):
    """GET /api/v1/me/mfa/ returns enabled status with backup codes info."""
    user_mfa = MagicMock()
    user_mfa.totp_enabled = True
    mock_mfa_service.get_user_mfa.return_value = user_mfa
    mock_mfa_service.get_backup_codes_status.return_value = (8, 10)

    response = await mfa_client.get("/api/v1/me/mfa/")
    assert response.status_code == 200
    data = response.json()
    assert data["totp_enabled"] is True
    assert data["backup_codes_remaining"] == 8
    assert data["backup_codes_total"] == 10


@pytest.mark.asyncio
async def test_get_mfa_status_unauthenticated(app):
    """GET /api/v1/me/mfa/ without token returns 401."""
    from auth.api.routes.api.deps import get_current_user_bearer
    from httpx import ASGITransport, AsyncClient

    app.dependency_overrides.pop(get_current_user_bearer, None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/me/mfa/")
    assert response.status_code == 401


# --- POST /api/v1/me/mfa/totp/setup ---


@pytest.mark.asyncio
async def test_setup_totp_success(mfa_client, mock_mfa_service):
    """POST /api/v1/me/mfa/totp/setup returns secret and QR code."""
    mock_mfa_service.setup_totp.return_value = ("JBSWY3DPEHPK3PXP", "otpauth://...", "base64qr")

    response = await mfa_client.post("/api/v1/me/mfa/totp/setup")
    assert response.status_code == 200
    data = response.json()
    assert data["secret"] == "JBSWY3DPEHPK3PXP"
    assert data["qr_code"] == "base64qr"


@pytest.mark.asyncio
async def test_setup_totp_no_email(mfa_client, mock_user):
    """POST /api/v1/me/mfa/totp/setup returns 400 if no primary email."""
    mock_user.emails = []

    response = await mfa_client.post("/api/v1/me/mfa/totp/setup")
    assert response.status_code == 400
    assert "primary email" in response.json()["detail"].lower()


# --- POST /api/v1/me/mfa/totp/verify ---


@pytest.mark.asyncio
async def test_verify_totp_success(mfa_client, mock_mfa_service):
    """POST /api/v1/me/mfa/totp/verify enables TOTP and returns backup codes."""
    mock_mfa_service.enable_totp.return_value = ["CODE1", "CODE2", "CODE3"]

    response = await mfa_client.post(
        "/api/v1/me/mfa/totp/verify",
        json={"code": "123456"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "TOTP enabled successfully"
    assert data["backup_codes"] == ["CODE1", "CODE2", "CODE3"]


@pytest.mark.asyncio
async def test_verify_totp_invalid_code(mfa_client, mock_mfa_service):
    """POST /api/v1/me/mfa/totp/verify returns 400 for invalid code."""
    mock_mfa_service.enable_totp.return_value = None

    response = await mfa_client.post(
        "/api/v1/me/mfa/totp/verify",
        json={"code": "000000"},
    )
    assert response.status_code == 400
    assert "invalid" in response.json()["detail"].lower()


# --- POST /api/v1/me/mfa/totp/disable ---


@pytest.mark.asyncio
async def test_disable_totp_success(mfa_client, mock_mfa_service):
    """POST /api/v1/me/mfa/totp/disable disables TOTP."""
    mock_mfa_service.disable_totp.return_value = True

    response = await mfa_client.post(
        "/api/v1/me/mfa/totp/disable",
        json={"code": "123456"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "TOTP disabled successfully"


@pytest.mark.asyncio
async def test_disable_totp_invalid_code(mfa_client, mock_mfa_service):
    """POST /api/v1/me/mfa/totp/disable returns 400 for invalid code."""
    mock_mfa_service.disable_totp.return_value = False

    response = await mfa_client.post(
        "/api/v1/me/mfa/totp/disable",
        json={"code": "000000"},
    )
    assert response.status_code == 400


# --- POST /api/v1/me/mfa/backup-codes ---


@pytest.mark.asyncio
async def test_regenerate_backup_codes_success(mfa_client, mock_mfa_service):
    """POST /api/v1/me/mfa/backup-codes returns new backup codes."""
    mock_mfa_service.regenerate_backup_codes.return_value = ["NEW1", "NEW2", "NEW3"]

    response = await mfa_client.post(
        "/api/v1/me/mfa/backup-codes",
        json={"code": "123456"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["backup_codes"] == ["NEW1", "NEW2", "NEW3"]


@pytest.mark.asyncio
async def test_regenerate_backup_codes_invalid_code(mfa_client, mock_mfa_service):
    """POST /api/v1/me/mfa/backup-codes returns 400 for invalid code."""
    mock_mfa_service.regenerate_backup_codes.return_value = None

    response = await mfa_client.post(
        "/api/v1/me/mfa/backup-codes",
        json={"code": "000000"},
    )
    assert response.status_code == 400
    assert "invalid" in response.json()["detail"].lower()
