# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for the database session dependency in knowledge/database.py.

The session factory is mocked: no database is needed.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestGetDb:
    """Test the get_db async generator for both success and error paths."""

    async def test_get_db_yields_session_and_commits(self):
        """Happy path: session is yielded and committed."""
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        # Create a mock session factory that returns an async context manager
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("knowledge.database.async_session_factory", mock_factory):
            from knowledge.database import get_db

            gen = get_db()
            session = await gen.__anext__()
            assert session is mock_session

            # Simulate normal exit (StopAsyncIteration expected)
            with pytest.raises(StopAsyncIteration):
                await gen.__anext__()

            mock_session.commit.assert_awaited_once()
            mock_session.rollback.assert_not_awaited()

    async def test_get_db_rolls_back_on_exception(self):
        """Error path: session rolls back and re-raises exception."""
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock(side_effect=RuntimeError("db error"))
        mock_session.rollback = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("knowledge.database.async_session_factory", mock_factory):
            from knowledge.database import get_db

            gen = get_db()
            session = await gen.__anext__()
            assert session is mock_session

            # The commit raises, so the generator should rollback and re-raise
            with pytest.raises(RuntimeError, match="db error"):
                await gen.__anext__()

            mock_session.rollback.assert_awaited_once()
