# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.repositories.catalog — reads and staging for the catalog sync."""

from unittest.mock import AsyncMock, MagicMock

from auth.db.repositories.catalog import CatalogRepository

from tests.conftest import make_execute_result


def named(name):
    item = MagicMock()
    item.name = name
    return item


class TestCatalogRepository:
    async def test_scopes_are_keyed_by_name(self, db):
        db.execute = AsyncMock(
            return_value=make_execute_result(scalars_list=[named("a:read"), named("b:read")])
        )
        assert set(await CatalogRepository().scopes_by_name(db)) == {"a:read", "b:read"}

    async def test_roles_are_keyed_by_name(self, db):
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=[named("viewer")]))
        assert set(await CatalogRepository().roles_by_name(db)) == {"viewer"}

    async def test_find_client(self, db):
        client = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=client))
        assert await CatalogRepository().find_client(db, "kb") is client

    async def test_find_missing_client(self, db):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        assert await CatalogRepository().find_client(db, "kb") is None

    async def test_add_stages_and_flushes(self, db):
        row = MagicMock()
        await CatalogRepository().add(db, row)
        db.add.assert_called_once_with(row)
        db.flush.assert_awaited_once()
