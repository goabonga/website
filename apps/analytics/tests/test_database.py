# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for analytics.database module."""

import importlib
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _import_database_module():
    """Import analytics.database, mocking asyncpg if not available.

    The module creates an engine at import time, which requires
    asyncpg. If asyncpg is not installed, we mock it so the module
    can be imported successfully for testing.
    """
    if "analytics.database" in sys.modules:
        return sys.modules["analytics.database"]

    try:
        import asyncpg  # noqa: F401

        return importlib.import_module("analytics.database")
    except ImportError:
        # asyncpg not available, mock it for import
        mock_asyncpg = MagicMock()
        with patch.dict(sys.modules, {"asyncpg": mock_asyncpg}):
            if "analytics.database" in sys.modules:
                del sys.modules["analytics.database"]
            mod = importlib.import_module("analytics.database")
            return mod


database_mod = _import_database_module()
get_async_database_url = database_mod.get_async_database_url


class TestGetAsyncDatabaseUrl:
    """Tests for get_async_database_url function."""

    def test_converts_postgres_url(self):
        url = "postgres://user:pass@host:5432/db"
        result = get_async_database_url(url)
        assert result == "postgresql+asyncpg://user:pass@host:5432/db"

    def test_converts_postgresql_url(self):
        url = "postgresql://user:pass@host:5432/db"
        result = get_async_database_url(url)
        assert result == "postgresql+asyncpg://user:pass@host:5432/db"

    def test_keeps_asyncpg_url(self):
        url = "postgresql+asyncpg://user:pass@host:5432/db"
        result = get_async_database_url(url)
        assert result == "postgresql+asyncpg://user:pass@host:5432/db"

    def test_keeps_sqlite_url(self):
        url = "sqlite+aiosqlite:///./test.db"
        result = get_async_database_url(url)
        assert result == "sqlite+aiosqlite:///./test.db"


class TestGetDb:
    """Tests for get_db async generator (lines 33-39)."""

    @pytest.mark.asyncio
    async def test_get_db_yields_session(self):
        """get_db should yield a session from async_session_maker."""
        mock_session = AsyncMock(name="session")

        # Create an async context manager mock
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_session
        mock_context.__aexit__.return_value = False

        mock_session_maker = MagicMock(return_value=mock_context)

        with patch.object(database_mod, "async_session_maker", mock_session_maker):
            gen = database_mod.get_db()
            session = await gen.__anext__()
            assert session is mock_session

            # Exhaust the generator to trigger the finally block
            with pytest.raises(StopAsyncIteration):
                await gen.__anext__()

        # Verify session.close() was called in the finally block
        mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_db_closes_session_on_exception(self):
        """get_db should close the session even when an exception occurs."""
        mock_session = AsyncMock(name="session")

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_session
        mock_context.__aexit__.return_value = False

        mock_session_maker = MagicMock(return_value=mock_context)

        with patch.object(database_mod, "async_session_maker", mock_session_maker):
            gen = database_mod.get_db()
            session = await gen.__anext__()
            assert session is mock_session

            # Throw an exception into the generator
            with pytest.raises(ValueError):
                await gen.athrow(ValueError("test error"))

        # Session should still be closed
        mock_session.close.assert_awaited_once()
