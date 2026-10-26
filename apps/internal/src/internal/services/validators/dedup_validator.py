# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Deduplication: embedding similarity check against existing entries."""

import logging

from openai import OpenAI
from sqlalchemy import text
from sqlalchemy.orm import Session

from internal.config import settings
from internal.models.knowledge import KnowledgeEntry
from internal.schemas.validation import StepResult, ValidationVerdict

logger = logging.getLogger(__name__)


def validate_dedup(
    question: str,
    entry_id: int,
    namespace_id: int | None,
    db: Session,
) -> StepResult:
    """Check if a similar entry already exists using embedding cosine similarity."""
    if not settings.openai_api_key:
        return StepResult(
            step="dedup",
            passed=True,
            verdict=ValidationVerdict.ACCEPT,
            details={"skipped": "OpenAI not configured"},
        )

    # Check if entry already has an embedding
    entry = db.get(KnowledgeEntry, entry_id)
    if entry and entry.embedding is not None:
        embedding = list(entry.embedding)
    else:
        # Generate embedding for the question
        client = OpenAI(api_key=settings.openai_api_key)
        try:
            response = client.embeddings.create(
                model=settings.rag_embedding_model,
                input=question,
            )
            embedding = response.data[0].embedding
        except Exception as e:
            logger.error("Failed to generate embedding for dedup: %s", e)
            return StepResult(
                step="dedup",
                passed=True,
                verdict=ValidationVerdict.NEEDS_REVIEW,
                error=str(e),
            )

    # Query for similar entries using pgvector cosine distance
    threshold = settings.validation_dedup_similarity_threshold
    embedding_str = f"[{','.join(str(v) for v in embedding)}]"

    query = text("""
        SELECT id, question, 1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
        FROM knowledge_base
        WHERE id != :entry_id
          AND embedding IS NOT NULL
          AND 1 - (embedding <=> CAST(:embedding AS vector)) > :threshold
        ORDER BY similarity DESC
        LIMIT 5
    """)

    result = db.execute(
        query,
        {
            "embedding": embedding_str,
            "entry_id": entry_id,
            "threshold": threshold,
        },
    )
    duplicates = [
        {"id": row.id, "question": row.question[:100], "similarity": round(row.similarity, 4)}
        for row in result
    ]

    if duplicates:
        best = duplicates[0]
        return StepResult(
            step="dedup",
            passed=False,
            verdict=ValidationVerdict.REJECT,
            score=best["similarity"],
            details={
                "duplicates": duplicates,
                "threshold": threshold,
                "closest_id": best["id"],
                "closest_similarity": best["similarity"],
            },
        )

    return StepResult(
        step="dedup",
        passed=True,
        verdict=ValidationVerdict.ACCEPT,
        score=0.0,
        details={
            "threshold": threshold,
            "embedding_generated": True,
            "embedding": [float(v) for v in embedding],
        },
    )
