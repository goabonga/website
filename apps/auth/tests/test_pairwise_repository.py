# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.repositories.pairwise — PairwiseSubjectRepository (100% mocked)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.db.repositories.pairwise import PairwiseSubjectRepository

from tests.conftest import make_execute_result


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def repo():
    return PairwiseSubjectRepository()


# ── find_by_user_and_tenant ──────────────────────────────────────────────────


class TestFindByUserAndTenant:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        sub_value = uuid.uuid4()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=sub_value))

        result = await repo.find_by_user_and_tenant(db, uuid.uuid4(), uuid.uuid4())
        assert result == sub_value

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_by_user_and_tenant(db, uuid.uuid4(), uuid.uuid4())
        assert result is None


# ── find_by_sub ──────────────────────────────────────────────────────────────


class TestFindBySub:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        user_id = uuid.uuid4()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=user_id))

        result = await repo.find_by_sub(db, uuid.uuid4(), uuid.uuid4())
        assert result == user_id

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_by_sub(db, uuid.uuid4(), uuid.uuid4())
        assert result is None


# ── list_for_user ────────────────────────────────────────────────────────────


class TestListForUser:
    @pytest.mark.asyncio
    async def test_returns_rows(self, db, repo):
        rows = [MagicMock(), MagicMock()]
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=rows))

        result = await repo.list_for_user(db, uuid.uuid4())
        assert result == rows

    @pytest.mark.asyncio
    async def test_empty(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=[]))

        result = await repo.list_for_user(db, uuid.uuid4())
        assert result == []


# ── add ──────────────────────────────────────────────────────────────────────


class TestAdd:
    @pytest.mark.asyncio
    async def test_executes_insert_and_flushes(self, db, repo):
        db.execute = AsyncMock(return_value=MagicMock())

        await repo.add(db, uuid.uuid4(), uuid.uuid4(), uuid.uuid4())

        db.execute.assert_awaited_once()
        db.flush.assert_awaited_once()


# ── delete_for_tenant ────────────────────────────────────────────────────────


class TestDeleteForTenant:
    @pytest.mark.asyncio
    async def test_returns_rowcount(self, db, repo):
        delete_result = MagicMock()
        delete_result.rowcount = 7
        db.execute = AsyncMock(return_value=delete_result)

        count = await repo.delete_for_tenant(db, uuid.uuid4())
        assert count == 7

    @pytest.mark.asyncio
    async def test_returns_zero_when_rowcount_none(self, db, repo):
        delete_result = MagicMock()
        delete_result.rowcount = None
        db.execute = AsyncMock(return_value=delete_result)

        count = await repo.delete_for_tenant(db, uuid.uuid4())
        assert count == 0


# ── find_platform_tenant_id ──────────────────────────────────────────────────


class TestFindPlatformTenantId:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        tenant_id = uuid.uuid4()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant_id))

        result = await repo.find_platform_tenant_id(db)
        assert result == tenant_id

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_platform_tenant_id(db)
        assert result is None
