# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""EmailVerificationRepository — SQL access for email verification codes."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.db.models.user import UserEmail, VerificationCode


class EmailVerificationRepository:
    """Data access for :class:`VerificationCode` rows and the related email lookup.

    Encapsulates every SQL query touching the ``verification_codes`` table
    and the ``user_emails`` lookup needed by the email service's
    ``verify_code`` flow. Methods return SQLAlchemy model instances and
    never commit — the caller owns the transaction boundary.
    """

    async def find_valid_for_email(
        self,
        db: AsyncSession,
        email: str,
        now: datetime,
    ) -> VerificationCode | None:
        """Find any valid (unused, non-expired) code for ``email``."""
        result = await db.execute(
            select(VerificationCode)
            .where(VerificationCode.email == email.lower())
            .where(VerificationCode.expires_at > now)
            .where(VerificationCode.used_at.is_(None))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def find_valid_by_hash(
        self,
        db: AsyncSession,
        email: str,
        code_hash: str,
        now: datetime,
    ) -> VerificationCode | None:
        """Find the most recent valid code matching ``email`` and ``code_hash``."""
        result = await db.execute(
            select(VerificationCode)
            .where(VerificationCode.email == email.lower())
            .where(VerificationCode.code_hash == code_hash)
            .where(VerificationCode.expires_at > now)
            .where(VerificationCode.used_at.is_(None))
            .order_by(VerificationCode.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def find_user_email(
        self,
        db: AsyncSession,
        email: str,
    ) -> UserEmail | None:
        """Fetch the :class:`UserEmail` row for ``email`` (lowercased)."""
        result = await db.execute(select(UserEmail).where(UserEmail.email == email.lower()))
        return result.scalar_one_or_none()

    async def add(self, db: AsyncSession, code: VerificationCode) -> None:
        """Stage a new verification code row and flush."""
        db.add(code)
        await db.flush()
