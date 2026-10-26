# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for semantic validator."""

import json
from unittest.mock import MagicMock, patch

from internal.schemas.validation import ValidationVerdict
from internal.services.validators.semantic_validator import validate_semantic


def _make_completion(content: str):
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


class TestValidateSemantic:
    @patch("internal.services.validators.semantic_validator.settings")
    @patch("internal.services.validators.semantic_validator.OpenAI")
    def test_useful_entry_accepted(self, MockOpenAI, mock_settings):
        mock_settings.openai_api_key = "sk-test"
        mock_settings.validation_semantic_model = "gpt-4o-mini"
        mock_settings.validation_semantic_confidence_threshold = 0.7

        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        mock_client.chat.completions.create.return_value = _make_completion(
            json.dumps(
                {
                    "useful": True,
                    "category": "technical",
                    "confidence": 0.95,
                    "reason": "Clear technical Q&A",
                }
            )
        )

        result = validate_semantic("What is Python?", "Python is a programming language.")
        assert result.passed is True
        assert result.verdict == ValidationVerdict.ACCEPT
        assert result.score == 0.95

    @patch("internal.services.validators.semantic_validator.settings")
    @patch("internal.services.validators.semantic_validator.OpenAI")
    def test_not_useful_rejected(self, MockOpenAI, mock_settings):
        mock_settings.openai_api_key = "sk-test"
        mock_settings.validation_semantic_model = "gpt-4o-mini"
        mock_settings.validation_semantic_confidence_threshold = 0.7

        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        mock_client.chat.completions.create.return_value = _make_completion(
            json.dumps(
                {
                    "useful": False,
                    "category": "other",
                    "confidence": 0.9,
                    "reason": "Trivial content",
                }
            )
        )

        result = validate_semantic("Hello?", "Hi there!")
        assert result.passed is False
        assert result.verdict == ValidationVerdict.REJECT

    @patch("internal.services.validators.semantic_validator.settings")
    @patch("internal.services.validators.semantic_validator.OpenAI")
    def test_low_confidence_needs_review(self, MockOpenAI, mock_settings):
        mock_settings.openai_api_key = "sk-test"
        mock_settings.validation_semantic_model = "gpt-4o-mini"
        mock_settings.validation_semantic_confidence_threshold = 0.7

        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        mock_client.chat.completions.create.return_value = _make_completion(
            json.dumps(
                {
                    "useful": True,
                    "category": "faq",
                    "confidence": 0.5,
                    "reason": "Uncertain",
                }
            )
        )

        result = validate_semantic("Is this useful?", "Maybe, it depends on context.")
        assert result.passed is True
        assert result.verdict == ValidationVerdict.NEEDS_REVIEW

    @patch("internal.services.validators.semantic_validator.settings")
    def test_openai_not_configured_skipped(self, mock_settings):
        mock_settings.openai_api_key = ""

        result = validate_semantic("What is X?", "X is something.")
        assert result.passed is True
        assert result.verdict == ValidationVerdict.ACCEPT
        assert result.details.get("skipped")

    @patch("internal.services.validators.semantic_validator.settings")
    @patch("internal.services.validators.semantic_validator.OpenAI")
    def test_api_error_returns_needs_review(self, MockOpenAI, mock_settings):
        mock_settings.openai_api_key = "sk-test"
        mock_settings.validation_semantic_model = "gpt-4o-mini"
        mock_settings.validation_semantic_confidence_threshold = 0.7

        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API error")

        result = validate_semantic("What is X?", "X is something useful.")
        assert result.passed is True
        assert result.verdict == ValidationVerdict.NEEDS_REVIEW
        assert result.error is not None
