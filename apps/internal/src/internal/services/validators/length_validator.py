# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Answer length validation: token count bounds on answer field."""

import logging

import tiktoken

from internal.config import settings
from internal.schemas.validation import StepResult, ValidationVerdict

logger = logging.getLogger(__name__)

_encoding = None


def _get_encoding() -> tiktoken.Encoding:
    """Get cached tiktoken encoding."""
    global _encoding
    if _encoding is None:
        _encoding = tiktoken.encoding_for_model("gpt-4o-mini")
    return _encoding


def count_tokens(text: str) -> int:
    """Count tokens using tiktoken."""
    return len(_get_encoding().encode(text))


def validate_length(answer: str) -> StepResult:
    """Check answer token count against configured bounds."""
    token_count = count_tokens(answer)

    min_tokens = settings.validation_answer_min_tokens
    max_tokens = settings.validation_answer_max_tokens
    warn_min = settings.validation_answer_warn_min_tokens
    warn_max = settings.validation_answer_warn_max_tokens

    if token_count < min_tokens:
        verdict = ValidationVerdict.REJECT
        passed = False
        reason = f"answer too short ({token_count} tokens, minimum {min_tokens})"
    elif token_count > max_tokens:
        verdict = ValidationVerdict.REJECT
        passed = False
        reason = f"answer too long ({token_count} tokens, maximum {max_tokens})"
    elif token_count < warn_min:
        verdict = ValidationVerdict.NEEDS_REVIEW
        passed = True
        reason = f"answer is short ({token_count} tokens, recommended minimum {warn_min})"
    elif token_count > warn_max:
        verdict = ValidationVerdict.NEEDS_REVIEW
        passed = True
        reason = f"answer is long ({token_count} tokens, recommended maximum {warn_max})"
    else:
        verdict = ValidationVerdict.ACCEPT
        passed = True
        reason = f"answer length OK ({token_count} tokens)"

    return StepResult(
        step="length",
        passed=passed,
        verdict=verdict,
        score=float(token_count),
        details={
            "token_count": token_count,
            "min_tokens": min_tokens,
            "max_tokens": max_tokens,
            "reason": reason,
        },
    )
