# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.repositories.client — OAuth2ClientRepository (100% mocked)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.db.repositories.client import OAuth2ClientRepository

from tests.conftest import make_execute_result, make_oauth2_client


def make_list_result(rows: list) -> MagicMock:
    """Build a Result mock where ``.scalars().all()`` returns ``rows``."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    result.scalars.return_value = scalars
    return result


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def repo():
    return OAuth2ClientRepository()


# ── find_by_id ───────────────────────────────────────────────────────────────


class TestFindById:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        client = make_oauth2_client()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=client))

        result = await repo.find_by_id(db, client.id)
        assert result is client

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_by_id(db, uuid.uuid4())
        assert result is None


# ── find_by_client_id ────────────────────────────────────────────────────────


class TestFindByClientId:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        client = make_oauth2_client(client_id="public_id")
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=client))

        result = await repo.find_by_client_id(db, "public_id")
        assert result is client

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_by_client_id(db, "missing")
        assert result is None


# ── list ─────────────────────────────────────────────────────────────────────


class TestList:
    @pytest.mark.asyncio
    async def test_returns_items_and_total(self, db, repo):
        clients = [make_oauth2_client(), make_oauth2_client(), make_oauth2_client()]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=3),
                make_list_result(clients),
            ]
        )

        items, total = await repo.list(db, page=1, page_size=20)

        assert items == clients
        assert total == 3
        assert db.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_empty(self, db, repo):
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=0),
                make_list_result([]),
            ]
        )

        items, total = await repo.list(db)

        assert items == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_pagination_offset_computed(self, db, repo):
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=50),
                make_list_result([]),
            ]
        )

        items, total = await repo.list(db, page=3, page_size=10)

        assert items == []
        assert total == 50

    @pytest.mark.asyncio
    async def test_with_tenant_filter(self, db, repo):
        tid = uuid.uuid4()
        clients = [make_oauth2_client()]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=1),
                make_list_result(clients),
            ]
        )

        items, total = await repo.list(db, tenant_id=tid)

        assert items == clients
        assert total == 1

    @pytest.mark.asyncio
    async def test_filter_no_tenant(self, db, repo):
        clients = [make_oauth2_client()]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=1),
                make_list_result(clients),
            ]
        )

        items, total = await repo.list(db, filter_no_tenant=True)

        assert items == clients
        assert total == 1

    @pytest.mark.asyncio
    async def test_filter_no_tenant_overrides_tenant_id(self, db, repo):
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=0),
                make_list_result([]),
            ]
        )

        items, total = await repo.list(db, filter_no_tenant=True, tenant_id=uuid.uuid4())

        assert items == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_with_search(self, db, repo):
        clients = [make_oauth2_client(name="My App")]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=1),
                make_list_result(clients),
            ]
        )

        items, total = await repo.list(db, search="my")

        assert items == clients
        assert total == 1

    @pytest.mark.asyncio
    async def test_all_filters_combined(self, db, repo):
        tid = uuid.uuid4()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=0),
                make_list_result([]),
            ]
        )

        items, total = await repo.list(
            db,
            page=2,
            page_size=5,
            tenant_id=tid,
            search="foo",
        )

        assert items == []
        assert total == 0


# ── add / delete ─────────────────────────────────────────────────────────────


class TestAdd:
    @pytest.mark.asyncio
    async def test_adds_and_flushes(self, db, repo):
        client = make_oauth2_client()

        await repo.add(db, client)

        db.add.assert_called_once_with(client)
        db.flush.assert_awaited_once()


class TestDelete:
    @pytest.mark.asyncio
    async def test_calls_db_delete(self, db, repo):
        client = make_oauth2_client()
        db.delete = AsyncMock()

        await repo.delete(db, client)

        db.delete.assert_awaited_once_with(client)


class TestFindScopedToTenant:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        client = make_oauth2_client()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=client))

        result = await repo.find_scoped_to_tenant(db, client.id, uuid.uuid4())

        assert result is client
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        assert await repo.find_scoped_to_tenant(db, uuid.uuid4(), uuid.uuid4()) is None


class TestCount:
    @pytest.mark.asyncio
    async def test_without_filter(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=12))

        assert await repo.count(db) == 12

    @pytest.mark.asyncio
    async def test_with_is_active_filter(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=3))

        assert await repo.count(db, is_active=True) == 3

    @pytest.mark.asyncio
    async def test_none_becomes_zero(self, db, repo):
        result = MagicMock()
        result.scalar.return_value = None
        db.execute = AsyncMock(return_value=result)

        assert await repo.count(db) == 0
