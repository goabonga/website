# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""MFARepository — SQL access for MFA-related rows."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth.db.models.user import MFAEmailCode, UserMFA


class MFARepository:
    """Data access for MFA rows.

    Encapsulates SQL queries touching ``user_mfa``, ``mfa_backup_codes`` and
    ``mfa_email_codes``. Methods return SQLAlchemy model instances and never
    commit — the caller owns the transaction boundary.
    """

    async def find_user_mfa(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> UserMFA | None:
        """Fetch the :class:`UserMFA` row for ``user_id`` with backup codes eager-loaded."""
        result = await db.execute(
            select(UserMFA)
            .where(UserMFA.user_id == user_id)
            .options(selectinload(UserMFA.backup_codes))
        )
        return result.scalar_one_or_none()

    async def find_valid_email_code(
        self,
        db: AsyncSession,
        user_id: str,
        code_hash: str,
        *,
        now: datetime,
    ) -> MFAEmailCode | None:
        """Fetch the most recent unused, unexpired email MFA code for ``user_id``.

        Matches on ``code_hash`` and requires ``expires_at > now`` and
        ``used_at IS NULL``. Returns the newest matching code or ``None``.
        """
        result = await db.execute(
            select(MFAEmailCode)
            .where(MFAEmailCode.user_id == user_id)
            .where(MFAEmailCode.code_hash == code_hash)
            .where(MFAEmailCode.expires_at > now)
            .where(MFAEmailCode.used_at == None)  # noqa: E711
            .order_by(MFAEmailCode.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def add(self, db: AsyncSession, instance: object) -> None:
        """Stage a new MFA row and flush so generated columns (id) are populated."""
        db.add(instance)
        await db.flush()

    async def stage(self, db: AsyncSession, instance: object) -> object:
        """Stage a new MFA row without flushing.

        Used by batch operations (backup-code regeneration) that share a
        single final flush.
        """
        db.add(instance)
        return instance

    async def delete(self, db: AsyncSession, instance: object) -> None:
        """Stage a row deletion (no commit)."""
        await db.delete(instance)
