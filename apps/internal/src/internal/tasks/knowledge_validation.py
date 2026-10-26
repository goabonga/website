# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Celery task for asynchronous knowledge validation."""

import logging

from internal.celery import celery_app
from internal.database import get_sync_db_session
from internal.services.knowledge_validation import KnowledgeValidationService

logger = logging.getLogger(__name__)


@celery_app.task(
    name="knowledge.validate_entry",
    bind=True,
    queue="internal",
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def validate_knowledge_entry(self, entry_id: int) -> dict:
    """Validate a knowledge entry through the full pipeline.

    This task runs synchronously in the Celery worker using a sync DB session.
    """
    logger.info(
        "Validation task started | entry_id=%d task_id=%s",
        entry_id,
        self.request.id,
    )

    try:
        with get_sync_db_session() as db:
            service = KnowledgeValidationService()
            result = service.validate(entry_id, db)

        logger.info(
            "Validation task completed | entry_id=%d verdict=%s",
            entry_id,
            result.final_verdict.value,
        )
        return result.model_dump()

    except Exception as exc:
        logger.error(
            "Validation task failed | entry_id=%d error=%s",
            entry_id,
            str(exc),
        )
        raise self.retry(exc=exc)
