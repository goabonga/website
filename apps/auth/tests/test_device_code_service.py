# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.device_code — DeviceCodeService and helpers."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.services.device_code import (
    DeviceCodeService,
    generate_device_code,
    generate_user_code,
    hash_device_code,
)

from tests.conftest import make_device_code, make_execute_result, make_oauth2_client

# ── Helper functions ─────────────────────────────────────────────────────────


class TestGenerateDeviceCode:
    def test_length(self):
        assert len(generate_device_code()) == 64

    def test_hex_format(self):
        int(generate_device_code(), 16)

    def test_randomness(self):
        assert generate_device_code() != generate_device_code()


class TestGenerateUserCode:
    def test_default_length_with_hyphen(self):
        code = generate_user_code()
        assert len(code) == 9  # 8 chars + 1 hyphen
        assert "-" in code

    def test_excludes_ambiguous_chars(self):
        for _ in range(100):
            code = generate_user_code().replace("-", "")
            for c in "O0I1L":
                assert c not in code

    def test_custom_length(self):
        code = generate_user_code(length=6)
        assert len(code) == 7  # 6 chars + 1 hyphen

    def test_short_code_no_hyphen(self):
        code = generate_user_code(length=3)
        assert "-" not in code
        assert len(code) == 3


class TestHashDeviceCode:
    def test_sha256(self):
        code = "device_code_value"
        expected = hashlib.sha256(code.encode()).hexdigest()
        assert hash_device_code(code) == expected


# ── DeviceCodeService ────────────────────────────────────────────────────────


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def service():
    return DeviceCodeService()


class TestCreateDeviceAuthorization:
    @pytest.mark.asyncio
    async def test_success(self, db, service):
        client = make_oauth2_client()
        # Mock get_by_user_code at method level to avoid SQLAlchemy select issues
        service.get_by_user_code = AsyncMock(return_value=None)

        with patch("auth.services.device_code.DeviceCode") as MockDC:
            mock_dc = MagicMock()
            mock_dc.user_code = "TEST-CODE"
            MockDC.return_value = mock_dc

            plain_code, device = await service.create_device_authorization(
                db, client, ["openid"], "https://auth.example.com/device"
            )

        assert len(plain_code) == 64
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_user_code_collision_retries(self, db, service):
        client = make_oauth2_client()
        existing = make_device_code()

        # First 2 calls find existing, then None
        service.get_by_user_code = AsyncMock(side_effect=[existing, existing, None])

        with patch("auth.services.device_code.DeviceCode") as MockDC:
            mock_dc = MagicMock()
            MockDC.return_value = mock_dc

            plain_code, device = await service.create_device_authorization(
                db, client, ["openid"], "https://auth.example.com/device"
            )

        assert len(plain_code) == 64


class TestGetByDeviceCode:
    @pytest.mark.asyncio
    async def test_found(self, db, service):
        dc = make_device_code()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=dc))

        result = await service.get_by_device_code(db, "plain_code")
        assert result is dc

    @pytest.mark.asyncio
    async def test_not_found(self, db, service):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await service.get_by_device_code(db, "missing")
        assert result is None


class TestGetByUserCode:
    @pytest.mark.asyncio
    async def test_found(self, db, service):
        dc = make_device_code(user_code="ABCD-EFGH")
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=dc))

        result = await service.get_by_user_code(db, "abcd-efgh")
        assert result is dc

    @pytest.mark.asyncio
    async def test_normalizes_input(self, db, service):
        dc = make_device_code(user_code="ABCD-EFGH")
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=dc))

        # Test without hyphen and lowercase
        result = await service.get_by_user_code(db, "abcdefgh")
        assert result is dc


class TestAuthorize:
    @pytest.mark.asyncio
    async def test_sets_status_and_user(self, db, service):
        dc = make_device_code(status="pending")
        user_id = uuid.uuid4()

        await service.authorize(db, dc, user_id)

        assert dc.status == "authorized"
        assert dc.user_id == user_id
        db.flush.assert_called_once()


class TestDeny:
    @pytest.mark.asyncio
    async def test_sets_denied_status(self, db, service):
        dc = make_device_code(status="pending")

        await service.deny(db, dc)

        assert dc.status == "denied"
        db.flush.assert_called_once()


class TestUpdatePollTime:
    @pytest.mark.asyncio
    async def test_updates_poll_time(self, db, service):
        dc = make_device_code()

        await service.update_poll_time(db, dc)

        assert dc.last_poll_at is not None
        db.flush.assert_called_once()


class TestIsExpired:
    def test_not_expired(self, service):
        dc = make_device_code(expires_at=datetime.now(UTC) + timedelta(minutes=10))
        assert service.is_expired(dc) is False

    def test_expired(self, service):
        dc = make_device_code(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        assert service.is_expired(dc) is True


class TestIsSlowDownRequired:
    def test_no_previous_poll(self, service):
        dc = make_device_code(last_poll_at=None, interval=5)
        assert service.is_slow_down_required(dc) is False

    def test_too_fast(self, service):
        dc = make_device_code(
            last_poll_at=datetime.now(UTC) - timedelta(seconds=1),
            interval=5,
        )
        assert service.is_slow_down_required(dc) is True

    def test_enough_time_passed(self, service):
        dc = make_device_code(
            last_poll_at=datetime.now(UTC) - timedelta(seconds=10),
            interval=5,
        )
        assert service.is_slow_down_required(dc) is False


class TestCleanupExpired:
    @pytest.mark.asyncio
    async def test_deletes_expired(self, db, service):
        expired = [make_device_code(), make_device_code()]
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=expired))

        count = await service.cleanup_expired(db)
        assert count == 2
        assert db.delete.call_count == 2

    @pytest.mark.asyncio
    async def test_no_expired(self, db, service):
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=[]))

        count = await service.cleanup_expired(db)
        assert count == 0


class TestCreateDeviceAuthorizationMaxRetries:
    @pytest.mark.asyncio
    async def test_raises_on_max_retries(self, db, service):
        """Cover line 98: ValueError when all user codes collide."""
        client = make_oauth2_client()
        existing = make_device_code()

        # Always return an existing code (never None)
        service.get_by_user_code = AsyncMock(return_value=existing)

        with pytest.raises(ValueError, match="Failed to generate unique user code"):
            await service.create_device_authorization(
                db, client, ["openid"], "https://auth.example.com/device"
            )


class TestGetByUserCodeShortCode:
    @pytest.mark.asyncio
    async def test_short_code_no_hyphen(self, db, service):
        """Cover line 166: user code with < 4 chars gets no hyphen."""
        dc = make_device_code(user_code="ABC")
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=dc))

        result = await service.get_by_user_code(db, "abc")
        assert result is dc


class TestDelete:
    @pytest.mark.asyncio
    async def test_stages_deletion_and_flushes(self):
        from auth.services.device_code import DeviceCodeService

        service = DeviceCodeService()
        service._repo.delete = AsyncMock()
        db = AsyncMock()
        device = make_device_code()

        await service.delete(db, device)

        service._repo.delete.assert_awaited_once_with(db, device)
        db.flush.assert_awaited_once()
