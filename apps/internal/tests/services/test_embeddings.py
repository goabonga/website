# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for embedding generation service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from internal.services.embeddings import EmbeddingService


@pytest.fixture
def service():
    """Create an EmbeddingService with mocked settings and OpenAI client."""
    with (
        patch("internal.services.embeddings.settings") as mock_settings,
        patch("internal.services.embeddings.AsyncOpenAI") as MockOpenAI,
    ):
        mock_settings.openai_api_key = "sk-test-key"
        mock_settings.rag_embedding_model = "text-embedding-3-small"
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        svc = EmbeddingService()
        yield svc, mock_client


@pytest.fixture
def service_custom_model():
    """Create an EmbeddingService with a custom model."""
    with (
        patch("internal.services.embeddings.settings") as mock_settings,
        patch("internal.services.embeddings.AsyncOpenAI") as MockOpenAI,
    ):
        mock_settings.openai_api_key = "sk-test-key"
        mock_settings.rag_embedding_model = "text-embedding-3-small"
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        svc = EmbeddingService(model="text-embedding-ada-002")
        yield svc, mock_client


class TestInit:
    def test_default_model(self):
        with (
            patch("internal.services.embeddings.settings") as mock_settings,
            patch("internal.services.embeddings.AsyncOpenAI") as MockOpenAI,
        ):
            mock_settings.openai_api_key = "sk-test-key"
            mock_settings.rag_embedding_model = "text-embedding-3-small"
            svc = EmbeddingService()
            assert svc.model == "text-embedding-3-small"
            assert svc.dimensions == 1536
            MockOpenAI.assert_called_once_with(api_key="sk-test-key")

    def test_custom_model(self):
        with (
            patch("internal.services.embeddings.settings") as mock_settings,
            patch("internal.services.embeddings.AsyncOpenAI"),
        ):
            mock_settings.openai_api_key = "sk-test-key"
            mock_settings.rag_embedding_model = "text-embedding-3-small"
            svc = EmbeddingService(model="text-embedding-ada-002")
            assert svc.model == "text-embedding-ada-002"
            assert svc.dimensions == 1536


class TestGenerate:
    @pytest.mark.asyncio
    async def test_success(self, service):
        svc, mock_client = service
        mock_embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
        mock_data_item = MagicMock()
        mock_data_item.embedding = mock_embedding
        mock_response = MagicMock()
        mock_response.data = [mock_data_item]
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        result = await svc.generate("Hello world")
        assert result == mock_embedding
        mock_client.embeddings.create.assert_called_once_with(
            model="text-embedding-3-small",
            input="Hello world",
        )

    @pytest.mark.asyncio
    async def test_returns_embedding_list(self, service):
        svc, mock_client = service
        expected = [0.01] * 1536
        mock_data_item = MagicMock()
        mock_data_item.embedding = expected
        mock_response = MagicMock()
        mock_response.data = [mock_data_item]
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        result = await svc.generate("test text")
        assert isinstance(result, list)
        assert len(result) == 1536

    @pytest.mark.asyncio
    async def test_with_custom_model(self, service_custom_model):
        svc, mock_client = service_custom_model
        mock_data_item = MagicMock()
        mock_data_item.embedding = [0.5, 0.6]
        mock_response = MagicMock()
        mock_response.data = [mock_data_item]
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        result = await svc.generate("test")
        assert result == [0.5, 0.6]
        mock_client.embeddings.create.assert_called_once_with(
            model="text-embedding-ada-002",
            input="test",
        )


class TestGenerateBatch:
    @pytest.mark.asyncio
    async def test_success_with_multiple_texts(self, service):
        svc, mock_client = service
        item1 = MagicMock()
        item1.embedding = [0.1, 0.2]
        item2 = MagicMock()
        item2.embedding = [0.3, 0.4]
        item3 = MagicMock()
        item3.embedding = [0.5, 0.6]
        mock_response = MagicMock()
        mock_response.data = [item1, item2, item3]
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        result = await svc.generate_batch(["text1", "text2", "text3"])
        assert result == [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]
        mock_client.embeddings.create.assert_called_once_with(
            model="text-embedding-3-small",
            input=["text1", "text2", "text3"],
        )

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self, service):
        svc, mock_client = service
        result = await svc.generate_batch([])
        assert result == []
        mock_client.embeddings.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_single_text(self, service):
        svc, mock_client = service
        item1 = MagicMock()
        item1.embedding = [0.9, 0.8, 0.7]
        mock_response = MagicMock()
        mock_response.data = [item1]
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        result = await svc.generate_batch(["only one"])
        assert result == [[0.9, 0.8, 0.7]]
