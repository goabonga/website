# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""RAG quality scoring: heuristic scoring to filter low-signal content."""

import logging
import re

from internal.config import settings
from internal.schemas.validation import StepResult, ValidationVerdict

logger = logging.getLogger(__name__)


def _compute_quality_score(question: str, answer: str) -> tuple[float, dict]:
    """Compute heuristic quality score (0.0-1.0) with breakdown."""
    scores = {}

    # 1. Question is actually a question (has ? or interrogative word)
    q_lower = question.lower().strip()
    has_question_mark = "?" in question
    has_interrogative = any(
        q_lower.startswith(w)
        for w in [
            "what",
            "how",
            "why",
            "when",
            "where",
            "who",
            "which",
            "is",
            "can",
            "does",
            "do",
            "are",
            "will",
            "should",
        ]
    )
    scores["question_form"] = 1.0 if (has_question_mark or has_interrogative) else 0.3

    # 2. Answer length relative to question (answer should be substantially longer)
    ratio = len(answer) / max(len(question), 1)
    scores["answer_ratio"] = min(1.0, ratio / 5.0)

    # 3. Answer has sentence structure (at least one period)
    sentence_count = len(re.findall(r"[.!?]\s", answer + " "))
    scores["sentence_structure"] = min(1.0, sentence_count / 3.0)

    # 4. No excessive repetition
    words = answer.lower().split()
    unique_ratio = len(set(words)) / max(len(words), 1)
    scores["lexical_diversity"] = unique_ratio

    # 5. Question-answer relevance (word overlap)
    q_words = set(question.lower().split())
    a_words = set(answer.lower().split())
    overlap = len(q_words & a_words) / max(len(q_words), 1)
    scores["qa_overlap"] = min(1.0, overlap * 2)

    # Weighted average
    weights = {
        "question_form": 0.15,
        "answer_ratio": 0.20,
        "sentence_structure": 0.20,
        "lexical_diversity": 0.25,
        "qa_overlap": 0.20,
    }
    total = sum(scores[k] * weights[k] for k in weights)

    return total, scores


def validate_quality(question: str, answer: str) -> StepResult:
    """Score RAG quality and check against threshold."""
    score, breakdown = _compute_quality_score(question, answer)
    threshold = settings.validation_quality_min_score
    passed = score >= threshold

    if not passed:
        verdict = ValidationVerdict.REJECT
    elif score < threshold + 0.15:
        verdict = ValidationVerdict.NEEDS_REVIEW
    else:
        verdict = ValidationVerdict.ACCEPT

    return StepResult(
        step="quality",
        passed=passed,
        verdict=verdict,
        score=score,
        details={"breakdown": breakdown, "threshold": threshold},
    )
