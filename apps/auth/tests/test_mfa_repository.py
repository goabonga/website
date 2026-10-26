# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.repositories.mfa — MFARepository (100% mocked)."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.db.repositories.mfa import MFARepository

from tests.conftest import make_backup_code, make_execute_result, make_user_mfa


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def repo():
    return MFARepository()


# ── find_user_mfa ────────────────────────────────────────────────────────────


class TestFindUserMfa:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        mfa = make_user_mfa(totp_enabled=True, backup_codes=[make_backup_code()])
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        result = await repo.find_user_mfa(db, str(uuid.uuid4()))

        assert result is mfa
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_user_mfa(db, str(uuid.uuid4()))

        assert result is None


# ── find_valid_email_code ────────────────────────────────────────────────────


class TestFindValidEmailCode:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        mock_code = MagicMock()
        mock_code.used_at = None
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mock_code))

        result = await repo.find_valid_email_code(
            db,
            str(uuid.uuid4()),
            "hash",
            now=datetime.now(UTC),
        )

        assert result is mock_code
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_valid_email_code(
            db,
            str(uuid.uuid4()),
            "hash",
            now=datetime.now(UTC),
        )

        assert result is None


# ── add / delete ─────────────────────────────────────────────────────────────


class TestAdd:
    @pytest.mark.asyncio
    async def test_adds_and_flushes(self, db, repo):
        instance = MagicMock()

        await repo.add(db, instance)

        db.add.assert_called_once_with(instance)
        db.flush.assert_awaited_once()


class TestStage:
    @pytest.mark.asyncio
    async def test_stages_without_flush(self, db, repo):
        instance = MagicMock()

        result = await repo.stage(db, instance)

        db.add.assert_called_once_with(instance)
        db.flush.assert_not_awaited()
        assert result is instance


class TestDelete:
    @pytest.mark.asyncio
    async def test_calls_db_delete(self, db, repo):
        instance = MagicMock()
        db.delete = AsyncMock()

        await repo.delete(db, instance)

        db.delete.assert_awaited_once_with(instance)
