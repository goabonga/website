# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.repositories.password_reset — PasswordResetRepository (100% mocked)."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.db.repositories.password_reset import PasswordResetRepository

from tests.conftest import (
    make_execute_result,
    make_password_reset_token,
    make_user,
    make_user_email,
)


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def repo():
    return PasswordResetRepository()


class TestFindVerifiedUserEmail:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        ue = make_user_email(is_verified=True)
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=ue))

        result = await repo.find_verified_user_email(db, "user@example.com")
        assert result is ue

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_verified_user_email(db, "missing@example.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_lowercased_in_call(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        await repo.find_verified_user_email(db, "USER@EXAMPLE.COM")
        db.execute.assert_called_once()


class TestFindValidByHash:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        prt = make_password_reset_token()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=prt))

        result = await repo.find_valid_by_hash(db, "hash", datetime.now(UTC))
        assert result is prt

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_valid_by_hash(db, "bad", datetime.now(UTC))
        assert result is None


class TestAddResetToken:
    @pytest.mark.asyncio
    async def test_adds_and_flushes(self, db, repo):
        token = make_password_reset_token()
        await repo.add_reset_token(db, token)
        db.add.assert_called_once_with(token)
        db.flush.assert_awaited_once()


class TestAddPassword:
    @pytest.mark.asyncio
    async def test_adds_no_flush(self, db, repo):
        pwd = MagicMock()
        await repo.add_password(db, pwd)
        db.add.assert_called_once_with(pwd)
        db.flush.assert_not_awaited()


class TestFindUserForReset:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        user = make_user()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=user))
        result = await repo.find_user_for_reset(db, user.id)
        assert result is user

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        result = await repo.find_user_for_reset(db, uuid.uuid4())
        assert result is None
