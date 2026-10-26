# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for mailler.database module."""

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch


class TestGetDb:
    """Tests for get_db async generator."""

    async def test_yields_session_and_closes(self):
        mock_session = AsyncMock()
        mock_session.close = AsyncMock()

        # AsyncSessionLocal() returns a context manager
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("mailler.database.AsyncSessionLocal", return_value=mock_cm):
            from mailler.database import get_db

            gen = get_db()
            session = await gen.__anext__()
            assert session is mock_session

            # Cleanup
            with contextlib.suppress(StopAsyncIteration):
                await gen.__anext__()

            mock_session.close.assert_awaited_once()


class TestGetAsyncDb:
    """Tests for get_async_db async context manager."""

    async def test_yields_session_and_closes(self):
        mock_session = AsyncMock()
        mock_session.close = AsyncMock()

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("mailler.database.AsyncSessionLocal", return_value=mock_cm):
            from mailler.database import get_async_db

            async with get_async_db() as session:
                assert session is mock_session


class TestGetSyncDb:
    """Tests for get_sync_db sync context manager."""

    def test_yields_session_and_closes(self):
        mock_session = MagicMock()

        with patch("mailler.database.SyncSessionLocal", return_value=mock_session):
            from mailler.database import get_sync_db

            with get_sync_db() as session:
                assert session is mock_session

            mock_session.close.assert_called_once()

    def test_closes_session_on_exception(self):
        mock_session = MagicMock()

        with patch("mailler.database.SyncSessionLocal", return_value=mock_session):
            from mailler.database import get_sync_db

            try:
                with get_sync_db():
                    raise ValueError("test error")
            except ValueError:
                pass

            mock_session.close.assert_called_once()
