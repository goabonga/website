# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Retrievability test: generate candidate questions, verify the chunk is searchable."""

import json
import logging

from openai import OpenAI
from sqlalchemy import text
from sqlalchemy.orm import Session

from internal.config import settings
from internal.schemas.validation import StepResult, ValidationVerdict

logger = logging.getLogger(__name__)

QUESTION_GEN_PROMPT = """Given this knowledge base entry, generate 3 diverse questions that a user might ask and that this entry should answer. Return ONLY a JSON object with a "questions" key containing an array of strings.

Question: {question}
Answer: {answer}

Return: {{"questions": ["question1", "question2", "question3"]}}"""


def validate_retrievability(
    question: str,
    answer: str,
    entry_id: int,
    embedding: list[float] | None,
    db: Session,
) -> StepResult:
    """Generate candidate queries and test if the entry appears in top results."""
    if not settings.openai_api_key or embedding is None:
        return StepResult(
            step="retrievability",
            passed=True,
            verdict=ValidationVerdict.ACCEPT,
            details={"skipped": "OpenAI not configured or no embedding"},
        )

    client = OpenAI(api_key=settings.openai_api_key)

    # Step 1: Generate candidate questions
    try:
        response = client.chat.completions.create(
            model=settings.validation_semantic_model,
            messages=[
                {
                    "role": "user",
                    "content": QUESTION_GEN_PROMPT.format(question=question, answer=answer),
                },
            ],
            temperature=0.7,
            response_format={"type": "json_object"},
            max_tokens=300,
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        # Handle both array and object with questions key
        if isinstance(data, list):
            candidate_questions = data
        elif isinstance(data, dict):
            candidate_questions = next((v for v in data.values() if isinstance(v, list)), [])
        else:
            candidate_questions = []
    except Exception as e:
        logger.error("Failed to generate candidate questions: %s", e)
        return StepResult(
            step="retrievability",
            passed=True,
            verdict=ValidationVerdict.NEEDS_REVIEW,
            error=str(e),
        )

    if not candidate_questions:
        return StepResult(
            step="retrievability",
            passed=True,
            verdict=ValidationVerdict.NEEDS_REVIEW,
            details={"error": "no candidate questions generated"},
        )

    # Step 2: For each candidate question, generate its embedding and search
    hits = 0
    search_results = []

    for cq in candidate_questions[:3]:
        try:
            emb_response = client.embeddings.create(
                model=settings.rag_embedding_model,
                input=cq,
            )
            cq_embedding = emb_response.data[0].embedding
            cq_embedding_str = f"[{','.join(str(v) for v in cq_embedding)}]"

            # Search top 5 results
            result = db.execute(
                text("""
                    SELECT id, 1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
                    FROM knowledge_base
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding <=> CAST(:embedding AS vector)
                    LIMIT 5
                """),
                {"embedding": cq_embedding_str},
            )
            top_ids = [row.id for row in result]
            found = entry_id in top_ids
            if found:
                hits += 1
            search_results.append(
                {
                    "query": cq[:100],
                    "found_in_top5": found,
                    "top_ids": top_ids,
                }
            )
        except Exception as e:
            logger.warning("Retrievability search failed for query '%s': %s", cq[:50], e)
            search_results.append({"query": cq[:100], "error": str(e)})

    min_hits = settings.validation_retrievability_min_hits
    passed = hits >= min_hits

    verdict = ValidationVerdict.NEEDS_REVIEW if not passed else ValidationVerdict.ACCEPT

    return StepResult(
        step="retrievability",
        passed=passed,
        verdict=verdict,
        score=hits / max(len(candidate_questions), 1),
        details={
            "hits": hits,
            "total_queries": len(candidate_questions),
            "min_hits_required": min_hits,
            "search_results": search_results,
        },
    )
