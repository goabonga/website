# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.repositories.webhook — WebhookRepository (100% mocked)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.db.repositories.webhook import WebhookRepository

from tests.conftest import make_execute_result


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
    return WebhookRepository()


class TestFindForTenant:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        webhook = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=webhook))

        result = await repo.find_for_tenant(db, uuid.uuid4(), uuid.uuid4())

        assert result is webhook
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        assert await repo.find_for_tenant(db, uuid.uuid4(), uuid.uuid4()) is None


class TestListMatchingSubscribed:
    @pytest.mark.asyncio
    async def test_returns_rows(self, db, repo):
        hooks = [MagicMock(), MagicMock()]
        db.execute = AsyncMock(return_value=make_list_result(hooks))

        result = await repo.list_matching_subscribed(db, uuid.uuid4(), ["user.*", "user.created"])

        assert result == hooks
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty(self, db, repo):
        db.execute = AsyncMock(return_value=make_list_result([]))

        assert await repo.list_matching_subscribed(db, uuid.uuid4(), ["user.*"]) == []


class TestCountByTenant:
    @pytest.mark.asyncio
    async def test_returns_count(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=7))

        assert await repo.count_by_tenant(db, uuid.uuid4()) == 7

    @pytest.mark.asyncio
    async def test_none_becomes_zero(self, db, repo):
        result = MagicMock()
        result.scalar.return_value = None
        db.execute = AsyncMock(return_value=result)

        assert await repo.count_by_tenant(db, uuid.uuid4()) == 0


class TestListByTenant:
    @pytest.mark.asyncio
    async def test_returns_rows(self, db, repo):
        hooks = [MagicMock()]
        db.execute = AsyncMock(return_value=make_list_result(hooks))

        assert await repo.list_by_tenant(db, uuid.uuid4(), offset=20, limit=10) == hooks

    @pytest.mark.asyncio
    async def test_default_pagination(self, db, repo):
        db.execute = AsyncMock(return_value=make_list_result([]))

        assert await repo.list_by_tenant(db, uuid.uuid4()) == []


class TestListAllByTenant:
    @pytest.mark.asyncio
    async def test_returns_rows(self, db, repo):
        hooks = [MagicMock(), MagicMock(), MagicMock()]
        db.execute = AsyncMock(return_value=make_list_result(hooks))

        assert await repo.list_all_by_tenant(db, uuid.uuid4()) == hooks

    @pytest.mark.asyncio
    async def test_empty(self, db, repo):
        db.execute = AsyncMock(return_value=make_list_result([]))

        assert await repo.list_all_by_tenant(db, uuid.uuid4()) == []


class TestListRecentDeliveries:
    @pytest.mark.asyncio
    async def test_returns_rows(self, db, repo):
        deliveries = [MagicMock()]
        db.execute = AsyncMock(return_value=make_list_result(deliveries))

        assert await repo.list_recent_deliveries(db, uuid.uuid4(), limit=5) == deliveries

    @pytest.mark.asyncio
    async def test_default_limit(self, db, repo):
        db.execute = AsyncMock(return_value=make_list_result([]))

        assert await repo.list_recent_deliveries(db, uuid.uuid4()) == []


class TestCountDeliveries:
    @pytest.mark.asyncio
    async def test_returns_count(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=42))

        assert await repo.count_deliveries(db, uuid.uuid4()) == 42

    @pytest.mark.asyncio
    async def test_none_becomes_zero(self, db, repo):
        result = MagicMock()
        result.scalar.return_value = None
        db.execute = AsyncMock(return_value=result)

        assert await repo.count_deliveries(db, uuid.uuid4()) == 0


class TestListDeliveries:
    @pytest.mark.asyncio
    async def test_returns_rows(self, db, repo):
        deliveries = [MagicMock(), MagicMock()]
        db.execute = AsyncMock(return_value=make_list_result(deliveries))

        assert await repo.list_deliveries(db, uuid.uuid4(), offset=10, limit=5) == deliveries

    @pytest.mark.asyncio
    async def test_default_pagination(self, db, repo):
        db.execute = AsyncMock(return_value=make_list_result([]))

        assert await repo.list_deliveries(db, uuid.uuid4()) == []


class TestFindDeliveryForWebhook:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        delivery = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=delivery))

        assert await repo.find_delivery_for_webhook(db, uuid.uuid4(), uuid.uuid4()) is delivery

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        assert await repo.find_delivery_for_webhook(db, uuid.uuid4(), uuid.uuid4()) is None


class TestWrites:
    @pytest.mark.asyncio
    async def test_add_stages_and_flushes(self, db, repo):
        instance = MagicMock()

        await repo.add(db, instance)

        db.add.assert_called_once_with(instance)
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stage_does_not_flush(self, db, repo):
        instance = MagicMock()

        result = await repo.stage(db, instance)

        assert result is instance
        db.add.assert_called_once_with(instance)
        db.flush.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_calls_db_delete(self, db, repo):
        instance = MagicMock()

        await repo.delete(db, instance)

        db.delete.assert_awaited_once_with(instance)

    @pytest.mark.asyncio
    async def test_flush(self, db, repo):
        await repo.flush(db)

        db.flush.assert_awaited_once()
