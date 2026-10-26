# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for retrievability validator."""

import json
from unittest.mock import MagicMock, patch

from internal.schemas.validation import ValidationVerdict
from internal.services.validators.retrievability_validator import validate_retrievability


def _make_completion(content: str):
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


def _make_embedding(values):
    data_item = MagicMock()
    data_item.embedding = values
    response = MagicMock()
    response.data = [data_item]
    return response


class TestValidateRetrievability:
    @patch("internal.services.validators.retrievability_validator.settings")
    def test_no_openai_skipped(self, mock_settings):
        mock_settings.openai_api_key = ""
        result = validate_retrievability("Q?", "A.", 1, [0.1] * 10, MagicMock())
        assert result.passed is True
        assert result.details.get("skipped")

    @patch("internal.services.validators.retrievability_validator.settings")
    def test_no_embedding_skipped(self, mock_settings):
        mock_settings.openai_api_key = "sk-test"
        result = validate_retrievability("Q?", "A.", 1, None, MagicMock())
        assert result.passed is True
        assert result.details.get("skipped")

    @patch("internal.services.validators.retrievability_validator.settings")
    @patch("internal.services.validators.retrievability_validator.OpenAI")
    def test_found_in_results_accepted(self, MockOpenAI, mock_settings):
        mock_settings.openai_api_key = "sk-test"
        mock_settings.validation_semantic_model = "gpt-4o-mini"
        mock_settings.rag_embedding_model = "text-embedding-3-small"
        mock_settings.validation_retrievability_min_hits = 1

        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client

        # Mock question generation
        mock_client.chat.completions.create.return_value = _make_completion(
            json.dumps({"questions": ["What is Python?", "How to use Python?", "Why Python?"]})
        )

        # Mock embedding generation for each candidate question
        mock_client.embeddings.create.return_value = _make_embedding([0.1] * 10)

        # Mock DB search returning our entry in results
        mock_row = MagicMock()
        mock_row.id = 1
        mock_row.similarity = 0.95

        mock_db = MagicMock()
        mock_db.execute.return_value = iter([mock_row])

        result = validate_retrievability(
            "What is Python?", "Python is a language.", 1, [0.1] * 10, mock_db
        )
        assert result.passed is True
        assert result.verdict == ValidationVerdict.ACCEPT
        assert result.details["hits"] >= 1

    @patch("internal.services.validators.retrievability_validator.settings")
    @patch("internal.services.validators.retrievability_validator.OpenAI")
    def test_not_found_needs_review(self, MockOpenAI, mock_settings):
        mock_settings.openai_api_key = "sk-test"
        mock_settings.validation_semantic_model = "gpt-4o-mini"
        mock_settings.rag_embedding_model = "text-embedding-3-small"
        mock_settings.validation_retrievability_min_hits = 1

        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client

        # Mock question generation
        mock_client.chat.completions.create.return_value = _make_completion(
            json.dumps({"questions": ["Q1?", "Q2?", "Q3?"]})
        )

        # Mock embedding generation
        mock_client.embeddings.create.return_value = _make_embedding([0.1] * 10)

        # Mock DB search NOT returning our entry (id=99)
        mock_row = MagicMock()
        mock_row.id = 2  # Different ID
        mock_row.similarity = 0.9

        mock_db = MagicMock()
        mock_db.execute.return_value = iter([mock_row])

        result = validate_retrievability("Q?", "A.", 99, [0.1] * 10, mock_db)
        assert result.verdict == ValidationVerdict.NEEDS_REVIEW
        assert result.details["hits"] == 0

    @patch("internal.services.validators.retrievability_validator.settings")
    @patch("internal.services.validators.retrievability_validator.OpenAI")
    def test_question_generation_error(self, MockOpenAI, mock_settings):
        mock_settings.openai_api_key = "sk-test"
        mock_settings.validation_semantic_model = "gpt-4o-mini"

        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API error")

        result = validate_retrievability("Q?", "A.", 1, [0.1] * 10, MagicMock())
        assert result.passed is True
        assert result.verdict == ValidationVerdict.NEEDS_REVIEW
        assert result.error is not None

    @patch("internal.services.validators.retrievability_validator.settings")
    @patch("internal.services.validators.retrievability_validator.OpenAI")
    def test_response_as_list(self, MockOpenAI, mock_settings):
        """When LLM returns a raw list instead of {"questions": [...]}."""
        mock_settings.openai_api_key = "sk-test"
        mock_settings.validation_semantic_model = "gpt-4o-mini"
        mock_settings.rag_embedding_model = "text-embedding-3-small"
        mock_settings.validation_retrievability_min_hits = 1

        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client

        # Return a raw list
        mock_client.chat.completions.create.return_value = _make_completion(
            json.dumps(["What is Python?", "How does Python work?", "Why use Python?"])
        )
        mock_client.embeddings.create.return_value = _make_embedding([0.1] * 10)

        mock_row = MagicMock()
        mock_row.id = 1
        mock_row.similarity = 0.95

        mock_db = MagicMock()
        mock_db.execute.return_value = iter([mock_row])

        result = validate_retrievability("Q?", "A.", 1, [0.1] * 10, mock_db)
        assert result.passed is True
        assert result.details["hits"] >= 1

    @patch("internal.services.validators.retrievability_validator.settings")
    @patch("internal.services.validators.retrievability_validator.OpenAI")
    def test_response_invalid_type(self, MockOpenAI, mock_settings):
        """When LLM returns something that's not a list or dict."""
        mock_settings.openai_api_key = "sk-test"
        mock_settings.validation_semantic_model = "gpt-4o-mini"
        mock_settings.rag_embedding_model = "text-embedding-3-small"
        mock_settings.validation_retrievability_min_hits = 1

        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client

        # Return a string (not list/dict)
        mock_client.chat.completions.create.return_value = _make_completion(
            json.dumps("just a string")
        )

        result = validate_retrievability("Q?", "A.", 1, [0.1] * 10, MagicMock())
        assert result.passed is True
        assert result.verdict == ValidationVerdict.NEEDS_REVIEW
        assert "no candidate questions" in result.details.get("error", "")

    @patch("internal.services.validators.retrievability_validator.settings")
    @patch("internal.services.validators.retrievability_validator.OpenAI")
    def test_empty_candidate_questions(self, MockOpenAI, mock_settings):
        """When LLM returns empty questions list."""
        mock_settings.openai_api_key = "sk-test"
        mock_settings.validation_semantic_model = "gpt-4o-mini"
        mock_settings.rag_embedding_model = "text-embedding-3-small"
        mock_settings.validation_retrievability_min_hits = 1

        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client

        mock_client.chat.completions.create.return_value = _make_completion(
            json.dumps({"questions": []})
        )

        result = validate_retrievability("Q?", "A.", 1, [0.1] * 10, MagicMock())
        assert result.passed is True
        assert result.verdict == ValidationVerdict.NEEDS_REVIEW
        assert "no candidate questions" in result.details.get("error", "")

    @patch("internal.services.validators.retrievability_validator.settings")
    @patch("internal.services.validators.retrievability_validator.OpenAI")
    def test_search_error_for_single_query(self, MockOpenAI, mock_settings):
        """When individual search fails for a candidate query."""
        mock_settings.openai_api_key = "sk-test"
        mock_settings.validation_semantic_model = "gpt-4o-mini"
        mock_settings.rag_embedding_model = "text-embedding-3-small"
        mock_settings.validation_retrievability_min_hits = 1

        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client

        mock_client.chat.completions.create.return_value = _make_completion(
            json.dumps({"questions": ["Q1?", "Q2?", "Q3?"]})
        )

        # Embedding succeeds but DB search raises
        mock_client.embeddings.create.return_value = _make_embedding([0.1] * 10)

        mock_db = MagicMock()
        mock_db.execute.side_effect = Exception("DB connection error")

        result = validate_retrievability("Q?", "A.", 1, [0.1] * 10, mock_db)
        assert result.details["hits"] == 0
        assert any("error" in sr for sr in result.details["search_results"])
