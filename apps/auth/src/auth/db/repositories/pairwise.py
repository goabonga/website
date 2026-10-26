# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""PairwiseSubjectRepository — SQL access for PairwiseSubject rows."""

from __future__ import annotations

import uuid

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from auth.db.models.pairwise import PairwiseSubject
from auth.db.models.tenant import Tenant


class PairwiseSubjectRepository:
    """Data access for ``pairwise_subjects`` rows.

    Encapsulates every SQL query touching the ``pairwise_subjects`` table.
    Methods return SQLAlchemy model instances or primitive values and never
    commit — the caller owns the transaction boundary.
    """

    async def find_by_user_and_tenant(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> uuid.UUID | None:
        """Return the ``sub_value`` for a ``(user, tenant)`` pair (if any)."""
        result = await db.execute(
            select(PairwiseSubject.sub_value).where(
                PairwiseSubject.user_id == user_id,
                PairwiseSubject.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def find_by_sub(
        self,
        db: AsyncSession,
        sub_value: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> uuid.UUID | None:
        """Resolve a pairwise ``sub_value`` back to the real ``user_id`` for a tenant."""
        result = await db.execute(
            select(PairwiseSubject.user_id).where(
                PairwiseSubject.sub_value == sub_value,
                PairwiseSubject.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> list[PairwiseSubject]:
        """Return every pairwise subject row for a user."""
        result = await db.execute(select(PairwiseSubject).where(PairwiseSubject.user_id == user_id))
        return list(result.scalars().all())

    async def add(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        sub_value: uuid.UUID,
    ) -> None:
        """Insert a new pairwise row, silently skipping conflicts on ``(user_id, tenant_id)``.

        Uses PostgreSQL ``INSERT ... ON CONFLICT DO NOTHING`` so concurrent
        callers can race safely on the unique constraint
        ``uq_pairwise_user_tenant``. The caller should follow up with a
        :meth:`find_by_user_and_tenant` to obtain the definitive winning row.
        """
        stmt = (
            pg_insert(PairwiseSubject)
            .values(
                id=uuid.uuid4(),
                user_id=user_id,
                tenant_id=tenant_id,
                sub_value=sub_value,
            )
            .on_conflict_do_nothing(constraint="uq_pairwise_user_tenant")
        )
        await db.execute(stmt)
        await db.flush()

    async def delete_for_tenant(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> int:
        """Delete every pairwise subject row for a tenant and return the row count."""
        result: CursorResult[tuple[()]] = await db.execute(  # type: ignore[assignment]
            delete(PairwiseSubject).where(PairwiseSubject.tenant_id == tenant_id)
        )
        return result.rowcount or 0

    async def find_platform_tenant_id(self, db: AsyncSession) -> uuid.UUID | None:
        """Return the platform tenant's ID (``is_platform=True``) if one exists."""
        result = await db.execute(select(Tenant.id).where(Tenant.is_platform.is_(True)).limit(1))
        return result.scalar_one_or_none()
