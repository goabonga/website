# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for sync embedding service."""

from unittest.mock import MagicMock, patch

from internal.services.embeddings_sync import SyncEmbeddingService


class TestSyncEmbeddingService:
    @patch("internal.services.embeddings_sync.settings")
    @patch("internal.services.embeddings_sync.OpenAI")
    def test_generate_embedding(self, MockOpenAI, mock_settings):
        mock_settings.openai_api_key = "sk-test"
        mock_settings.rag_embedding_model = "text-embedding-3-small"

        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client

        data_item = MagicMock()
        data_item.embedding = [0.1, 0.2, 0.3]
        mock_response = MagicMock()
        mock_response.data = [data_item]
        mock_client.embeddings.create.return_value = mock_response

        service = SyncEmbeddingService()
        result = service.generate("test text")

        assert result == [0.1, 0.2, 0.3]
        mock_client.embeddings.create.assert_called_once_with(
            model="text-embedding-3-small",
            input="test text",
        )

    @patch("internal.services.embeddings_sync.settings")
    @patch("internal.services.embeddings_sync.OpenAI")
    def test_custom_model(self, MockOpenAI, mock_settings):
        mock_settings.openai_api_key = "sk-test"
        mock_settings.rag_embedding_model = "text-embedding-3-small"

        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client

        data_item = MagicMock()
        data_item.embedding = [0.5]
        mock_response = MagicMock()
        mock_response.data = [data_item]
        mock_client.embeddings.create.return_value = mock_response

        service = SyncEmbeddingService(model="custom-model")
        result = service.generate("test")

        assert result == [0.5]
        mock_client.embeddings.create.assert_called_once_with(
            model="custom-model",
            input="test",
        )
