# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for schema validator."""

from internal.schemas.validation import ValidationVerdict
from internal.services.validators.schema_validator import validate_schema


class TestValidateSchema:
    def test_valid_entry(self):
        result = validate_schema(
            "What is Python programming?",
            "Python is a high-level programming language.",
            {"tags": ["python"]},
        )
        assert result.passed is True
        assert result.verdict == ValidationVerdict.ACCEPT

    def test_question_too_short(self):
        result = validate_schema("Short?", "This is a valid answer text.", {})
        assert result.passed is False
        assert result.verdict == ValidationVerdict.REJECT
        assert "question too short" in result.details["issues"][0]

    def test_answer_too_short(self):
        result = validate_schema("What is Python programming?", "Short.", {})
        assert result.passed is False
        assert result.verdict == ValidationVerdict.REJECT
        assert "answer too short" in result.details["issues"][0]

    def test_empty_question(self):
        result = validate_schema("", "This is a valid answer text.", {})
        assert result.passed is False
        assert result.verdict == ValidationVerdict.REJECT

    def test_empty_answer(self):
        result = validate_schema("What is Python programming?", "", {})
        assert result.passed is False
        assert result.verdict == ValidationVerdict.REJECT

    def test_binary_content_in_question(self):
        result = validate_schema(
            "What is \x00 this binary?",
            "This is a valid answer text.",
            {},
        )
        assert result.passed is False
        assert result.verdict == ValidationVerdict.REJECT
        assert any("binary" in issue for issue in result.details["issues"])

    def test_binary_content_in_answer(self):
        result = validate_schema(
            "What is Python programming?",
            "This answer has \x00 null bytes in it.",
            {},
        )
        assert result.passed is False
        assert result.verdict == ValidationVerdict.REJECT

    def test_invalid_metadata_type(self):
        result = validate_schema(
            "What is Python programming?",
            "Python is a high-level programming language.",
            "not a dict",
        )
        assert result.passed is False
        assert result.verdict == ValidationVerdict.REJECT
        assert any("metadata" in issue for issue in result.details["issues"])

    def test_none_metadata_accepted(self):
        result = validate_schema(
            "What is Python programming?",
            "Python is a high-level programming language.",
            None,
        )
        assert result.passed is True

    def test_multiple_issues(self):
        result = validate_schema("Hi", "No", "bad")
        assert result.passed is False
        assert len(result.details["issues"]) >= 3
