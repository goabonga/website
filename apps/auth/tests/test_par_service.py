# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.par — PARService (Pushed Authorization Requests)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.services.par import PAR_REQUEST_URI_PREFIX, PARService, generate_request_uri

from tests.conftest import make_execute_result, make_oauth2_client


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def service():
    return PARService()


# ── generate_request_uri ──────────────────────────────────────────────────────


class TestGenerateRequestUri:
    def test_prefix(self):
        uri = generate_request_uri()
        assert uri.startswith(PAR_REQUEST_URI_PREFIX)

    def test_randomness(self):
        assert generate_request_uri() != generate_request_uri()

    def test_length(self):
        uri = generate_request_uri()
        assert len(uri) > len(PAR_REQUEST_URI_PREFIX)


# ── PARService ────────────────────────────────────────────────────────────────


class TestCreateParRequest:
    @pytest.mark.asyncio
    async def test_success(self, db, service):
        client = make_oauth2_client()
        with (
            patch("auth.services.par.PARRequest"),
            patch("auth.services.par.settings") as mock_settings,
        ):
            mock_settings.par_request_expiry_seconds = 60
            uri, expires_in = await service.create_par_request(
                db,
                client,
                "code",
                "https://app.example.com/callback",
                ["openid"],
                state="abc",
                code_challenge="challenge",
                code_challenge_method="S256",
                nonce="nonce",
                prompt="consent",
            )
        assert uri.startswith(PAR_REQUEST_URI_PREFIX)
        assert expires_in == 60
        db.add.assert_called_once()
        db.flush.assert_called_once()


class TestGetParRequest:
    @pytest.mark.asyncio
    async def test_found(self, db, service):
        par = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=par))
        result = await service.get_par_request(db, "urn:ietf:params:oauth:request_uri:abc")
        assert result is par

    @pytest.mark.asyncio
    async def test_not_found(self, db, service):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        result = await service.get_par_request(db, "urn:ietf:params:oauth:request_uri:missing")
        assert result is None


class TestGetParRequestForClient:
    @pytest.mark.asyncio
    async def test_found(self, db, service):
        par = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=par))
        result = await service.get_par_request_for_client(
            db, "urn:ietf:params:oauth:request_uri:abc", "client_123"
        )
        assert result is par

    @pytest.mark.asyncio
    async def test_not_found(self, db, service):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        result = await service.get_par_request_for_client(
            db, "urn:ietf:params:oauth:request_uri:abc", "wrong_client"
        )
        assert result is None


class TestIsExpired:
    def test_not_expired(self, service):
        par = MagicMock()
        par.expires_at = datetime.now(UTC) + timedelta(hours=1)
        assert service.is_expired(par) is False

    def test_expired(self, service):
        par = MagicMock()
        par.expires_at = datetime.now(UTC) - timedelta(hours=1)
        assert service.is_expired(par) is True


class TestIsUsed:
    def test_not_used(self, service):
        par = MagicMock()
        par.used_at = None
        assert service.is_used(par) is False

    def test_used(self, service):
        par = MagicMock()
        par.used_at = datetime.now(UTC)
        assert service.is_used(par) is True


class TestMarkAsUsed:
    @pytest.mark.asyncio
    async def test_marks_used(self, db, service):
        par = MagicMock()
        par.id = "some-id"
        par.used_at = None
        await service.mark_as_used(db, par)
        assert par.used_at is not None
        db.flush.assert_called_once()


class TestDeleteExpired:
    @pytest.mark.asyncio
    async def test_deletes_expired(self, db, service):
        expired = [MagicMock(), MagicMock()]
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=expired))
        count = await service.delete_expired(db)
        assert count == 2
        assert db.delete.call_count == 2

    @pytest.mark.asyncio
    async def test_no_expired(self, db, service):
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=[]))
        count = await service.delete_expired(db)
        assert count == 0
