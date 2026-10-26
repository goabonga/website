# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/database.py."""

import contextlib

import pytest
from custom_domain.database import _get_async_url


class TestUrlConversion:
    """Tests for URL conversion functions."""

    def test_get_async_url(self):
        """Test converting to async URL."""
        url = "postgresql://user:pass@localhost/db"
        result = _get_async_url(url)
        assert result == "postgresql+asyncpg://user:pass@localhost/db"

    def test_get_async_url_local(self):
        """Test converting local URL to async."""
        url = "postgresql:///db"
        result = _get_async_url(url)
        assert result == "postgresql+asyncpg:///db"


class TestGetDbAsync:
    """Tests for get_db async dependency."""

    @pytest.mark.asyncio
    async def test_get_db_yields_and_closes_session(self):
        """Test get_db yields a session and closes it."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_session = AsyncMock()

        # Create a mock session factory
        mock_session_class = MagicMock()
        mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("custom_domain.database.AsyncSessionLocal", mock_session_class):
            from custom_domain.database import get_db

            # get_db is an async generator
            gen = get_db()
            session = await gen.__anext__()
            assert session is mock_session

            # Consume the rest of the generator
            with contextlib.suppress(StopAsyncIteration):
                await gen.__anext__()

            # Session close should be called
            mock_session.close.assert_called_once()


class TestGetAsyncDb:
    """Tests for get_async_db context manager."""

    @pytest.mark.asyncio
    async def test_get_async_db_yields_and_closes_session(self):
        """Test get_async_db yields a session and closes it."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_session = AsyncMock()

        # Create a mock session factory
        mock_session_class = MagicMock()
        mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("custom_domain.database.AsyncSessionLocal", mock_session_class):
            from custom_domain.database import get_async_db

            async with get_async_db() as session:
                assert session is mock_session

            mock_session.close.assert_called_once()


class TestPoolSettings:
    """The size of the connection pool is a setting."""

    def test_defaults(self):
        from custom_domain.config import Settings

        defaults = Settings(_env_file=None)
        assert defaults.database_pool_size == 5
        assert defaults.database_max_overflow == 10

    def test_engine_uses_the_settings(self, monkeypatch):
        import importlib

        from custom_domain import database
        from custom_domain.config import settings

        monkeypatch.setattr(settings, "database_pool_size", 3)
        monkeypatch.setattr(settings, "database_max_overflow", 4)
        reloaded = importlib.reload(database)
        try:
            assert reloaded.async_engine.pool.size() == 3
            assert reloaded.async_engine.pool._max_overflow == 4
        finally:
            monkeypatch.undo()
            importlib.reload(database)
