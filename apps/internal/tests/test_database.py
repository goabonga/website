# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for database URL conversion functions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from internal.database import get_async_database_url, get_sync_database_url


class TestGetAsyncDatabaseUrl:
    def test_postgres_prefix(self):
        assert get_async_database_url("postgres://user:pass@host/db") == (
            "postgresql+asyncpg://user:pass@host/db"
        )

    def test_postgresql_prefix(self):
        assert get_async_database_url("postgresql://user:pass@host/db") == (
            "postgresql+asyncpg://user:pass@host/db"
        )

    def test_already_async(self):
        url = "postgresql+asyncpg://user:pass@host/db"
        assert get_async_database_url(url) == url

    def test_other_scheme_unchanged(self):
        url = "sqlite:///./app.db"
        assert get_async_database_url(url) == url


class TestGetSyncDatabaseUrl:
    def test_postgres_prefix(self):
        assert get_sync_database_url("postgres://user:pass@host/db") == (
            "postgresql+psycopg://user:pass@host/db"
        )

    def test_asyncpg_driver_url_passes_through(self):
        # "postgresql+asyncpg://" doesn't startswith("postgresql://"), so passes through
        url = "postgresql+asyncpg://user:pass@host/db"
        assert get_sync_database_url(url) == url

    def test_postgresql_with_asyncpg_in_url(self):
        # Covers elif branch: startswith("postgresql://") and "+asyncpg" in url
        # replace() doesn't find "postgresql+asyncpg://" substring, so URL unchanged
        url = "postgresql://user+asyncpg@host/db"
        assert get_sync_database_url(url) == "postgresql://user+asyncpg@host/db"

    def test_postgresql_prefix(self):
        assert get_sync_database_url("postgresql://user:pass@host/db") == (
            "postgresql+psycopg://user:pass@host/db"
        )

    def test_already_sync(self):
        url = "postgresql+psycopg://user:pass@host/db"
        assert get_sync_database_url(url) == url


class TestGetDb:
    @pytest.mark.asyncio
    async def test_yields_session_and_closes(self):
        mock_session = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("internal.database.async_session_maker", mock_session_maker):
            from internal.database import get_db

            gen = get_db()
            session = await gen.__anext__()
            assert session is mock_session
            with pytest.raises(StopAsyncIteration):
                await gen.__anext__()


class TestGetSyncDbSession:
    def test_yields_session_and_closes(self):
        mock_session = MagicMock()
        mock_maker = MagicMock(return_value=mock_session)

        with patch("internal.database.sync_session_maker", mock_maker):
            from internal.database import get_sync_db_session

            with get_sync_db_session() as session:
                assert session is mock_session
            mock_session.close.assert_called_once()
