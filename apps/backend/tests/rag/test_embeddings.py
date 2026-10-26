# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for backend.rag.embeddings.EmbeddingService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestEmbeddingService:
    """Tests for the EmbeddingService class."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Patch settings and AsyncOpenAI before each test."""
        with patch("backend.rag.embeddings.settings") as mock_settings:
            mock_settings.openai_api_key = "test-key"
            mock_settings.rag_embedding_model = "text-embedding-3-small"
            with patch("backend.rag.embeddings.AsyncOpenAI") as mock_openai_cls:
                self.mock_client = AsyncMock()
                mock_openai_cls.return_value = self.mock_client
                from backend.rag.embeddings import EmbeddingService

                self.service = EmbeddingService()
                self.mock_settings = mock_settings
                yield

    async def test_generate_returns_embedding(self):
        """generate() should return the embedding vector from the API response."""
        fake_embedding = [0.1, 0.2, 0.3]
        mock_data_item = MagicMock()
        mock_data_item.embedding = fake_embedding

        mock_response = MagicMock()
        mock_response.data = [mock_data_item]
        self.mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        result = await self.service.generate("test text")

        assert result == fake_embedding
        self.mock_client.embeddings.create.assert_awaited_once_with(
            model=self.service.model,
            input="test text",
        )

    async def test_generate_batch_returns_list_of_embeddings(self):
        """generate_batch() should return a list of embedding vectors."""
        fake_embeddings = [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]
        mock_data_items = []
        for emb in fake_embeddings:
            item = MagicMock()
            item.embedding = emb
            mock_data_items.append(item)

        mock_response = MagicMock()
        mock_response.data = mock_data_items
        self.mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        result = await self.service.generate_batch(["text1", "text2", "text3"])

        assert result == fake_embeddings
        self.mock_client.embeddings.create.assert_awaited_once_with(
            model=self.service.model,
            input=["text1", "text2", "text3"],
        )

    async def test_generate_batch_empty_list_returns_empty(self):
        """generate_batch() with an empty list should return an empty list without calling the API."""
        result = await self.service.generate_batch([])

        assert result == []
        self.mock_client.embeddings.create.assert_not_awaited()
