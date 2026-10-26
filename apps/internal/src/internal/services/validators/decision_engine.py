# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Decision engine: aggregate step results into a final ACCEPT/REJECT/NEEDS_REVIEW."""

import logging

from internal.schemas.validation import StepResult, ValidationResult, ValidationVerdict

logger = logging.getLogger(__name__)

# Steps whose REJECT is hard (cannot be overridden)
HARD_REJECT_STEPS = {"schema", "dedup"}


def decide(entry_id: int, steps: list[StepResult]) -> ValidationResult:
    """Aggregate step results into a final validation verdict."""
    # If any hard-reject step failed, overall REJECT
    for step in steps:
        if step.verdict == ValidationVerdict.REJECT and step.step in HARD_REJECT_STEPS:
            return ValidationResult(
                entry_id=entry_id,
                final_verdict=ValidationVerdict.REJECT,
                steps=steps,
                summary=f"Rejected by {step.step}: {step.details}",
            )

    # Count verdicts
    reject_count = sum(1 for s in steps if s.verdict == ValidationVerdict.REJECT)
    review_count = sum(1 for s in steps if s.verdict == ValidationVerdict.NEEDS_REVIEW)

    # 2+ soft rejects -> REJECT
    if reject_count >= 2:
        return ValidationResult(
            entry_id=entry_id,
            final_verdict=ValidationVerdict.REJECT,
            steps=steps,
            summary=f"Rejected: {reject_count} steps failed",
        )

    # 1 soft reject or any NEEDS_REVIEW -> NEEDS_REVIEW
    if reject_count >= 1 or review_count >= 1:
        return ValidationResult(
            entry_id=entry_id,
            final_verdict=ValidationVerdict.NEEDS_REVIEW,
            steps=steps,
            summary=f"Needs review: {reject_count} reject(s), {review_count} review(s)",
        )

    return ValidationResult(
        entry_id=entry_id,
        final_verdict=ValidationVerdict.ACCEPT,
        steps=steps,
        summary="All validation steps passed",
    )
