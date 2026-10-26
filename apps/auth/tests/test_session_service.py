# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.session — SessionService and helpers."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.services.session import SessionService, generate_token, hash_token

from tests.conftest import make_execute_result, make_session, make_user

# ── Helper functions ─────────────────────────────────────────────────────────


class TestGenerateToken:
    def test_length(self):
        assert len(generate_token()) == 64

    def test_hex_format(self):
        int(generate_token(), 16)

    def test_randomness(self):
        assert generate_token() != generate_token()


class TestHashTokenHelper:
    def test_sha256(self):
        expected = hashlib.sha256(b"abc").hexdigest()
        assert hash_token("abc") == expected


# ── SessionService ───────────────────────────────────────────────────────────


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def service():
    return SessionService()


class TestCreateSession:
    @pytest.mark.asyncio
    async def test_returns_tokens(self, db, service):
        with patch("auth.services.session.Session"):
            session_token, csrf_token = await service.create_session(
                db, str(uuid.uuid4()), ip_address="127.0.0.1"
            )

        assert len(session_token) == 64
        assert len(csrf_token) == 64
        assert session_token != csrf_token
        db.add.assert_called_once()
        db.flush.assert_called_once()


class TestGetSessionByToken:
    @pytest.mark.asyncio
    async def test_found(self, db, service):
        s = make_session()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=s))

        result = await service.get_session_by_token(db, "session_token")
        assert result is s

    @pytest.mark.asyncio
    async def test_not_found(self, db, service):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await service.get_session_by_token(db, "missing_token")
        assert result is None


class TestGetUserBySessionToken:
    @pytest.mark.asyncio
    async def test_found(self, db, service):
        s = make_session()
        user = make_user(user_id=s.user_id)

        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=s),
                make_execute_result(scalar_value=user),
            ]
        )

        result = await service.get_user_by_session_token(db, "session_token")
        assert result is user

    @pytest.mark.asyncio
    async def test_no_session(self, db, service):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await service.get_user_by_session_token(db, "bad_token")
        assert result is None


class TestVerifyCsrfToken:
    @pytest.mark.asyncio
    async def test_valid_csrf(self, db, service):
        csrf_token = "my_csrf_token"
        s = make_session(csrf_token_hash=hash_token(csrf_token))
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=s))

        result = await service.verify_csrf_token(db, "session_token", csrf_token)
        assert result is True

    @pytest.mark.asyncio
    async def test_invalid_csrf(self, db, service):
        s = make_session(csrf_token_hash=hash_token("correct_csrf"))
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=s))

        result = await service.verify_csrf_token(db, "session_token", "wrong_csrf")
        assert result is False

    @pytest.mark.asyncio
    async def test_no_session(self, db, service):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await service.verify_csrf_token(db, "missing", "csrf")
        assert result is False


class TestRevokeSession:
    @pytest.mark.asyncio
    async def test_success(self, db, service):
        s = make_session()
        s.revoked_at = None
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=s))

        result = await service.revoke_session(db, "session_token")
        assert result is True
        assert s.revoked_at is not None

    @pytest.mark.asyncio
    async def test_not_found(self, db, service):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await service.revoke_session(db, "missing")
        assert result is False


class TestRevokeAllUserSessions:
    @pytest.mark.asyncio
    async def test_revokes_all(self, db, service):
        sessions = [make_session(), make_session()]
        for s in sessions:
            s.revoked_at = None
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=sessions))

        count = await service.revoke_all_user_sessions(db, str(uuid.uuid4()))
        assert count == 2
        assert all(s.revoked_at is not None for s in sessions)

    @pytest.mark.asyncio
    async def test_no_sessions(self, db, service):
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=[]))

        count = await service.revoke_all_user_sessions(db, str(uuid.uuid4()))
        assert count == 0

    @pytest.mark.asyncio
    async def test_except_session_id(self, db, service):
        """Cover line 206-207: except_session_id filter."""
        sessions = [make_session()]
        for s in sessions:
            s.revoked_at = None
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=sessions))

        count = await service.revoke_all_user_sessions(
            db, str(uuid.uuid4()), except_session_id=str(uuid.uuid4())
        )
        assert count == 1
        assert sessions[0].revoked_at is not None


class TestGetUserSessions:
    @pytest.mark.asyncio
    async def test_returns_sessions(self, db, service):
        sessions = [make_session(), make_session()]
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=sessions))

        result = await service.get_user_sessions(db, str(uuid.uuid4()))
        assert len(result) == 2


class TestRevokeSessionById:
    @pytest.mark.asyncio
    async def test_success(self, db, service):
        s = make_session()
        s.revoked_at = None
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=s))

        result = await service.revoke_session_by_id(db, str(s.user_id), str(s.id))
        assert result is True
        assert s.revoked_at is not None

    @pytest.mark.asyncio
    async def test_not_found(self, db, service):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await service.revoke_session_by_id(db, str(uuid.uuid4()), str(uuid.uuid4()))
        assert result is False


class TestRefreshSession:
    @pytest.mark.asyncio
    async def test_refreshes_when_near_expiry(self, db, service):
        # Session expiring in 1 hour (within 10% of 7 days = ~17h)
        s = make_session(expires_at=datetime.now(UTC) + timedelta(hours=1))

        with patch("auth.services.session.settings") as mock_settings:
            mock_settings.session_expiry_days = 7
            await service.refresh_session(db, s)

        # Session should have been extended
        db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_does_not_refresh_when_far_from_expiry(self, db, service):
        # Session expiring in 5 days (way outside 10% window)
        s = make_session(expires_at=datetime.now(UTC) + timedelta(days=5))

        with patch("auth.services.session.settings") as mock_settings:
            mock_settings.session_expiry_days = 7
            await service.refresh_session(db, s)

        db.flush.assert_not_called()


class TestCleanupExpiredSessions:
    @pytest.mark.asyncio
    async def test_deletes_expired(self, db, service):
        expired = [make_session(), make_session()]
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=expired))

        count = await service.cleanup_expired_sessions(db)
        assert count == 2
        assert db.delete.call_count == 2

    @pytest.mark.asyncio
    async def test_no_expired(self, db, service):
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=[]))

        count = await service.cleanup_expired_sessions(db)
        assert count == 0


class TestGetSession:
    @pytest.mark.asyncio
    async def test_alias(self, db, service):
        s = make_session()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=s))

        result = await service.get_session(db, "token")
        assert result is s


class TestAdd:
    @pytest.mark.asyncio
    async def test_stages_prebuilt_session(self, db, service):
        session = make_session()
        service._repo.add = AsyncMock()

        assert await service.add(db, session) is session
        service._repo.add.assert_awaited_once_with(db, session)


class TestGetSessionWithUserByToken:
    @pytest.mark.asyncio
    async def test_hashes_token_before_lookup(self, db, service):
        session = make_session()
        service._repo.find_by_token_hash_with_user = AsyncMock(return_value=session)

        assert await service.get_session_with_user_by_token(db, "raw-token") is session
        service._repo.find_by_token_hash_with_user.assert_awaited_once_with(
            db, hash_token("raw-token")
        )


class TestGetUserBySessionTokenInactive:
    @pytest.mark.asyncio
    async def test_inactive_user_returns_none(self, db, service):
        session = make_session()
        service.get_session_by_token = AsyncMock(return_value=session)
        user = make_user(is_active=False)
        service._user_repo.find_by_id = AsyncMock(return_value=user)

        assert await service.get_user_by_session_token(db, "raw-token") is None

    @pytest.mark.asyncio
    async def test_missing_user_returns_none(self, db, service):
        service.get_session_by_token = AsyncMock(return_value=make_session())
        service._user_repo.find_by_id = AsyncMock(return_value=None)

        assert await service.get_user_by_session_token(db, "raw-token") is None


class TestCountActive:
    @pytest.mark.asyncio
    async def test_delegates_to_repository(self, db, service):
        service._repo.count_active = AsyncMock(return_value=3)
        user_id = uuid.uuid4()

        assert await service.count_active(db, user_id=user_id) == 3
        service._repo.count_active.assert_awaited_once_with(db, user_id=user_id)


class TestRevokeSessionByIdAdmin:
    @pytest.mark.asyncio
    async def test_revokes_existing_session(self, db, service):
        session = make_session()
        service._repo.find_unrevoked_by_id = AsyncMock(return_value=session)
        service._repo.revoke = AsyncMock()

        assert await service.revoke_session_by_id_admin(db, session.id) is session
        service._repo.revoke.assert_awaited_once_with(db, session)

    @pytest.mark.asyncio
    async def test_unknown_or_revoked_session_returns_none(self, db, service):
        service._repo.find_unrevoked_by_id = AsyncMock(return_value=None)
        service._repo.revoke = AsyncMock()

        assert await service.revoke_session_by_id_admin(db, uuid.uuid4()) is None
        service._repo.revoke.assert_not_awaited()
