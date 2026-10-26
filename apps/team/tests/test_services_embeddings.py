# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for embedding generation service."""

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

from team.services.embeddings import (
    EMBEDDING_DIMENSIONS,
    generate_embedding,
    generate_embeddings_batch,
)


class TestGenerateEmbedding:
    async def test_returns_embedding(self):
        fake_embedding = [0.1] * EMBEDDING_DIMENSIONS
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=fake_embedding)]

        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)
        mock_client.close = AsyncMock()

        with (
            patch("team.services.embeddings.settings") as mock_settings,
            patch("team.services.embeddings.openai") as mock_openai,
        ):
            mock_settings.openai_api_key = "sk-test"
            mock_openai.AsyncOpenAI.return_value = mock_client

            result = await generate_embedding("Hello world")

        assert result == fake_embedding
        mock_client.embeddings.create.assert_awaited_once()
        call_kwargs = mock_client.embeddings.create.call_args[1]
        assert call_kwargs["input"] == "Hello world"
        assert call_kwargs["model"] == "text-embedding-3-small"
        assert call_kwargs["dimensions"] == EMBEDDING_DIMENSIONS
        mock_client.close.assert_awaited_once()

    async def test_returns_zero_vector_without_api_key(self):
        with patch("team.services.embeddings.settings") as mock_settings:
            mock_settings.openai_api_key = ""

            result = await generate_embedding("Hello world")

        assert result == [0.0] * EMBEDDING_DIMENSIONS
        assert len(result) == EMBEDDING_DIMENSIONS

    async def test_closes_client_on_error(self):
        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(side_effect=RuntimeError("API error"))
        mock_client.close = AsyncMock()

        with (
            patch("team.services.embeddings.settings") as mock_settings,
            patch("team.services.embeddings.openai") as mock_openai,
        ):
            mock_settings.openai_api_key = "sk-test"
            mock_openai.AsyncOpenAI.return_value = mock_client

            with contextlib.suppress(RuntimeError):
                await generate_embedding("fail")

        mock_client.close.assert_awaited_once()


class TestGenerateEmbeddingsBatch:
    async def test_returns_embeddings(self):
        emb1 = [0.1] * EMBEDDING_DIMENSIONS
        emb2 = [0.2] * EMBEDDING_DIMENSIONS
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=emb1), MagicMock(embedding=emb2)]

        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)
        mock_client.close = AsyncMock()

        with (
            patch("team.services.embeddings.settings") as mock_settings,
            patch("team.services.embeddings.openai") as mock_openai,
        ):
            mock_settings.openai_api_key = "sk-test"
            mock_openai.AsyncOpenAI.return_value = mock_client

            result = await generate_embeddings_batch(["Hello", "World"])

        assert len(result) == 2
        assert result[0] == emb1
        assert result[1] == emb2
        call_kwargs = mock_client.embeddings.create.call_args[1]
        assert call_kwargs["input"] == ["Hello", "World"]

    async def test_returns_empty_for_empty_input(self):
        result = await generate_embeddings_batch([])
        assert result == []

    async def test_returns_zero_vectors_without_api_key(self):
        with patch("team.services.embeddings.settings") as mock_settings:
            mock_settings.openai_api_key = ""

            result = await generate_embeddings_batch(["Hello", "World"])

        assert len(result) == 2
        assert all(v == 0.0 for v in result[0])
        assert all(v == 0.0 for v in result[1])

    async def test_closes_client_on_error(self):
        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(side_effect=RuntimeError("API error"))
        mock_client.close = AsyncMock()

        with (
            patch("team.services.embeddings.settings") as mock_settings,
            patch("team.services.embeddings.openai") as mock_openai,
        ):
            mock_settings.openai_api_key = "sk-test"
            mock_openai.AsyncOpenAI.return_value = mock_client

            with contextlib.suppress(RuntimeError):
                await generate_embeddings_batch(["fail"])

        mock_client.close.assert_awaited_once()
