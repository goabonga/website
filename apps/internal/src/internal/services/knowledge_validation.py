# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Knowledge validation pipeline orchestrator."""

import logging

from sqlalchemy.orm import Session

from internal.models.knowledge import KnowledgeEntry, KnowledgeEntryStatus
from internal.schemas.validation import StepResult, ValidationResult, ValidationVerdict
from internal.services.validators.cleaning_validator import validate_cleaning
from internal.services.validators.decision_engine import decide
from internal.services.validators.dedup_validator import validate_dedup
from internal.services.validators.length_validator import validate_length
from internal.services.validators.quality_validator import validate_quality
from internal.services.validators.retrievability_validator import validate_retrievability
from internal.services.validators.schema_validator import validate_schema
from internal.services.validators.semantic_validator import validate_semantic

logger = logging.getLogger(__name__)


class KnowledgeValidationService:
    """Orchestrates the full knowledge entry validation pipeline.

    Runs synchronously inside a Celery worker.
    """

    def validate(self, entry_id: int, db: Session) -> ValidationResult:
        """Run the full validation pipeline on a knowledge entry."""
        entry = db.get(KnowledgeEntry, entry_id)
        if not entry:
            raise ValueError(f"KnowledgeEntry {entry_id} not found")

        # Mark as validating
        entry.status = KnowledgeEntryStatus.VALIDATING.value
        db.commit()

        logger.info("Validation started | entry_id=%d", entry_id)

        steps: list[StepResult] = []

        # Step 1: Schema validation
        step1 = validate_schema(entry.question, entry.answer, entry.metadata_)
        steps.append(step1)
        if step1.verdict == ValidationVerdict.REJECT:
            return self._finalize(entry, steps, db)

        # Step 2: Cleaning & normalization
        step2 = validate_cleaning(entry.question, entry.answer)
        steps.append(step2)
        # Apply cleaned text for subsequent steps
        question = step2.details.get("cleaned_question", entry.question)
        answer = step2.details.get("cleaned_answer", entry.answer)

        # Step 3: RAG quality scoring
        step3 = validate_quality(question, answer)
        steps.append(step3)

        # Step 4: Semantic validation (LLM)
        step4 = validate_semantic(question, answer)
        steps.append(step4)

        # Step 5: Deduplication
        step5 = validate_dedup(question, entry.id, entry.namespace_id, db)
        steps.append(step5)
        if step5.verdict == ValidationVerdict.REJECT:
            return self._finalize(entry, steps, db)

        # Capture embedding from dedup step for reuse
        embedding = step5.details.get("embedding")

        # Step 6: Answer length validation
        step6 = validate_length(answer)
        steps.append(step6)

        # Step 7: Retrievability test
        if embedding:
            # Store embedding on entry before retrievability test
            entry.embedding = embedding
            db.flush()

        step7 = validate_retrievability(question, answer, entry.id, embedding, db)
        steps.append(step7)

        return self._finalize(entry, steps, db)

    def _finalize(
        self,
        entry: KnowledgeEntry,
        steps: list[StepResult],
        db: Session,
    ) -> ValidationResult:
        """Apply decision engine and update the entry."""
        result = decide(entry.id, steps)

        # Map verdict to model status
        status_map = {
            ValidationVerdict.ACCEPT: KnowledgeEntryStatus.ACCEPTED,
            ValidationVerdict.REJECT: KnowledgeEntryStatus.REJECTED,
            ValidationVerdict.NEEDS_REVIEW: KnowledgeEntryStatus.NEEDS_REVIEW,
        }
        entry.status = status_map[result.final_verdict].value

        # Store validation details (exclude large embedding from serialization)
        safe_steps = []
        for s in result.steps:
            d = s.model_dump()
            if "embedding" in d.get("details", {}):
                del d["details"]["embedding"]
            safe_steps.append(d)

        entry.validation_details = {
            "verdict": result.final_verdict.value,
            "summary": result.summary,
            "steps": safe_steps,
        }

        db.commit()

        logger.info(
            "Validation completed | entry_id=%d verdict=%s summary=%s",
            entry.id,
            result.final_verdict.value,
            result.summary,
        )

        return result
