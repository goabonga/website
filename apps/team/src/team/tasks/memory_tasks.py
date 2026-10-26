# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Memory tasks - compress long-term memory."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from team.celery import celery_app
from team.config import settings
from team.database import async_session_factory
from team.models import MemoryEntry, Team
from team.services.embeddings import generate_embedding
from team.services.llm import get_completion
from team.tasks.utils import run_async

logger = logging.getLogger(__name__)

SUMMARY_SYSTEM_PROMPT = (
    "You are a memory compression assistant. "
    "Summarize the following memory entries into a single concise paragraph "
    "that preserves the most important facts and context. "
    "Output only the summary, nothing else."
)


async def _summarize() -> int:
    """Summarize old memory entries grouped by team."""
    if not settings.openai_api_key and not settings.anthropic_api_key:
        logger.warning("No LLM API key configured, skipping memory summarization")
        return 0

    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=24)
    summarized = 0

    async with async_session_factory() as session:
        # Get teams with old memory entries
        team_result = await session.execute(select(Team).where(Team.is_active.is_(True)))
        teams = list(team_result.scalars().all())

        for team in teams:
            # Get old entries (not already summaries)
            entries_result = await session.execute(
                select(MemoryEntry)
                .where(
                    MemoryEntry.team_id == team.id,
                    MemoryEntry.created_at < cutoff,
                )
                .order_by(MemoryEntry.created_at.asc())
                .limit(100)
            )
            entries = list(entries_result.scalars().all())

            if len(entries) < 2:
                continue

            # Filter out entries that are already summaries
            raw_entries = [e for e in entries if not e.extra.get("is_summary")]

            if len(raw_entries) < 2:
                continue

            # Concatenate content
            combined = "\n---\n".join(e.content for e in raw_entries)

            # Pick provider/model: prefer openai if available
            provider = "openai" if settings.openai_api_key else "anthropic"
            model = "gpt-4o" if provider == "openai" else "claude-sonnet-4-5-20250929"

            try:
                summary_text = await get_completion(
                    provider=provider,
                    model=model,
                    system_prompt=SUMMARY_SYSTEM_PROMPT,
                    user_message=combined,
                )
            except Exception:
                logger.exception(f"Failed to summarize memory for team {team.id}")
                continue

            # Generate embedding for the summary
            summary_embedding = await generate_embedding(summary_text)

            # Create summarized entry
            summary_entry = MemoryEntry(
                team_id=team.id,
                content=summary_text,
                extra={"is_summary": True, "source_count": len(raw_entries)},
                embedding=summary_embedding,
            )
            session.add(summary_entry)

            # Delete old entries
            for entry in raw_entries:
                await session.delete(entry)

            summarized += len(raw_entries)
            logger.info(f"Summarized {len(raw_entries)} entries for team {team.name}")

        await session.commit()

    return summarized


@celery_app.task(name="team.tasks.memory_tasks.summarize_memory")
def summarize_memory() -> dict:
    """Compress and summarize long-term memory entries.

    Runs every hour via Celery beat.
    """
    logger.info("Summarizing long-term memory entries")
    count = run_async(_summarize())
    logger.info(f"Summarized {count} memory entries")
    return {"summarized": count}
