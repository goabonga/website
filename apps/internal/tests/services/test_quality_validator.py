# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for quality validator."""

from unittest.mock import patch

from internal.schemas.validation import ValidationVerdict
from internal.services.validators.quality_validator import _compute_quality_score, validate_quality


class TestComputeQualityScore:
    def test_high_quality_entry(self):
        score, breakdown = _compute_quality_score(
            "What is Python used for?",
            "Python is a versatile programming language used for web development, "
            "data science, machine learning, automation, and scripting. It has a "
            "clean syntax and a large ecosystem of libraries.",
        )
        assert score > 0.5
        assert "question_form" in breakdown
        assert "answer_ratio" in breakdown

    def test_non_question_gets_lower_score(self):
        score, breakdown = _compute_quality_score(
            "Python programming language",
            "Python is a versatile programming language used for many tasks.",
        )
        assert breakdown["question_form"] == 0.3

    def test_question_with_mark_scores_high(self):
        _, breakdown = _compute_quality_score(
            "What is X?",
            "X is a thing that does many useful operations for developers.",
        )
        assert breakdown["question_form"] == 1.0

    def test_repetitive_answer_penalized(self):
        _, breakdown = _compute_quality_score(
            "What is repetition?",
            "word word word word word word word word word word word word",
        )
        assert breakdown["lexical_diversity"] < 0.3


class TestValidateQuality:
    @patch("internal.services.validators.quality_validator.settings")
    def test_high_quality_accepted(self, mock_settings):
        mock_settings.validation_quality_min_score = 0.4
        result = validate_quality(
            "What is Python used for?",
            "Python is a versatile programming language widely used for web "
            "development, data analysis, artificial intelligence, and automation. "
            "It features clean syntax and extensive libraries.",
        )
        assert result.passed is True
        assert result.score is not None
        assert result.score > 0.4

    @patch("internal.services.validators.quality_validator.settings")
    def test_low_quality_rejected(self, mock_settings):
        mock_settings.validation_quality_min_score = 0.8
        result = validate_quality("x", "y")
        assert result.passed is False
        assert result.verdict == ValidationVerdict.REJECT

    @patch("internal.services.validators.quality_validator.settings")
    def test_borderline_needs_review(self, mock_settings):
        mock_settings.validation_quality_min_score = 0.3
        result = validate_quality(
            "Python overview",
            "Python is a language. It is used for programming.",
        )
        # Score should be above 0.3 but potentially below 0.45 (threshold + 0.15)
        if result.passed and result.score < 0.45:
            assert result.verdict == ValidationVerdict.NEEDS_REVIEW

    @patch("internal.services.validators.quality_validator.settings")
    def test_near_threshold_needs_review(self, mock_settings):
        # Set threshold so score lands in the NEEDS_REVIEW band (>= threshold, < threshold + 0.15)
        mock_settings.validation_quality_min_score = 0.01
        result = validate_quality(
            "Python overview",
            "Python is a language.",
        )
        # With such a low threshold, the score should be >= 0.01 but
        # we need it < 0.16 for NEEDS_REVIEW. Force with a higher threshold.
        mock_settings.validation_quality_min_score = max(0.01, result.score - 0.10)
        result = validate_quality(
            "Python overview",
            "Python is a language.",
        )
        if result.passed and result.score < mock_settings.validation_quality_min_score + 0.15:
            assert result.verdict == ValidationVerdict.NEEDS_REVIEW

    @patch("internal.services.validators.quality_validator.settings")
    def test_score_exactly_at_needs_review_boundary(self, mock_settings):
        # Compute the actual score first, then set threshold to force NEEDS_REVIEW
        from internal.services.validators.quality_validator import _compute_quality_score

        score, _ = _compute_quality_score("Python details", "Python is used for coding.")
        # Set threshold so score is in [threshold, threshold+0.15)
        mock_settings.validation_quality_min_score = score - 0.05
        result = validate_quality("Python details", "Python is used for coding.")
        assert result.passed is True
        assert result.verdict == ValidationVerdict.NEEDS_REVIEW

    @patch("internal.services.validators.quality_validator.settings")
    def test_score_in_details(self, mock_settings):
        mock_settings.validation_quality_min_score = 0.4
        result = validate_quality("What is X?", "X is a useful concept in computing.")
        assert "breakdown" in result.details
        assert "threshold" in result.details
