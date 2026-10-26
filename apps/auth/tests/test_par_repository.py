# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.repositories.par — PARRepository (100% mocked)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.db.repositories.par import PARRepository

from tests.conftest import make_execute_result


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def repo():
    return PARRepository()


class TestFindByUri:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        par = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=par))
        result = await repo.find_by_uri(db, "urn:ietf:params:oauth:request_uri:abc")
        assert result is par

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        result = await repo.find_by_uri(db, "urn:ietf:params:oauth:request_uri:missing")
        assert result is None


class TestFindByUriAndClient:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        par = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=par))
        result = await repo.find_by_uri_and_client(db, "urn:ietf:params:oauth:request_uri:abc", "c")
        assert result is par

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        result = await repo.find_by_uri_and_client(db, "urn:ietf:params:oauth:request_uri:x", "c")
        assert result is None


class TestListExpired:
    @pytest.mark.asyncio
    async def test_returns_expired(self, db, repo):
        rows = [MagicMock(), MagicMock()]
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
        par = MagicMock()
        await repo.add(db, par)
        db.add.assert_called_once_with(par)
        db.flush.assert_awaited_once()


class TestDelete:
    @pytest.mark.asyncio
    async def test_calls_db_delete(self, db, repo):
        par = MagicMock()
        db.delete = AsyncMock()
        await repo.delete(db, par)
        db.delete.assert_awaited_once_with(par)
