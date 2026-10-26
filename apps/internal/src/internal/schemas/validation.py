# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Pydantic schemas for the knowledge validation pipeline."""

from enum import StrEnum

from pydantic import BaseModel, Field


class ValidationVerdict(StrEnum):
    """Final verdict of a validation step or the full pipeline."""

    ACCEPT = "accept"
    REJECT = "reject"
    NEEDS_REVIEW = "needs_review"


class StepResult(BaseModel):
    """Result of a single validation step."""

    step: str
    passed: bool
    verdict: ValidationVerdict = ValidationVerdict.ACCEPT
    score: float | None = None
    details: dict = Field(default_factory=dict)
    error: str | None = None


class SemanticClassification(BaseModel):
    """LLM semantic validation response."""

    useful: bool
    category: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = ""


class ValidationResult(BaseModel):
    """Full pipeline result aggregating all steps."""

    entry_id: int
    final_verdict: ValidationVerdict
    steps: list[StepResult]
    summary: str = ""


class KnowledgeEntryInput(BaseModel):
    """Input validation model for knowledge entry creation."""

    question: str = Field(min_length=10, max_length=2000)
    answer: str = Field(min_length=20, max_length=50000)
    metadata_: dict = Field(default_factory=dict, alias="metadata")
    namespace_id: int

    model_config = {"populate_by_name": True}
