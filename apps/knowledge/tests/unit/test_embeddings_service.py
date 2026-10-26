# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for knowledge/services/embeddings.py — EmbeddingService."""

from unittest.mock import AsyncMock, MagicMock, patch

from knowledge.services.embeddings import EmbeddingService, get_embedding_service


class TestEmbeddingService:
    def _make_service(self):
        """Create an EmbeddingService with a mocked OpenAI client."""
        with patch("knowledge.services.embeddings.get_settings") as mock_gs:
            mock_gs.return_value.openai_api_key = "test-key"
            mock_gs.return_value.embedding_model = "text-embedding-3-small"
            mock_gs.return_value.embedding_dimension = 1536
            with patch("knowledge.services.embeddings.AsyncOpenAI") as mock_openai:
                service = EmbeddingService()
                service.client = mock_openai.return_value
        return service

    # --- embed_text ---

    async def test_embed_text(self):
        service = self._make_service()
        mock_embedding = [0.1, 0.2, 0.3]

        mock_data_item = MagicMock()
        mock_data_item.embedding = mock_embedding

        mock_response = MagicMock()
        mock_response.data = [mock_data_item]

        service.client.embeddings.create = AsyncMock(return_value=mock_response)

        result = await service.embed_text("Hello world")
        assert result == mock_embedding
        service.client.embeddings.create.assert_awaited_once_with(
            model=service.model,
            input="Hello world",
            dimensions=service.dimension,
        )

    # --- embed_texts ---

    async def test_embed_texts_empty(self):
        service = self._make_service()
        result = await service.embed_texts([])
        assert result == []

    async def test_embed_texts_multiple(self):
        service = self._make_service()
        emb1 = [0.1, 0.2]
        emb2 = [0.3, 0.4]

        item1 = MagicMock()
        item1.index = 0
        item1.embedding = emb1

        item2 = MagicMock()
        item2.index = 1
        item2.embedding = emb2

        mock_response = MagicMock()
        # Return in reverse order to test sorting
        mock_response.data = [item2, item1]

        service.client.embeddings.create = AsyncMock(return_value=mock_response)

        result = await service.embed_texts(["text1", "text2"])
        assert result == [emb1, emb2]
        service.client.embeddings.create.assert_awaited_once_with(
            model=service.model,
            input=["text1", "text2"],
            dimensions=service.dimension,
        )

    async def test_embed_texts_single(self):
        service = self._make_service()
        emb = [0.5, 0.6]

        item = MagicMock()
        item.index = 0
        item.embedding = emb

        mock_response = MagicMock()
        mock_response.data = [item]

        service.client.embeddings.create = AsyncMock(return_value=mock_response)

        result = await service.embed_texts(["single text"])
        assert result == [emb]


# --- get_embedding_service singleton ---


class TestGetEmbeddingService:
    @patch("knowledge.services.embeddings._embedding_service", None)
    @patch("knowledge.services.embeddings.AsyncOpenAI")
    @patch("knowledge.services.embeddings.get_settings")
    def test_get_embedding_service_creates_new(self, mock_gs, mock_openai):
        mock_gs.return_value.openai_api_key = "key"
        mock_gs.return_value.embedding_model = "model"
        mock_gs.return_value.embedding_dimension = 1536
        service = get_embedding_service()
        assert isinstance(service, EmbeddingService)

    def test_get_embedding_service_returns_existing(self):
        import knowledge.services.embeddings as mod

        original = mod._embedding_service
        sentinel = MagicMock()
        mod._embedding_service = sentinel
        try:
            result = get_embedding_service()
            assert result is sentinel
        finally:
            mod._embedding_service = original
