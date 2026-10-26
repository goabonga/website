# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Cleaning & normalization: HTML removal, log/stack trace detection, language detection, UTF-8."""

import logging
import re
import unicodedata

from bs4 import BeautifulSoup

from internal.schemas.validation import StepResult, ValidationVerdict

logger = logging.getLogger(__name__)

# Patterns indicating noisy content
LOG_PATTERN = re.compile(
    r"^\d{4}[-/]\d{2}[-/]\d{2}[\sT]\d{2}:\d{2}:\d{2}",
    re.MULTILINE,
)
STACK_TRACE_PATTERN = re.compile(
    r"(Traceback \(most recent call last\)|^\s+at\s+[\w.$]+\(|Exception in thread)",
    re.MULTILINE,
)


def strip_html(text: str) -> str:
    """Remove HTML tags, return plain text."""
    if "<" in text and ">" in text:
        soup = BeautifulSoup(text, "html.parser")
        return soup.get_text(separator=" ", strip=True)
    return text


def normalize_unicode(text: str) -> str:
    """Normalize to NFC form and clean control chars."""
    text = unicodedata.normalize("NFC", text)
    # Remove control characters except newlines and tabs
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)
    return text.strip()


def detect_language(text: str) -> str | None:
    """Detect language, return ISO code or None on failure."""
    try:
        from langdetect import detect

        return detect(text[:500])
    except Exception:
        return None


def validate_cleaning(question: str, answer: str) -> StepResult:
    """Clean content and flag issues. Returns cleaned text in details."""
    warnings = []

    # Clean HTML
    clean_q = strip_html(question)
    clean_a = strip_html(answer)

    if clean_q != question:
        warnings.append("question contained HTML (stripped)")
    if clean_a != answer:
        warnings.append("answer contained HTML (stripped)")

    # Normalize unicode
    clean_q = normalize_unicode(clean_q)
    clean_a = normalize_unicode(clean_a)

    # Check for log lines
    log_matches_q = len(LOG_PATTERN.findall(clean_q))
    log_matches_a = len(LOG_PATTERN.findall(clean_a))
    if log_matches_q > 2:
        warnings.append(f"question contains {log_matches_q} log-like lines")
    if log_matches_a > 2:
        warnings.append(f"answer contains {log_matches_a} log-like lines")

    # Check for stack traces
    if STACK_TRACE_PATTERN.search(clean_a):
        warnings.append("answer contains stack trace patterns")

    # Language detection
    lang = detect_language(clean_q) or detect_language(clean_a)

    has_critical = any("stack trace" in w or "log-like" in w for w in warnings)
    verdict = ValidationVerdict.NEEDS_REVIEW if has_critical else ValidationVerdict.ACCEPT

    return StepResult(
        step="cleaning",
        passed=True,
        verdict=verdict,
        details={
            "cleaned_question": clean_q,
            "cleaned_answer": clean_a,
            "warnings": warnings,
            "detected_language": lang,
        },
    )
