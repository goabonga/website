# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.repositories.token — TokenRepository (100% mocked)."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.db.repositories.token import TokenRepository

from tests.conftest import (
    make_access_token,
    make_execute_result,
    make_oauth2_client,
    make_refresh_token,
)


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
    return TokenRepository()


# ── find_access_token_by_id_for_client ───────────────────────────────────────


class TestFindAccessTokenByIdForClient:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        at = make_access_token()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=at))

        result = await repo.find_access_token_by_id_for_client(db, at.id, at.client_id)
        assert result is at

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_access_token_by_id_for_client(db, uuid.uuid4(), uuid.uuid4())
        assert result is None


# ── find_access_token_by_jti (+ revoked / active variants) ───────────────────


class TestFindAccessTokenByJti:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        at = make_access_token()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=at))

        result = await repo.find_access_token_by_jti(db, at.jti)
        assert result is at

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_access_token_by_jti(db, "missing")
        assert result is None


class TestFindRevokedAccessTokenByJti:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        at = make_access_token(revoked_at=datetime.now(UTC))
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=at))

        result = await repo.find_revoked_access_token_by_jti(db, at.jti)
        assert result is at

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_revoked_access_token_by_jti(db, "missing")
        assert result is None


class TestFindActiveAccessTokenByJti:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        at = make_access_token(revoked_at=None)
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=at))

        result = await repo.find_active_access_token_by_jti(db, at.jti)
        assert result is at

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_active_access_token_by_jti(db, "missing")
        assert result is None


# ── list_access_tokens_for_client / counts / search ──────────────────────────


class TestListAccessTokensForClient:
    @pytest.mark.asyncio
    async def test_returns_rows(self, db, repo):
        tokens = [make_access_token(), make_access_token()]
        db.execute = AsyncMock(return_value=make_list_result(tokens))

        result = await repo.list_access_tokens_for_client(db, uuid.uuid4())
        assert result == tokens

    @pytest.mark.asyncio
    async def test_without_eager_user(self, db, repo):
        tokens = [make_access_token()]
        db.execute = AsyncMock(return_value=make_list_result(tokens))

        result = await repo.list_access_tokens_for_client(db, uuid.uuid4(), eager_user=False)
        assert result == tokens


class TestCountAccessTokensForClient:
    @pytest.mark.asyncio
    async def test_returns_count(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=7))
        assert await repo.count_access_tokens_for_client(db, uuid.uuid4()) == 7

    @pytest.mark.asyncio
    async def test_zero_when_none(self, db, repo):
        res = MagicMock()
        res.scalar.return_value = None
        db.execute = AsyncMock(return_value=res)
        assert await repo.count_access_tokens_for_client(db, uuid.uuid4()) == 0


class TestCountActiveAccessTokensForClient:
    @pytest.mark.asyncio
    async def test_returns_count(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=3))
        assert (
            await repo.count_active_access_tokens_for_client(
                db, uuid.uuid4(), now=datetime.now(UTC)
            )
            == 3
        )


class TestCountRevokedAccessTokensForClient:
    @pytest.mark.asyncio
    async def test_returns_count(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=2))
        assert await repo.count_revoked_access_tokens_for_client(db, uuid.uuid4()) == 2


class TestCountExpiredAccessTokensForClient:
    @pytest.mark.asyncio
    async def test_returns_count(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=5))
        assert (
            await repo.count_expired_access_tokens_for_client(
                db, uuid.uuid4(), now=datetime.now(UTC)
            )
            == 5
        )


class TestSearchAccessTokensForClient:
    @pytest.mark.asyncio
    async def test_no_filters(self, db, repo):
        tokens = [make_access_token()]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=1),
                make_list_result(tokens),
            ]
        )
        rows, total = await repo.search_access_tokens_for_client(
            db, uuid.uuid4(), now=datetime.now(UTC)
        )
        assert rows == tokens
        assert total == 1

    @pytest.mark.asyncio
    async def test_status_active(self, db, repo):
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=0),
                make_list_result([]),
            ]
        )
        rows, total = await repo.search_access_tokens_for_client(
            db, uuid.uuid4(), status_filter="active", now=datetime.now(UTC)
        )
        assert rows == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_status_revoked(self, db, repo):
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=0),
                make_list_result([]),
            ]
        )
        rows, total = await repo.search_access_tokens_for_client(
            db, uuid.uuid4(), status_filter="revoked", now=datetime.now(UTC)
        )
        assert total == 0

    @pytest.mark.asyncio
    async def test_status_expired(self, db, repo):
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=0),
                make_list_result([]),
            ]
        )
        rows, total = await repo.search_access_tokens_for_client(
            db, uuid.uuid4(), status_filter="expired", now=datetime.now(UTC)
        )
        assert total == 0

    @pytest.mark.asyncio
    async def test_with_user_ids_empty(self, db, repo):
        """Empty user_ids list -> no rows."""
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=0),
                make_list_result([]),
            ]
        )
        rows, total = await repo.search_access_tokens_for_client(
            db, uuid.uuid4(), user_ids=[], now=datetime.now(UTC)
        )
        assert rows == []

    @pytest.mark.asyncio
    async def test_with_user_ids_populated(self, db, repo):
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=1),
                make_list_result([make_access_token()]),
            ]
        )
        rows, total = await repo.search_access_tokens_for_client(
            db, uuid.uuid4(), user_ids=[uuid.uuid4()], now=datetime.now(UTC)
        )
        assert total == 1

    @pytest.mark.asyncio
    async def test_with_scope_filter(self, db, repo):
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=1),
                make_list_result([make_access_token()]),
            ]
        )
        rows, total = await repo.search_access_tokens_for_client(
            db, uuid.uuid4(), scope_filter="openid", now=datetime.now(UTC)
        )
        assert total == 1


class TestListDistinctScopesForClient:
    @pytest.mark.asyncio
    async def test_returns_sorted(self, db, repo):
        db.execute = AsyncMock(
            return_value=make_execute_result(all_rows=[("profile",), ("openid",)])
        )
        result = await repo.list_distinct_scopes_for_client(db, uuid.uuid4())
        assert result == ["openid", "profile"]


class TestListActiveAccessTokensForClient:
    @pytest.mark.asyncio
    async def test_returns_tokens(self, db, repo):
        tokens = [make_access_token()]
        db.execute = AsyncMock(return_value=make_list_result(tokens))
        result = await repo.list_active_access_tokens_for_client(
            db, uuid.uuid4(), now=datetime.now(UTC)
        )
        assert result == tokens


class TestListActiveAccessTokensForUserClient:
    @pytest.mark.asyncio
    async def test_returns_tokens(self, db, repo):
        tokens = [make_access_token(), make_access_token()]
        db.execute = AsyncMock(return_value=make_list_result(tokens))
        result = await repo.list_active_access_tokens_for_user_client(
            db, uuid.uuid4(), uuid.uuid4()
        )
        assert result == tokens


# ── aggregate_authorized_clients_for_user ────────────────────────────────────


class TestAggregateAuthorizedClientsForUser:
    @pytest.mark.asyncio
    async def test_returns_rows(self, db, repo):
        row = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(all_rows=[row]))

        result = await repo.aggregate_authorized_clients_for_user(
            db, uuid.uuid4(), now=datetime.now(UTC)
        )
        assert result == [row]


class TestFindLatestActiveScopes:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=["openid"]))

        result = await repo.find_latest_active_scopes(
            db, uuid.uuid4(), uuid.uuid4(), now=datetime.now(UTC)
        )
        assert result == ["openid"]

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_latest_active_scopes(
            db, uuid.uuid4(), uuid.uuid4(), now=datetime.now(UTC)
        )
        assert result is None


# ── access-token writes ──────────────────────────────────────────────────────


class TestAddAccessToken:
    @pytest.mark.asyncio
    async def test_adds_and_flushes(self, db, repo):
        at = make_access_token()

        await repo.add_access_token(db, at)

        db.add.assert_called_once_with(at)
        db.flush.assert_awaited_once()


class TestRevokeAccessTokensForRefreshCascade:
    @pytest.mark.asyncio
    async def test_executes_update(self, db, repo):
        db.execute = AsyncMock()
        await repo.revoke_access_tokens_for_refresh_cascade(
            db,
            client_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            now=datetime.now(UTC),
        )
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_with_null_user(self, db, repo):
        db.execute = AsyncMock()
        await repo.revoke_access_tokens_for_refresh_cascade(
            db,
            client_id=uuid.uuid4(),
            user_id=None,
            now=datetime.now(UTC),
        )
        db.execute.assert_awaited_once()


# ── refresh-token reads ──────────────────────────────────────────────────────


class TestListRefreshTokensForAccessToken:
    @pytest.mark.asyncio
    async def test_returns_tokens(self, db, repo):
        tokens = [make_refresh_token()]
        db.execute = AsyncMock(return_value=make_list_result(tokens))

        result = await repo.list_refresh_tokens_for_access_token(db, uuid.uuid4())
        assert result == tokens


class TestListActiveRefreshTokensForClient:
    @pytest.mark.asyncio
    async def test_returns_tokens(self, db, repo):
        tokens = [make_refresh_token()]
        db.execute = AsyncMock(return_value=make_list_result(tokens))

        result = await repo.list_active_refresh_tokens_for_client(
            db, uuid.uuid4(), now=datetime.now(UTC)
        )
        assert result == tokens


class TestListActiveRefreshTokensForUserClient:
    @pytest.mark.asyncio
    async def test_returns_tokens(self, db, repo):
        tokens = [make_refresh_token()]
        db.execute = AsyncMock(return_value=make_list_result(tokens))

        result = await repo.list_active_refresh_tokens_for_user_client(
            db, uuid.uuid4(), uuid.uuid4()
        )
        assert result == tokens


class TestFindRefreshTokenByHash:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        rt = make_refresh_token()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=rt))

        result = await repo.find_refresh_token_by_hash(db, "hash-1")
        assert result is rt

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_refresh_token_by_hash(db, "missing")
        assert result is None


class TestFindValidRefreshTokenByHash:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        rt = make_refresh_token(
            revoked_at=None, used_at=None, expires_at=datetime.now(UTC) + timedelta(days=1)
        )
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=rt))

        result = await repo.find_valid_refresh_token_by_hash(db, "hash-1", now=datetime.now(UTC))
        assert result is rt

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_valid_refresh_token_by_hash(db, "missing", now=datetime.now(UTC))
        assert result is None


# ── refresh-token writes ─────────────────────────────────────────────────────


class TestAddRefreshToken:
    @pytest.mark.asyncio
    async def test_adds_and_flushes(self, db, repo):
        rt = make_refresh_token()

        await repo.add_refresh_token(db, rt)

        db.add.assert_called_once_with(rt)
        db.flush.assert_awaited_once()


# ── OAuth2 client lookup helpers ─────────────────────────────────────────────


class TestFindClientByStringId:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        client = make_oauth2_client()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=client))

        result = await repo.find_client_by_string_id(db, "client-1")
        assert result is client

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_client_by_string_id(db, "missing")
        assert result is None


class TestFindClientsByIds:
    @pytest.mark.asyncio
    async def test_returns_clients(self, db, repo):
        clients = [make_oauth2_client(), make_oauth2_client()]
        db.execute = AsyncMock(return_value=make_list_result(clients))

        result = await repo.find_clients_by_ids(db, [uuid.uuid4(), uuid.uuid4()])
        assert result == clients

    @pytest.mark.asyncio
    async def test_empty_shortcircuits(self, db, repo):
        """Empty ID list returns [] without hitting the DB."""
        db.execute = AsyncMock()
        result = await repo.find_clients_by_ids(db, [])
        assert result == []
        db.execute.assert_not_called()


# ── user email search ────────────────────────────────────────────────────────


class TestListUserIdsByEmailSearch:
    @pytest.mark.asyncio
    async def test_returns_ids(self, db, repo):
        uid = uuid.uuid4()
        db.execute = AsyncMock(return_value=make_execute_result(all_rows=[(uid,)]))

        result = await repo.list_user_ids_by_email_search(db, "alice")
        assert result == [uid]
