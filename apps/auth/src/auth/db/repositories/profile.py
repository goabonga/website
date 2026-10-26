# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""ProfileRepository — SQL access for :class:`UserProfile` rows."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.db.models.user import UserProfile


class ProfileRepository:
    """Data access for :class:`UserProfile` rows.

    Encapsulates every SQL query touching the ``user_profiles`` table.
    Methods return SQLAlchemy model instances and never commit — the caller
    (typically :class:`ProfileService`) owns the transaction boundary.
    """

    async def find_by_user_id(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> UserProfile | None:
        """Fetch a user profile by ``user_id`` (or ``None`` when absent)."""
        result = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
        return result.scalar_one_or_none()

    async def add(self, db: AsyncSession, profile: UserProfile) -> None:
        """Stage a new profile row and flush so generated columns are populated."""
        db.add(profile)
        await db.flush()

    async def stage(self, db: AsyncSession, profile: UserProfile) -> UserProfile:
        """Stage a new profile row without flushing.

        Used by callers that only need to attach a row to an already-flushed
        user and plan to commit themselves (e.g. admin edit flow).
        """
        db.add(profile)
        return profile

    async def flush(self, db: AsyncSession) -> None:
        """Flush pending changes (no commit)."""
        await db.flush()
