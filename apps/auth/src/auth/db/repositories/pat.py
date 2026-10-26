# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""PATRepository — SQL access for Personal Access Token rows."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth.db.models.pat import PersonalAccessToken


class PATRepository:
    """Data access for :class:`PersonalAccessToken` rows.

    Encapsulates every SQL query touching the ``personal_access_tokens``
    table. Methods return SQLAlchemy model instances and never commit —
    the caller owns the transaction boundary.
    """

    async def find_by_id(
        self,
        db: AsyncSession,
        pat_id: uuid.UUID,
    ) -> PersonalAccessToken | None:
        """Fetch a PAT by ID."""
        result = await db.execute(
            select(PersonalAccessToken).where(PersonalAccessToken.id == pat_id)
        )
        return result.scalar_one_or_none()

    async def find_by_id_and_user(
        self,
        db: AsyncSession,
        pat_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> PersonalAccessToken | None:
        """Fetch a PAT by ID with an ownership check on ``user_id``."""
        result = await db.execute(
            select(PersonalAccessToken)
            .where(PersonalAccessToken.id == pat_id)
            .where(PersonalAccessToken.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def find_active_by_token_hash(
        self,
        db: AsyncSession,
        token_hash: str,
        now: datetime,
    ) -> PersonalAccessToken | None:
        """Fetch a non-revoked, non-expired PAT by its token hash.

        The associated :class:`User` is eager-loaded so callers can check
        ``pat.user.is_active`` without an extra query.
        """
        result = await db.execute(
            select(PersonalAccessToken)
            .options(selectinload(PersonalAccessToken.user))
            .where(PersonalAccessToken.token_hash == token_hash)
            .where(PersonalAccessToken.revoked_at.is_(None))
            .where(
                or_(
                    PersonalAccessToken.expires_at.is_(None),
                    PersonalAccessToken.expires_at > now,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_by_user(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        *,
        include_revoked: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[PersonalAccessToken], int]:
        """List PATs owned by a user.

        Returns a ``(tokens, total)`` tuple. Tokens are ordered by
        ``created_at`` descending. When ``include_revoked`` is False,
        revoked rows are excluded from both the count and the page.
        """
        query = select(PersonalAccessToken).where(PersonalAccessToken.user_id == user_id)

        if not include_revoked:
            query = query.where(PersonalAccessToken.revoked_at.is_(None))

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(PersonalAccessToken.created_at.desc()).offset(offset).limit(limit)
        result = await db.execute(query)
        tokens = result.scalars().all()

        return tokens, total

    async def list_all(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID | None = None,
        include_revoked: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[PersonalAccessToken], int]:
        """List PATs across all users (admin view).

        Returns a ``(tokens, total)`` tuple. The owning :class:`User` is
        eager-loaded on each row. Tokens are ordered by ``created_at``
        descending. When ``user_id`` is provided, the query is restricted
        to that user. When ``include_revoked`` is False, revoked rows are
        excluded from both the count and the page.
        """
        query = select(PersonalAccessToken)

        if user_id is not None:
            query = query.where(PersonalAccessToken.user_id == user_id)

        if not include_revoked:
            query = query.where(PersonalAccessToken.revoked_at.is_(None))

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        query = (
            query.options(selectinload(PersonalAccessToken.user))
            .order_by(PersonalAccessToken.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(query)
        tokens = result.scalars().all()

        return tokens, total

    async def list_active_by_user(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> Sequence[PersonalAccessToken]:
        """Fetch every non-revoked PAT for a user (no pagination)."""
        result = await db.execute(
            select(PersonalAccessToken)
            .where(PersonalAccessToken.user_id == user_id)
            .where(PersonalAccessToken.revoked_at.is_(None))
        )
        return result.scalars().all()

    async def list_active(
        self,
        db: AsyncSession,
    ) -> Sequence[PersonalAccessToken]:
        """Fetch every non-revoked PAT across all users (no pagination)."""
        result = await db.execute(
            select(PersonalAccessToken).where(PersonalAccessToken.revoked_at.is_(None))
        )
        return result.scalars().all()

    async def list_for_cleanup(
        self,
        db: AsyncSession,
        *,
        expired_cutoff: datetime,
        revoked_cutoff: datetime,
    ) -> Sequence[PersonalAccessToken]:
        """Fetch PATs whose expiry or revocation is past the grace cutoff."""
        result = await db.execute(
            select(PersonalAccessToken).where(
                or_(
                    PersonalAccessToken.expires_at < expired_cutoff,
                    PersonalAccessToken.revoked_at < revoked_cutoff,
                )
            )
        )
        return result.scalars().all()

    async def add(self, db: AsyncSession, pat: PersonalAccessToken) -> None:
        """Stage a new PAT row and flush to obtain its generated ID."""
        db.add(pat)
        await db.flush()

    async def delete(self, db: AsyncSession, pat: PersonalAccessToken) -> None:
        """Stage a PAT deletion (no commit)."""
        await db.delete(pat)
