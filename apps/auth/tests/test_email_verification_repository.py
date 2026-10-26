# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.repositories.email_verification — EmailVerificationRepository (100% mocked)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.db.repositories.email_verification import EmailVerificationRepository

from tests.conftest import make_execute_result, make_user_email


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def repo():
    return EmailVerificationRepository()


class TestFindValidForEmail:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        code = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=code))
        result = await repo.find_valid_for_email(db, "x@example.com", datetime.now(UTC))
        assert result is code

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        result = await repo.find_valid_for_email(db, "x@example.com", datetime.now(UTC))
        assert result is None


class TestFindValidByHash:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        code = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=code))
        result = await repo.find_valid_by_hash(db, "x@example.com", "h", datetime.now(UTC))
        assert result is code

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        result = await repo.find_valid_by_hash(db, "x@example.com", "h", datetime.now(UTC))
        assert result is None


class TestFindUserEmail:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        ue = make_user_email()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=ue))
        result = await repo.find_user_email(db, "X@Example.com")
        assert result is ue

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        result = await repo.find_user_email(db, "x@example.com")
        assert result is None


class TestAdd:
    @pytest.mark.asyncio
    async def test_adds_and_flushes(self, db, repo):
        code = MagicMock()
        await repo.add(db, code)
        db.add.assert_called_once_with(code)
        db.flush.assert_awaited_once()
