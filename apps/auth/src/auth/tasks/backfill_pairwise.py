# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Backfill task for pairwise subject identifiers."""

import logging

from auth.celery import celery_app
from auth.core.database import get_sync_db
from auth.db.repositories.cleanup import cleanup_repository

logger = logging.getLogger(__name__)


@celery_app.task(name="backfill_pairwise_subjects", ignore_result=True)
def backfill_pairwise_subjects() -> dict:
    """Pre-populate pairwise subjects for existing (user, tenant) pairs.

    Scans access_tokens to find unique (user_id, client.tenant_id) pairs,
    resolves tenant_id (using platform tenant for NULL),
    and inserts a pairwise subject for each pair that does not yet exist.

    Returns:
        Dict with stats: {"created": N, "existing": M, "total": N+M}.
    """
    created = 0
    existing = 0

    with get_sync_db() as db:
        platform_tenant_id = cleanup_repository.find_platform_tenant_id(db)

        if platform_tenant_id is None:
            logger.error("No platform tenant found (is_platform=True), aborting backfill")
            return {"created": 0, "existing": 0, "total": 0, "error": "no_platform_tenant"}

        pairs = cleanup_repository.list_access_token_user_tenant_pairs(
            db, fallback_tenant_id=platform_tenant_id
        )

        for user_id, tenant_id in pairs:
            if cleanup_repository.insert_pairwise_subject_if_missing(
                db, user_id=user_id, tenant_id=tenant_id
            ):
                created += 1
            else:
                existing += 1

    total = created + existing
    logger.info(
        "Pairwise backfill completed: %d created, %d already existed, %d total pairs",
        created,
        existing,
        total,
    )

    return {"created": created, "existing": existing, "total": total}
