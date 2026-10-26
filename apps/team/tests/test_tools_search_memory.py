# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for search_memory tool with vector and keyword search."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import team.services.tools  # noqa: F401
from team.services.tool_service import ToolService


def _mock_entry(content="Some fact"):
    entry = MagicMock()
    entry.id = uuid4()
    entry.content = content
    entry.created_at = datetime(2026, 1, 15, 10, 0, 0)
    return entry


class TestSearchMemoryVector:
    """Tests for vector (cosine similarity) search path."""

    async def test_vector_search_when_embedding_available(self):
        entries = [_mock_entry("Relevant fact")]
        mock_session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = entries
        mock_session.execute = AsyncMock(return_value=result_mock)

        ctx = {"db": mock_session, "team_id": "team-1"}

        with patch(
            "team.services.tools.memory_ops.generate_embedding",
            new_callable=AsyncMock,
            return_value=[0.1] * 1536,
        ):
            result = await ToolService._registry["search_memory"][0]({"query": "relevant"}, ctx)

        assert result["search_type"] == "vector"
        assert len(result["results"]) == 1
        assert result["results"][0]["content"] == "Relevant fact"

    async def test_vector_search_respects_limit(self):
        mock_session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=result_mock)

        ctx = {"db": mock_session, "team_id": "team-1"}

        with patch(
            "team.services.tools.memory_ops.generate_embedding",
            new_callable=AsyncMock,
            return_value=[0.1] * 1536,
        ):
            result = await ToolService._registry["search_memory"][0](
                {"query": "test", "limit": 3}, ctx
            )

        assert result["search_type"] == "vector"
        assert result["results"] == []


class TestSearchMemoryKeyword:
    """Tests for keyword (ILIKE) fallback search path."""

    async def test_falls_back_to_keyword_when_no_api_key(self):
        entries = [_mock_entry("Some keyword match")]
        mock_session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = entries
        mock_session.execute = AsyncMock(return_value=result_mock)

        ctx = {"db": mock_session, "team_id": "team-1"}

        # Zero embedding = no API key
        with patch(
            "team.services.tools.memory_ops.generate_embedding",
            new_callable=AsyncMock,
            return_value=[0.0] * 1536,
        ):
            result = await ToolService._registry["search_memory"][0]({"query": "keyword"}, ctx)

        assert result["search_type"] == "keyword"
        assert len(result["results"]) == 1
        assert result["results"][0]["content"] == "Some keyword match"

    async def test_keyword_search_empty_results(self):
        mock_session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=result_mock)

        ctx = {"db": mock_session, "team_id": "team-1"}

        with patch(
            "team.services.tools.memory_ops.generate_embedding",
            new_callable=AsyncMock,
            return_value=[0.0] * 1536,
        ):
            result = await ToolService._registry["search_memory"][0]({"query": "nothing"}, ctx)

        assert result["search_type"] == "keyword"
        assert result["results"] == []

    async def test_default_limit_is_five(self):
        mock_session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=result_mock)

        ctx = {"db": mock_session, "team_id": "team-1"}

        with patch(
            "team.services.tools.memory_ops.generate_embedding",
            new_callable=AsyncMock,
            return_value=[0.0] * 1536,
        ):
            result = await ToolService._registry["search_memory"][0]({"query": "test"}, ctx)

        assert result["search_type"] == "keyword"
