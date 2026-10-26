# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for dedup validator."""

from unittest.mock import MagicMock, patch

from internal.schemas.validation import ValidationVerdict
from internal.services.validators.dedup_validator import validate_dedup


class TestValidateDedup:
    @patch("internal.services.validators.dedup_validator.settings")
    def test_openai_not_configured_skipped(self, mock_settings):
        mock_settings.openai_api_key = ""
        result = validate_dedup("What is X?", 1, None, MagicMock())
        assert result.passed is True
        assert result.verdict == ValidationVerdict.ACCEPT
        assert result.details.get("skipped")

    @patch("internal.services.validators.dedup_validator.settings")
    @patch("internal.services.validators.dedup_validator.OpenAI")
    def test_no_duplicates_accepted(self, MockOpenAI, mock_settings):
        mock_settings.openai_api_key = "sk-test"
        mock_settings.rag_embedding_model = "text-embedding-3-small"
        mock_settings.validation_dedup_similarity_threshold = 0.92

        # Mock OpenAI embedding
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        mock_data = MagicMock()
        mock_data.embedding = [0.1] * 10
        mock_response = MagicMock()
        mock_response.data = [mock_data]
        mock_client.embeddings.create.return_value = mock_response

        # Mock DB session
        mock_db = MagicMock()
        mock_db.get.return_value = None  # No existing entry with embedding
        mock_db.execute.return_value = iter([])  # No similar entries

        result = validate_dedup("What is Python?", 1, None, mock_db)
        assert result.passed is True
        assert result.verdict == ValidationVerdict.ACCEPT
        assert result.details.get("embedding") is not None

    @patch("internal.services.validators.dedup_validator.settings")
    @patch("internal.services.validators.dedup_validator.OpenAI")
    def test_high_similarity_rejected(self, MockOpenAI, mock_settings):
        mock_settings.openai_api_key = "sk-test"
        mock_settings.rag_embedding_model = "text-embedding-3-small"
        mock_settings.validation_dedup_similarity_threshold = 0.92

        # Mock OpenAI embedding
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        mock_data = MagicMock()
        mock_data.embedding = [0.1] * 10
        mock_response = MagicMock()
        mock_response.data = [mock_data]
        mock_client.embeddings.create.return_value = mock_response

        # Mock DB with a similar entry found
        mock_row = MagicMock()
        mock_row.id = 42
        mock_row.question = "What is Python programming?"
        mock_row.similarity = 0.95

        mock_db = MagicMock()
        mock_db.get.return_value = None
        mock_db.execute.return_value = iter([mock_row])

        result = validate_dedup("What is Python?", 1, None, mock_db)
        assert result.passed is False
        assert result.verdict == ValidationVerdict.REJECT
        assert result.details["closest_id"] == 42
        assert result.details["closest_similarity"] == 0.95

    @patch("internal.services.validators.dedup_validator.settings")
    def test_existing_embedding_reused(self, mock_settings):
        mock_settings.openai_api_key = "sk-test"
        mock_settings.rag_embedding_model = "text-embedding-3-small"
        mock_settings.validation_dedup_similarity_threshold = 0.92

        # Mock entry with existing embedding
        mock_entry = MagicMock()
        mock_entry.embedding = [0.2] * 10

        mock_db = MagicMock()
        mock_db.get.return_value = mock_entry
        mock_db.execute.return_value = iter([])

        result = validate_dedup("What is Python?", 1, None, mock_db)
        assert result.passed is True
        assert result.details.get("embedding") == [0.2] * 10

    @patch("internal.services.validators.dedup_validator.settings")
    @patch("internal.services.validators.dedup_validator.OpenAI")
    def test_embedding_error_returns_needs_review(self, MockOpenAI, mock_settings):
        mock_settings.openai_api_key = "sk-test"
        mock_settings.rag_embedding_model = "text-embedding-3-small"

        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        mock_client.embeddings.create.side_effect = Exception("API error")

        mock_db = MagicMock()
        mock_db.get.return_value = None

        result = validate_dedup("What is X?", 1, None, mock_db)
        assert result.passed is True
        assert result.verdict == ValidationVerdict.NEEDS_REVIEW
        assert result.error is not None
