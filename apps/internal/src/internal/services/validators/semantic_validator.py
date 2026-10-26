# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Semantic validation: LLM classifier to judge knowledge base utility."""

import json
import logging

from openai import OpenAI

from internal.config import settings
from internal.schemas.validation import SemanticClassification, StepResult, ValidationVerdict

logger = logging.getLogger(__name__)

SEMANTIC_SYSTEM_PROMPT = """You are a knowledge base quality reviewer. Given a question-answer pair, determine if it would be useful in a retrieval-augmented generation (RAG) knowledge base.

Respond ONLY with valid JSON:
{
  "useful": true/false,
  "category": "faq|technical|policy|tutorial|reference|other",
  "confidence": 0.0-1.0,
  "reason": "brief explanation"
}

A useful entry should:
- Be self-contained and understandable without external context
- Provide factual, actionable information
- Be relevant for an organization's knowledge base
- Not be trivial, tautological, or purely opinion-based"""


def validate_semantic(question: str, answer: str) -> StepResult:
    """Use LLM to classify whether entry is useful for RAG."""
    if not settings.openai_api_key:
        return StepResult(
            step="semantic",
            passed=True,
            verdict=ValidationVerdict.ACCEPT,
            details={"skipped": "OpenAI not configured"},
        )

    client = OpenAI(api_key=settings.openai_api_key)

    try:
        response = client.chat.completions.create(
            model=settings.validation_semantic_model,
            messages=[
                {"role": "system", "content": SEMANTIC_SYSTEM_PROMPT},
                {"role": "user", "content": f"Question: {question}\n\nAnswer: {answer}"},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
            max_tokens=200,
        )

        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        classification = SemanticClassification(**data)

        threshold = settings.validation_semantic_confidence_threshold
        if not classification.useful:
            verdict = ValidationVerdict.REJECT
        elif classification.confidence < threshold:
            verdict = ValidationVerdict.NEEDS_REVIEW
        else:
            verdict = ValidationVerdict.ACCEPT

        return StepResult(
            step="semantic",
            passed=classification.useful,
            verdict=verdict,
            score=classification.confidence,
            details=classification.model_dump(),
        )

    except Exception as e:
        logger.error("Semantic validation failed: %s", e)
        return StepResult(
            step="semantic",
            passed=True,
            verdict=ValidationVerdict.NEEDS_REVIEW,
            error=str(e),
            details={"fallback": "classifier error, flagged for review"},
        )
