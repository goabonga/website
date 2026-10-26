# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for length validator."""

from unittest.mock import patch

from internal.schemas.validation import ValidationVerdict
from internal.services.validators.length_validator import count_tokens, validate_length


class TestCountTokens:
    def test_short_text(self):
        tokens = count_tokens("Hello world")
        assert tokens > 0
        assert tokens < 10

    def test_empty_string(self):
        assert count_tokens("") == 0


class TestValidateLength:
    @patch("internal.services.validators.length_validator.settings")
    def test_normal_length_accepted(self, mock_settings):
        mock_settings.validation_answer_min_tokens = 30
        mock_settings.validation_answer_max_tokens = 800
        mock_settings.validation_answer_warn_min_tokens = 50
        mock_settings.validation_answer_warn_max_tokens = 600
        # Generate a moderate-length answer (~100 tokens)
        answer = " ".join(["This is a test sentence with several words."] * 15)
        result = validate_length(answer)
        assert result.passed is True
        assert result.verdict == ValidationVerdict.ACCEPT
        assert result.details["token_count"] > 0

    @patch("internal.services.validators.length_validator.settings")
    def test_too_short_rejected(self, mock_settings):
        mock_settings.validation_answer_min_tokens = 30
        mock_settings.validation_answer_max_tokens = 800
        mock_settings.validation_answer_warn_min_tokens = 50
        mock_settings.validation_answer_warn_max_tokens = 600
        result = validate_length("Short answer.")
        assert result.passed is False
        assert result.verdict == ValidationVerdict.REJECT
        assert "too short" in result.details["reason"]

    @patch("internal.services.validators.length_validator.settings")
    def test_too_long_rejected(self, mock_settings):
        mock_settings.validation_answer_min_tokens = 30
        mock_settings.validation_answer_max_tokens = 50
        mock_settings.validation_answer_warn_min_tokens = 35
        mock_settings.validation_answer_warn_max_tokens = 45
        answer = " ".join(["word"] * 200)
        result = validate_length(answer)
        assert result.passed is False
        assert result.verdict == ValidationVerdict.REJECT
        assert "too long" in result.details["reason"]

    @patch("internal.services.validators.length_validator.settings")
    def test_borderline_short_needs_review(self, mock_settings):
        mock_settings.validation_answer_min_tokens = 5
        mock_settings.validation_answer_max_tokens = 800
        mock_settings.validation_answer_warn_min_tokens = 50
        mock_settings.validation_answer_warn_max_tokens = 600
        # Short but above min
        answer = "This is a brief answer with a few words."
        result = validate_length(answer)
        if result.details["token_count"] < 50:
            assert result.verdict == ValidationVerdict.NEEDS_REVIEW

    @patch("internal.services.validators.length_validator.settings")
    def test_borderline_long_needs_review(self, mock_settings):
        mock_settings.validation_answer_min_tokens = 5
        mock_settings.validation_answer_max_tokens = 800
        mock_settings.validation_answer_warn_min_tokens = 10
        mock_settings.validation_answer_warn_max_tokens = 20
        # Generate answer above warn_max (20) but below max (800)
        answer = " ".join(["This is a test sentence with several words."] * 5)
        result = validate_length(answer)
        assert result.passed is True
        assert result.verdict == ValidationVerdict.NEEDS_REVIEW
        assert "is long" in result.details["reason"]

    @patch("internal.services.validators.length_validator.settings")
    def test_token_count_in_score(self, mock_settings):
        mock_settings.validation_answer_min_tokens = 5
        mock_settings.validation_answer_max_tokens = 800
        mock_settings.validation_answer_warn_min_tokens = 10
        mock_settings.validation_answer_warn_max_tokens = 600
        result = validate_length("This is a test answer for token counting.")
        assert result.score is not None
        assert result.score == float(result.details["token_count"])
