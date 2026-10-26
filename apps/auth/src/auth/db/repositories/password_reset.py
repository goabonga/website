# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""PasswordResetRepository — SQL access for password-reset flows."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.db.models.user import PasswordResetToken, UserEmail, UserPassword


class PasswordResetRepository:
    """Data access for password-reset-related rows.

    Encapsulates every SQL query touching ``password_reset_tokens``,
    ``user_passwords`` and the verified-email lookup used by the password
    service. Methods return SQLAlchemy model instances and never commit —
    the caller owns the transaction boundary.
    """

    # ------------------------------------------------------------------
    # Verified email lookup
    # ------------------------------------------------------------------

    async def find_verified_user_email(
        self,
        db: AsyncSession,
        email: str,
    ) -> UserEmail | None:
        """Fetch a verified :class:`UserEmail` row by address (lowercased)."""
        result = await db.execute(
            select(UserEmail)
            .where(UserEmail.email == email.lower())
            .where(UserEmail.is_verified.is_(True))
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Reset-token queries
    # ------------------------------------------------------------------

    async def find_valid_by_hash(
        self,
        db: AsyncSession,
        token_hash: str,
        now: datetime,
    ) -> PasswordResetToken | None:
        """Fetch the most-recent unused, non-expired token matching ``token_hash``."""
        result = await db.execute(
            select(PasswordResetToken)
            .where(PasswordResetToken.token_hash == token_hash)
            .where(PasswordResetToken.expires_at > now)
            .where(PasswordResetToken.used_at.is_(None))
            .order_by(PasswordResetToken.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def add_reset_token(
        self,
        db: AsyncSession,
        token: PasswordResetToken,
    ) -> None:
        """Stage a new reset token row and flush."""
        db.add(token)
        await db.flush()

    # ------------------------------------------------------------------
    # UserPassword helpers
    # ------------------------------------------------------------------

    async def add_password(
        self,
        db: AsyncSession,
        password: UserPassword,
    ) -> None:
        """Stage a new password row (no flush — caller owns the boundary)."""
        db.add(password)

    async def find_user_for_reset(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ):
        """Fetch a user row by ID (used during reset flow)."""
        from auth.db.models.user import User

        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()
