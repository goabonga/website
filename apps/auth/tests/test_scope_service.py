# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.scope — ScopeService read passthroughs (repository mocked)."""

import uuid
from unittest.mock import AsyncMock

import pytest
from auth.services.scope import ScopeService


@pytest.fixture
def repo():
    return AsyncMock()


@pytest.fixture
def service(repo):
    return ScopeService(repository=repo)


@pytest.fixture
def db():
    return AsyncMock()


class TestGetByName:
    @pytest.mark.asyncio
    async def test_found(self, db, repo, service):
        scope = object()
        repo.find_by_name.return_value = scope

        assert await service.get_by_name(db, "users:read") is scope
        repo.find_by_name.assert_awaited_once_with(db, "users:read")

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo, service):
        repo.find_by_name.return_value = None

        assert await service.get_by_name(db, "nope") is None


class TestListDistinctCategories:
    @pytest.mark.asyncio
    async def test_delegates_to_repository(self, db, repo, service):
        repo.list_distinct_categories.return_value = ["identity", "admin"]

        assert await service.list_distinct_categories(db) == ["identity", "admin"]
        repo.list_distinct_categories.assert_awaited_once_with(db)


class TestCountRolesForScope:
    @pytest.mark.asyncio
    async def test_delegates_to_repository(self, db, repo, service):
        repo.count_roles_for_scope.return_value = 3
        scope_id = uuid.uuid4()

        assert await service.count_roles_for_scope(db, scope_id) == 3
        repo.count_roles_for_scope.assert_awaited_once_with(db, scope_id)


class TestListRolesForScope:
    @pytest.mark.asyncio
    async def test_delegates_to_repository(self, db, repo, service):
        roles = [object(), object()]
        repo.list_roles_for_scope.return_value = roles
        scope_id = uuid.uuid4()

        assert await service.list_roles_for_scope(db, scope_id) == roles
        repo.list_roles_for_scope.assert_awaited_once_with(db, scope_id)
