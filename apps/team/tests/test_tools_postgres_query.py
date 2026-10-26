# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for postgres_query tool."""

from unittest.mock import AsyncMock, MagicMock, patch

import team.services.tools  # noqa: F401
from team.services.tool_service import ToolService
from team.services.tools.postgres_query import _asyncpg_dsn, _validate_query


class TestValidateQuery:
    def test_valid_select(self):
        assert _validate_query("SELECT * FROM users") is None

    def test_valid_select_with_semicolon(self):
        assert _validate_query("SELECT id FROM teams;") is None

    def test_valid_select_lowercase(self):
        assert _validate_query("select count(*) from agents") is None

    def test_rejects_insert(self):
        assert _validate_query("INSERT INTO users VALUES (1)") is not None

    def test_rejects_update(self):
        assert _validate_query("UPDATE users SET name='x'") is not None

    def test_rejects_delete(self):
        assert _validate_query("DELETE FROM users") is not None

    def test_rejects_drop(self):
        assert _validate_query("DROP TABLE users") is not None

    def test_rejects_alter(self):
        assert _validate_query("ALTER TABLE users ADD COLUMN x int") is not None

    def test_rejects_create(self):
        assert _validate_query("CREATE TABLE evil (id int)") is not None

    def test_rejects_truncate(self):
        assert _validate_query("TRUNCATE users") is not None

    def test_rejects_grant(self):
        assert _validate_query("GRANT ALL ON users TO evil") is not None

    def test_rejects_revoke(self):
        assert _validate_query("REVOKE ALL ON users FROM evil") is not None

    def test_rejects_select_with_embedded_delete(self):
        result = _validate_query("SELECT * FROM users; DELETE FROM users")
        assert result is not None

    def test_rejects_non_select(self):
        result = _validate_query("EXPLAIN SELECT * FROM users")
        assert result is not None


class TestAsyncpgDsn:
    def test_converts_sqlalchemy_to_asyncpg(self):
        result = _asyncpg_dsn("postgresql+asyncpg://user:pass@host/db")
        assert result == "postgresql://user:pass@host/db"

    def test_no_change_if_already_plain(self):
        result = _asyncpg_dsn("postgresql://user@host/db")
        assert result == "postgresql://user@host/db"


class TestPostgresQuery:
    async def test_query_success(self):
        mock_conn = AsyncMock()
        mock_row = MagicMock()
        mock_row.__iter__ = MagicMock(return_value=iter([("id", 1), ("name", "test")]))
        mock_row.items.return_value = [("id", 1), ("name", "test")]

        record = MagicMock()
        record.items.return_value = [("id", 1), ("name", "test")]
        # asyncpg Records support dict()
        record.__iter__ = MagicMock(return_value=iter(["id", "name"]))
        record.keys.return_value = ["id", "name"]
        record.__getitem__ = lambda self, key: {"id": 1, "name": "test"}[key]

        # Mock dict(row) behavior
        mock_records = [{"id": 1, "name": "test"}]
        mock_conn.fetch = AsyncMock(return_value=mock_records)
        mock_conn.close = AsyncMock()

        with (
            patch(
                "team.services.tools.postgres_query.asyncpg.connect", new_callable=AsyncMock
            ) as mock_connect,
            patch("team.services.tools.postgres_query.get_settings") as mock_settings,
        ):
            mock_connect.return_value = mock_conn
            mock_settings.return_value.database_url = "postgresql+asyncpg://user@host/db"

            result = await ToolService._registry["postgres_query"][0](
                {"query": "SELECT * FROM users"},
                {},
            )
        assert result["count"] == 1
        assert result["truncated"] is False

    async def test_query_truncated(self):
        mock_conn = AsyncMock()
        # 101 rows — should truncate
        mock_conn.fetch = AsyncMock(return_value=[{"id": i} for i in range(101)])
        mock_conn.close = AsyncMock()

        with (
            patch(
                "team.services.tools.postgres_query.asyncpg.connect", new_callable=AsyncMock
            ) as mock_connect,
            patch("team.services.tools.postgres_query.get_settings") as mock_settings,
        ):
            mock_connect.return_value = mock_conn
            mock_settings.return_value.database_url = "postgresql+asyncpg://u@h/d"

            result = await ToolService._registry["postgres_query"][0](
                {"query": "SELECT * FROM big_table"},
                {},
            )
        assert result["count"] == 100
        assert result["truncated"] is True

    async def test_query_invalid_rejected(self):
        result = await ToolService._registry["postgres_query"][0](
            {"query": "DELETE FROM users"},
            {},
        )
        assert "error" in result
        assert "Only SELECT" in result["error"] or "forbidden" in result["error"].lower()

    async def test_query_non_select_rejected(self):
        result = await ToolService._registry["postgres_query"][0](
            {"query": "EXPLAIN ANALYZE SELECT 1"},
            {},
        )
        assert "error" in result
