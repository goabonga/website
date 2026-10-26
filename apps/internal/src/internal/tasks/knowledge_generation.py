# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Celery task for asynchronous knowledge generation."""

import logging

from internal.celery import celery_app
from internal.config import settings
from internal.database import get_sync_db_session
from internal.models.knowledge import KnowledgeEntry, KnowledgeEntryStatus, KnowledgeNamespace

logger = logging.getLogger(__name__)


@celery_app.task(
    name="knowledge.generate_entries",
    bind=True,
    queue="internal",
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def generate_knowledge_entries(
    self,
    source_text: str,
    num_entries: int,
    context: str | None,
    namespace_id: int,
) -> dict:
    """Generate knowledge entries from source text using OpenAI.

    This task runs synchronously in the Celery worker using sync services.
    """
    logger.info(
        "Generation task started | namespace_id=%d num_entries=%d task_id=%s",
        namespace_id,
        num_entries,
        self.request.id,
    )

    try:
        self.update_state(
            state="PROGRESS",
            meta={"step": "generating", "current": 0, "total": num_entries},
        )

        # Generate entries using sync OpenAI client
        from internal.services.knowledge_generator_sync import SyncKnowledgeGeneratorService

        generator = SyncKnowledgeGeneratorService()
        generated = generator.generate_entries(
            source_text=source_text,
            num_entries=num_entries,
            context=context,
        )

        if not generated:
            return {"created_count": 0, "entry_ids": [], "namespace_slug": ""}

        self.update_state(
            state="PROGRESS",
            meta={"step": "embedding", "current": 0, "total": len(generated)},
        )

        # Create entries with embeddings in sync DB session
        from internal.services.embeddings_sync import SyncEmbeddingService

        embedding_service = SyncEmbeddingService() if settings.openai_api_key else None

        with get_sync_db_session() as db:
            # Resolve namespace slug for redirect
            ns = db.get(KnowledgeNamespace, namespace_id)
            namespace_slug = ns.slug if ns else "general"

            created_entries = []
            for i, entry_data in enumerate(generated):
                question = entry_data.get("question", "").strip()
                answer = entry_data.get("answer", "").strip()
                metadata = entry_data.get("metadata", {})

                if not question or not answer:
                    continue

                # Generate embedding
                embedding = None
                if embedding_service:
                    try:
                        embedding = embedding_service.generate(question)
                    except Exception as e:
                        logger.warning("Failed to generate embedding: %s", e)

                entry = KnowledgeEntry(
                    question=question,
                    answer=answer,
                    embedding=embedding,
                    metadata_=metadata,
                    namespace_id=namespace_id,
                )

                if settings.validation_enabled:
                    entry.status = KnowledgeEntryStatus.PENDING.value

                db.add(entry)
                created_entries.append(entry)

                self.update_state(
                    state="PROGRESS",
                    meta={
                        "step": "embedding",
                        "current": i + 1,
                        "total": len(generated),
                    },
                )

            db.commit()

            entry_ids = [e.id for e in created_entries]

            # Dispatch validation tasks
            if settings.validation_enabled:
                try:
                    from internal.tasks.knowledge_validation import validate_knowledge_entry

                    for entry in created_entries:
                        validate_knowledge_entry.delay(entry.id)
                except Exception:
                    logger.warning("Failed to dispatch validation tasks for generated entries")

        created_count = len(created_entries)
        logger.info(
            "Generation task completed | created_count=%d namespace=%s",
            created_count,
            namespace_slug,
        )

        return {
            "created_count": created_count,
            "entry_ids": entry_ids,
            "namespace_slug": namespace_slug,
        }

    except Exception as exc:
        logger.error(
            "Generation task failed | error=%s",
            str(exc),
        )
        raise self.retry(exc=exc)
