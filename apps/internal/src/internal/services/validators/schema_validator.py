# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Schema validation: required fields, type checks, content guards."""

import logging

from internal.schemas.validation import StepResult, ValidationVerdict

logger = logging.getLogger(__name__)

MIN_QUESTION_LENGTH = 10
MIN_ANSWER_LENGTH = 20


def validate_schema(question: str, answer: str, metadata: dict | None) -> StepResult:
    """Validate required fields, reject empty/too short/binary content."""
    issues = []

    if not question or len(question.strip()) < MIN_QUESTION_LENGTH:
        issues.append(f"question too short (min {MIN_QUESTION_LENGTH} chars)")
    if not answer or len(answer.strip()) < MIN_ANSWER_LENGTH:
        issues.append(f"answer too short (min {MIN_ANSWER_LENGTH} chars)")
    if metadata is not None and not isinstance(metadata, dict):
        issues.append("metadata must be a JSON object")

    # Reject binary content (null bytes)
    for field_name, value in [("question", question), ("answer", answer)]:
        if value and "\x00" in value:
            issues.append(f"{field_name} contains binary/null bytes")

    passed = len(issues) == 0
    return StepResult(
        step="schema",
        passed=passed,
        verdict=ValidationVerdict.REJECT if not passed else ValidationVerdict.ACCEPT,
        details={"issues": issues} if issues else {},
    )
