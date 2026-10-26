# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for cleaning validator."""

from unittest.mock import patch

from internal.schemas.validation import ValidationVerdict
from internal.services.validators.cleaning_validator import (
    detect_language,
    normalize_unicode,
    strip_html,
    validate_cleaning,
)


class TestStripHtml:
    def test_plain_text_unchanged(self):
        assert strip_html("Hello world") == "Hello world"

    def test_html_tags_removed(self):
        result = strip_html("<p>Hello <b>world</b></p>")
        assert "Hello" in result
        assert "world" in result
        assert "<" not in result

    def test_nested_html(self):
        result = strip_html("<div><p>Text <a href='#'>link</a></p></div>")
        assert "Text" in result
        assert "link" in result
        assert "<" not in result


class TestNormalizeUnicode:
    def test_normal_text(self):
        assert normalize_unicode("Hello world") == "Hello world"

    def test_control_chars_removed(self):
        result = normalize_unicode("Hello\x00\x01\x02world")
        assert "\x00" not in result
        assert result == "Helloworld"

    def test_whitespace_stripped(self):
        assert normalize_unicode("  Hello  ") == "Hello"


class TestDetectLanguage:
    @patch("langdetect.detect")
    def test_english_detected(self, mock_detect):
        mock_detect.return_value = "en"
        assert detect_language("This is English text") == "en"

    @patch("langdetect.detect")
    def test_french_detected(self, mock_detect):
        mock_detect.return_value = "fr"
        assert detect_language("Ceci est du texte francais") == "fr"

    def test_exception_returns_none(self):
        assert detect_language("") is None


class TestValidateCleaning:
    def test_plain_text_passes(self):
        result = validate_cleaning(
            "What is Python?",
            "Python is a programming language.",
        )
        assert result.passed is True
        assert result.verdict == ValidationVerdict.ACCEPT

    def test_html_stripped_with_warning(self):
        result = validate_cleaning(
            "<p>What is Python?</p>",
            "Python is a programming language.",
        )
        assert result.passed is True
        assert any("HTML" in w for w in result.details["warnings"])
        assert "<" not in result.details["cleaned_question"]

    def test_html_in_answer_stripped_with_warning(self):
        result = validate_cleaning(
            "What is Python?",
            "<p>Python is a <b>great</b> language for development.</p>",
        )
        assert result.passed is True
        assert any("answer" in w and "HTML" in w for w in result.details["warnings"])
        assert "<" not in result.details["cleaned_answer"]

    def test_log_lines_in_question_flagged(self):
        log_question = (
            "2024-01-01 12:00:00 INFO Starting\n"
            "2024-01-01 12:00:01 DEBUG Processing\n"
            "2024-01-01 12:00:02 ERROR Failed\n"
            "What happened here?"
        )
        result = validate_cleaning(log_question, "The server crashed due to a bug.")
        assert result.verdict == ValidationVerdict.NEEDS_REVIEW
        assert any("question" in w and "log-like" in w for w in result.details["warnings"])

    def test_log_lines_flagged(self):
        log_text = (
            "2024-01-01 12:00:00 INFO Starting\n"
            "2024-01-01 12:00:01 DEBUG Processing\n"
            "2024-01-01 12:00:02 ERROR Failed\n"
            "Some actual content here."
        )
        result = validate_cleaning("What happened?", log_text)
        assert result.verdict == ValidationVerdict.NEEDS_REVIEW
        assert any("log-like" in w for w in result.details["warnings"])

    def test_stack_trace_flagged(self):
        trace = "Traceback (most recent call last):\n  File 'test.py', line 1\nValueError: invalid"
        result = validate_cleaning("What error?", trace)
        assert result.verdict == ValidationVerdict.NEEDS_REVIEW
        assert any("stack trace" in w for w in result.details["warnings"])

    def test_cleaned_text_in_details(self):
        result = validate_cleaning("What is Python?", "Python is great.")
        assert "cleaned_question" in result.details
        assert "cleaned_answer" in result.details

    def test_language_detected(self):
        with patch(
            "langdetect.detect",
            return_value="en",
        ):
            result = validate_cleaning("What is Python?", "Python is a language.")
            assert result.details["detected_language"] == "en"
