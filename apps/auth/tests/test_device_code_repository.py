# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.repositories.device_code — DeviceCodeRepository (100% mocked)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.db.repositories.device_code import DeviceCodeRepository

from tests.conftest import make_device_code, make_execute_result


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def repo():
    return DeviceCodeRepository()


class TestFindByDeviceCodeHash:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        device = make_device_code()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=device))
        result = await repo.find_by_device_code_hash(db, "hash")
        assert result is device

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        result = await repo.find_by_device_code_hash(db, "missing")
        assert result is None


class TestFindByUserCode:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        device = make_device_code()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=device))
        result = await repo.find_by_user_code(db, "ABCD-EFGH")
        assert result is device

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        result = await repo.find_by_user_code(db, "MISS-ING1")
        assert result is None


class TestListExpired:
    @pytest.mark.asyncio
    async def test_returns_expired(self, db, repo):
        rows = [make_device_code(), make_device_code()]
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=rows))
        result = await repo.list_expired(db, datetime.now(UTC))
        assert list(result) == rows

    @pytest.mark.asyncio
    async def test_empty(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=[]))
        result = await repo.list_expired(db, datetime.now(UTC))
        assert list(result) == []


class TestAdd:
    @pytest.mark.asyncio
    async def test_adds_and_flushes(self, db, repo):
        device = make_device_code()
        await repo.add(db, device)
        db.add.assert_called_once_with(device)
        db.flush.assert_awaited_once()


class TestDelete:
    @pytest.mark.asyncio
    async def test_calls_db_delete(self, db, repo):
        device = make_device_code()
        db.delete = AsyncMock()
        await repo.delete(db, device)
        db.delete.assert_awaited_once_with(device)
