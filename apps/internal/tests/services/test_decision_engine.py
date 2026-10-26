# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for decision engine."""

from internal.schemas.validation import StepResult, ValidationVerdict
from internal.services.validators.decision_engine import decide


def _step(name: str, verdict: ValidationVerdict, passed: bool = True) -> StepResult:
    return StepResult(step=name, passed=passed, verdict=verdict)


class TestDecide:
    def test_all_pass_accepted(self):
        steps = [
            _step("schema", ValidationVerdict.ACCEPT),
            _step("cleaning", ValidationVerdict.ACCEPT),
            _step("quality", ValidationVerdict.ACCEPT),
            _step("semantic", ValidationVerdict.ACCEPT),
            _step("dedup", ValidationVerdict.ACCEPT),
            _step("length", ValidationVerdict.ACCEPT),
            _step("retrievability", ValidationVerdict.ACCEPT),
        ]
        result = decide(1, steps)
        assert result.final_verdict == ValidationVerdict.ACCEPT
        assert "passed" in result.summary.lower()

    def test_hard_reject_from_schema(self):
        steps = [
            _step("schema", ValidationVerdict.REJECT, passed=False),
        ]
        result = decide(1, steps)
        assert result.final_verdict == ValidationVerdict.REJECT
        assert "schema" in result.summary.lower()

    def test_hard_reject_from_dedup(self):
        steps = [
            _step("schema", ValidationVerdict.ACCEPT),
            _step("cleaning", ValidationVerdict.ACCEPT),
            _step("quality", ValidationVerdict.ACCEPT),
            _step("dedup", ValidationVerdict.REJECT, passed=False),
        ]
        result = decide(1, steps)
        assert result.final_verdict == ValidationVerdict.REJECT
        assert "dedup" in result.summary.lower()

    def test_two_soft_rejects_overall_reject(self):
        steps = [
            _step("schema", ValidationVerdict.ACCEPT),
            _step("cleaning", ValidationVerdict.ACCEPT),
            _step("quality", ValidationVerdict.REJECT, passed=False),
            _step("semantic", ValidationVerdict.REJECT, passed=False),
            _step("length", ValidationVerdict.ACCEPT),
        ]
        result = decide(1, steps)
        assert result.final_verdict == ValidationVerdict.REJECT
        assert "2" in result.summary

    def test_one_soft_reject_needs_review(self):
        steps = [
            _step("schema", ValidationVerdict.ACCEPT),
            _step("cleaning", ValidationVerdict.ACCEPT),
            _step("quality", ValidationVerdict.REJECT, passed=False),
            _step("semantic", ValidationVerdict.ACCEPT),
            _step("dedup", ValidationVerdict.ACCEPT),
            _step("length", ValidationVerdict.ACCEPT),
            _step("retrievability", ValidationVerdict.ACCEPT),
        ]
        result = decide(1, steps)
        assert result.final_verdict == ValidationVerdict.NEEDS_REVIEW

    def test_needs_review_propagated(self):
        steps = [
            _step("schema", ValidationVerdict.ACCEPT),
            _step("cleaning", ValidationVerdict.NEEDS_REVIEW),
            _step("quality", ValidationVerdict.ACCEPT),
            _step("semantic", ValidationVerdict.ACCEPT),
            _step("dedup", ValidationVerdict.ACCEPT),
            _step("length", ValidationVerdict.ACCEPT),
            _step("retrievability", ValidationVerdict.ACCEPT),
        ]
        result = decide(1, steps)
        assert result.final_verdict == ValidationVerdict.NEEDS_REVIEW

    def test_entry_id_preserved(self):
        steps = [_step("schema", ValidationVerdict.ACCEPT)]
        result = decide(42, steps)
        assert result.entry_id == 42

    def test_all_steps_preserved(self):
        steps = [
            _step("schema", ValidationVerdict.ACCEPT),
            _step("quality", ValidationVerdict.ACCEPT),
        ]
        result = decide(1, steps)
        assert len(result.steps) == 2
