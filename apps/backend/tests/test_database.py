# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for backend.database.get_async_database_url."""

import contextlib

from backend.database import get_async_database_url


class TestGetAsyncDatabaseUrl:
    """Tests for get_async_database_url."""

    def test_converts_postgres_to_asyncpg(self):
        """postgres:// should be converted to postgresql+asyncpg://."""
        url = "postgres://user:pass@host:5432/dbname"
        result = get_async_database_url(url)
        assert result == "postgresql+asyncpg://user:pass@host:5432/dbname"

    def test_converts_postgresql_to_asyncpg(self):
        """postgresql:// should be converted to postgresql+asyncpg://."""
        url = "postgresql://user:pass@host:5432/dbname"
        result = get_async_database_url(url)
        assert result == "postgresql+asyncpg://user:pass@host:5432/dbname"

    def test_leaves_already_converted_asyncpg_unchanged(self):
        """postgresql+asyncpg:// should remain unchanged."""
        url = "postgresql+asyncpg://user:pass@host:5432/dbname"
        result = get_async_database_url(url)
        assert result == "postgresql+asyncpg://user:pass@host:5432/dbname"


class TestGetDb:
    """Tests for get_db async generator."""

    async def test_get_db_yields_session(self):
        """get_db() yields a session and closes it after use."""
        from unittest.mock import AsyncMock, patch

        mock_session = AsyncMock()
        mock_session.close = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.database.async_session_maker", return_value=mock_session_ctx):
            from backend.database import get_db

            gen = get_db()
            session = await gen.__anext__()

            assert session is mock_session

            # Exhaust the generator to trigger the finally block
            with contextlib.suppress(StopAsyncIteration):
                await gen.__anext__()

            mock_session.close.assert_awaited_once()
