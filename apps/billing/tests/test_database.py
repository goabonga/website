# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for billing/database.py."""

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestGetDb:
    """Tests for the get_db() async generator."""

    async def test_yields_session_and_commits_on_success(self):
        """Should yield a session and commit when no exception occurs."""
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        # Create a mock async context manager that returns our mock session
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock(return_value=mock_session_ctx)

        with patch("billing.database.async_session_factory", mock_factory):
            from billing.database import get_db

            gen = get_db()
            session = await gen.__anext__()

            assert session is mock_session

            # Simulate FastAPI completing the request successfully
            with contextlib.suppress(StopAsyncIteration):
                await gen.__anext__()

            mock_session.commit.assert_awaited_once()
            mock_session.rollback.assert_not_awaited()

    async def test_rollbacks_on_exception(self):
        """Should rollback the session when an exception occurs during request."""
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock(side_effect=Exception("DB error"))
        mock_session.rollback = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock(return_value=mock_session_ctx)

        with patch("billing.database.async_session_factory", mock_factory):
            from billing.database import get_db

            gen = get_db()
            session = await gen.__anext__()

            assert session is mock_session

            # The commit will raise, triggering rollback
            with pytest.raises(Exception, match="DB error"):
                await gen.__anext__()

            mock_session.rollback.assert_awaited_once()

    async def test_session_is_async_context_managed(self):
        """Should use async context manager pattern for session lifecycle."""
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock(return_value=mock_session_ctx)

        with patch("billing.database.async_session_factory", mock_factory):
            from billing.database import get_db

            gen = get_db()
            await gen.__anext__()

            # Verify factory was called to create a session context
            mock_factory.assert_called_once()
            # Verify __aenter__ was called
            mock_session_ctx.__aenter__.assert_awaited_once()
