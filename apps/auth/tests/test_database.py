# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.core.database — URL conversion and session management."""

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.core.database import get_async_database_url, get_sync_database_url

# ── get_async_database_url ─────────────────────────────────────────────────


class TestGetAsyncDatabaseUrl:
    def test_postgresql(self):
        result = get_async_database_url("postgresql://localhost/db")
        assert result == "postgresql+asyncpg://localhost/db"

    def test_postgres(self):
        result = get_async_database_url("postgres://localhost/db")
        assert result == "postgresql+asyncpg://localhost/db"

    def test_already_asyncpg(self):
        url = "postgresql+asyncpg://localhost/db"
        result = get_async_database_url(url)
        assert result == url

    def test_unknown_prefix(self):
        url = "sqlite:///test.db"
        result = get_async_database_url(url)
        assert result == url


# ── get_sync_database_url ──────────────────────────────────────────────────


class TestGetSyncDatabaseUrl:
    def test_asyncpg_to_psycopg2(self):
        result = get_sync_database_url("postgresql+asyncpg://localhost/db")
        assert result == "postgresql+psycopg2://localhost/db"

    def test_postgresql(self):
        result = get_sync_database_url("postgresql://localhost/db")
        assert result == "postgresql+psycopg2://localhost/db"

    def test_postgres(self):
        result = get_sync_database_url("postgres://localhost/db")
        assert result == "postgresql+psycopg2://localhost/db"

    def test_unknown_prefix(self):
        url = "sqlite:///test.db"
        result = get_sync_database_url(url)
        assert result == url


# ── get_db ──────────────────────────────────────────────────────────────────


class TestGetDb:
    @pytest.mark.asyncio
    async def test_yields_session_and_commits(self):
        mock_session = AsyncMock()
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("auth.core.database.async_session_factory", mock_factory):
            from auth.core.database import get_db

            gen = get_db()
            session = await gen.__anext__()
            assert session is mock_session
            # Simulate successful completion
            with contextlib.suppress(StopAsyncIteration):
                await gen.__anext__()
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_rollback_on_error(self):
        mock_session = AsyncMock()
        mock_session.commit.side_effect = Exception("commit error")
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("auth.core.database.async_session_factory", mock_factory):
            from auth.core.database import get_db

            gen = get_db()
            await gen.__anext__()
            with pytest.raises(Exception, match="commit error"):
                await gen.__anext__()
            mock_session.rollback.assert_called_once()


# ── get_db_context ──────────────────────────────────────────────────────────


class TestGetDbContext:
    @pytest.mark.asyncio
    async def test_yields_session_and_commits(self):
        mock_session = AsyncMock()
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("auth.core.database.async_session_factory", mock_factory):
            from auth.core.database import get_db_context

            async with get_db_context() as session:
                assert session is mock_session
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_rollback_on_error(self):
        mock_session = AsyncMock()
        mock_session.commit.side_effect = Exception("fail")
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("auth.core.database.async_session_factory", mock_factory):
            from auth.core.database import get_db_context

            with pytest.raises(Exception, match="fail"):
                async with get_db_context() as _session:
                    pass  # Commit happens on exit
            mock_session.rollback.assert_called_once()


# ── check_database_connection ───────────────────────────────────────────────


class TestCheckDatabaseConnection:
    @pytest.mark.asyncio
    async def test_success(self):
        mock_session = AsyncMock()
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("auth.core.database.async_session_factory", mock_factory):
            from auth.core.database import check_database_connection

            result = await check_database_connection()
        assert result is True

    @pytest.mark.asyncio
    async def test_failure(self):
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(side_effect=Exception("conn error"))
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("auth.core.database.async_session_factory", mock_factory):
            from auth.core.database import check_database_connection

            result = await check_database_connection()
        assert result is False


# ── init_database ───────────────────────────────────────────────────────────


class TestInitDatabase:
    @pytest.mark.asyncio
    async def test_creates_tables(self):
        mock_conn = AsyncMock()
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_engine = MagicMock()
        mock_engine.begin.return_value = mock_ctx

        with patch("auth.core.database.engine", mock_engine):
            from auth.core.database import init_database

            await init_database()
        mock_conn.run_sync.assert_called_once()


# ── close_database ──────────────────────────────────────────────────────────


class TestCloseDatabase:
    @pytest.mark.asyncio
    async def test_disposes_engine(self):
        mock_engine = AsyncMock()

        with patch("auth.core.database.engine", mock_engine):
            from auth.core.database import close_database

            await close_database()
        mock_engine.dispose.assert_called_once()


# ── get_sync_db ─────────────────────────────────────────────────────────────


class TestGetSyncDb:
    def test_yields_session_and_commits(self):
        mock_session = MagicMock()
        mock_factory = MagicMock(return_value=mock_session)

        with patch("auth.core.database.sync_session_factory", mock_factory):
            from auth.core.database import get_sync_db

            with get_sync_db() as session:
                assert session is mock_session
            mock_session.commit.assert_called_once()
            mock_session.close.assert_called_once()

    def test_rollback_on_error(self):
        mock_session = MagicMock()
        mock_session.commit.side_effect = Exception("fail")
        mock_factory = MagicMock(return_value=mock_session)

        with patch("auth.core.database.sync_session_factory", mock_factory):
            from auth.core.database import get_sync_db

            with pytest.raises(Exception, match="fail"), get_sync_db() as _session:
                pass
            mock_session.rollback.assert_called_once()
            mock_session.close.assert_called_once()
