# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.token_admin — TokenAdminService (repository mocked)."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from auth.services.token_admin import TokenAdminService


@pytest.fixture
def repo():
    return AsyncMock()


@pytest.fixture
def service(repo):
    return TokenAdminService(repository=repo)


@pytest.fixture
def db():
    return AsyncMock()


class TestCountRevokedAccessTokensForClient:
    @pytest.mark.asyncio
    async def test_delegates_to_repository(self, db, repo, service):
        repo.count_revoked_access_tokens_for_client.return_value = 4
        client_id = uuid.uuid4()

        assert await service.count_revoked_access_tokens_for_client(db, client_id) == 4
        repo.count_revoked_access_tokens_for_client.assert_awaited_once_with(db, client_id)


class TestCountExpiredAccessTokensForClient:
    @pytest.mark.asyncio
    async def test_delegates_to_repository(self, db, repo, service):
        repo.count_expired_access_tokens_for_client.return_value = 2
        client_id = uuid.uuid4()
        now = datetime.now(UTC)

        assert await service.count_expired_access_tokens_for_client(db, client_id, now=now) == 2
        repo.count_expired_access_tokens_for_client.assert_awaited_once_with(db, client_id, now=now)


class TestSearchAccessTokensForClient:
    @pytest.mark.asyncio
    async def test_forwards_every_filter(self, db, repo, service):
        rows = ([object()], 1)
        repo.search_access_tokens_for_client.return_value = rows
        client_id = uuid.uuid4()
        user_ids = [uuid.uuid4()]
        now = datetime.now(UTC)

        result = await service.search_access_tokens_for_client(
            db,
            client_id,
            page=3,
            page_size=50,
            status_filter="active",
            user_ids=user_ids,
            scope_filter="openid",
            now=now,
        )

        assert result == rows
        repo.search_access_tokens_for_client.assert_awaited_once_with(
            db,
            client_id,
            page=3,
            page_size=50,
            status_filter="active",
            user_ids=user_ids,
            scope_filter="openid",
            now=now,
        )

    @pytest.mark.asyncio
    async def test_defaults(self, db, repo, service):
        repo.search_access_tokens_for_client.return_value = ([], 0)

        await service.search_access_tokens_for_client(db, uuid.uuid4(), now=datetime.now(UTC))

        kwargs = repo.search_access_tokens_for_client.await_args.kwargs
        assert kwargs["page"] == 1
        assert kwargs["page_size"] == 20
        assert kwargs["status_filter"] is None
        assert kwargs["user_ids"] is None
        assert kwargs["scope_filter"] is None


class TestListDistinctScopesForClient:
    @pytest.mark.asyncio
    async def test_delegates_to_repository(self, db, repo, service):
        repo.list_distinct_scopes_for_client.return_value = ["openid", "profile"]
        client_id = uuid.uuid4()

        assert await service.list_distinct_scopes_for_client(db, client_id) == [
            "openid",
            "profile",
        ]
        repo.list_distinct_scopes_for_client.assert_awaited_once_with(db, client_id)


class TestListUserIdsByEmailSearch:
    @pytest.mark.asyncio
    async def test_delegates_to_repository(self, db, repo, service):
        ids = [uuid.uuid4()]
        repo.list_user_ids_by_email_search.return_value = ids

        assert await service.list_user_ids_by_email_search(db, "%@example.com") == ids
        repo.list_user_ids_by_email_search.assert_awaited_once_with(db, "%@example.com")


class TestSingleton:
    def test_module_singleton_is_a_service(self):
        from auth.services.token_admin import token_admin_service

        assert isinstance(token_admin_service, TokenAdminService)
