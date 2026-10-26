# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""SessionRepository — SQL access for Session rows."""

from __future__ import annotations

import uuid
from builtins import list as BuiltinList
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth.db.models.user import Session, User


class SessionRepository:
    """Data access for Session rows.

    Encapsulates every SQL query touching the ``sessions`` table. Methods
    return SQLAlchemy model instances and never commit — the caller owns
    the transaction boundary.
    """

    async def find_by_id(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
    ) -> Session | None:
        """Fetch a session by its primary key."""
        result = await db.execute(select(Session).where(Session.id == session_id))
        return result.scalar_one_or_none()

    async def find_by_token_hash_with_user(
        self,
        db: AsyncSession,
        token_hash: str,
    ) -> Session | None:
        """Fetch a non-revoked session by token hash with ``user`` eager-loaded.

        Expiration is checked by the caller. Returns ``None`` when no row
        matches or the session has been revoked.
        """
        stmt = (
            select(Session)
            .options(selectinload(Session.user))
            .where(Session.session_token_hash == token_hash)
            .where(Session.revoked_at.is_(None))
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_token_hash(
        self,
        db: AsyncSession,
        token_hash: str,
        *,
        active_only: bool = True,
    ) -> Session | None:
        """Fetch a session by its (hashed) session token.

        When ``active_only`` is True the query is restricted to sessions
        that are neither revoked nor expired — matching the semantics of
        :meth:`SessionService.get_session_by_token`.
        """
        stmt = select(Session).where(Session.session_token_hash == token_hash)
        if active_only:
            now = datetime.now(UTC)
            stmt = stmt.where(Session.expires_at > now).where(Session.revoked_at.is_(None))
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def find_active_for_user(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Session | None:
        """Fetch an active (non-revoked, non-expired) session belonging to ``user_id``."""
        now = datetime.now(UTC)
        stmt = (
            select(Session)
            .where(Session.id == session_id)
            .where(Session.user_id == user_id)
            .where(Session.revoked_at.is_(None))
            .where(Session.expires_at > now)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def find_unrevoked_by_id(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
    ) -> Session | None:
        """Fetch a session that has not yet been revoked (ignores expiry)."""
        stmt = select(Session).where(
            Session.id == session_id,
            Session.revoked_at.is_(None),
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_id_with_user(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
    ) -> Session | None:
        """Fetch a session by ID eager-loading its ``user`` and ``user.emails``."""
        stmt = (
            select(Session)
            .options(selectinload(Session.user).selectinload(User.emails))
            .where(Session.id == session_id)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self,
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
        user_id: uuid.UUID | None = None,
        active_only: bool = False,
        with_user: bool = False,
    ) -> tuple[BuiltinList[Session], int]:
        """List sessions with filters and pagination.

        Returns a ``(sessions, total)`` tuple, ordered by ``created_at``
        descending. When ``with_user`` is True the sessions are returned
        with ``user`` (and ``user.emails``) eager-loaded.
        """
        now = datetime.now(UTC)
        offset = (page - 1) * page_size

        query = select(Session)
        count_query = select(func.count()).select_from(Session)

        if with_user:
            query = query.options(selectinload(Session.user).selectinload(User.emails))

        if user_id is not None:
            query = query.where(Session.user_id == user_id)
            count_query = count_query.where(Session.user_id == user_id)

        if active_only:
            query = query.where(Session.revoked_at.is_(None)).where(Session.expires_at > now)
            count_query = count_query.where(Session.revoked_at.is_(None)).where(
                Session.expires_at > now
            )

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(Session.created_at.desc()).offset(offset).limit(page_size)
        result = await db.execute(query)
        sessions = list(result.scalars().all())

        return sessions, total

    async def list_for_user(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        *,
        active_only: bool = True,
    ) -> BuiltinList[Session]:
        """Return every session for ``user_id`` (helper without pagination).

        Sessions are ordered by ``created_at`` descending. When
        ``active_only`` is True (the default) revoked or expired sessions
        are excluded.
        """
        stmt = select(Session).where(Session.user_id == user_id)
        if active_only:
            now = datetime.now(UTC)
            stmt = stmt.where(Session.revoked_at.is_(None)).where(Session.expires_at > now)
        stmt = stmt.order_by(Session.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def list_active_for_user(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        *,
        except_session_id: uuid.UUID | None = None,
    ) -> BuiltinList[Session]:
        """Return active sessions for a user, optionally excluding one by ID."""
        now = datetime.now(UTC)
        stmt = (
            select(Session)
            .where(Session.user_id == user_id)
            .where(Session.revoked_at.is_(None))
            .where(Session.expires_at > now)
        )
        if except_session_id is not None:
            stmt = stmt.where(Session.id != except_session_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def list_active(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID | None = None,
    ) -> BuiltinList[Session]:
        """Return every currently-active session (non-revoked, non-expired)."""
        now = datetime.now(UTC)
        stmt = select(Session).where(
            Session.revoked_at.is_(None),
            Session.expires_at > now,
        )
        if user_id is not None:
            stmt = stmt.where(Session.user_id == user_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def list_expired_before(
        self,
        db: AsyncSession,
        cutoff: datetime,
    ) -> BuiltinList[Session]:
        """Return sessions whose ``expires_at`` is before ``cutoff``."""
        stmt = select(Session).where(Session.expires_at < cutoff)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def count_active_for_user(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> int:
        """Return the number of active sessions for ``user_id``."""
        now = datetime.now(UTC)
        stmt = (
            select(func.count())
            .select_from(Session)
            .where(Session.user_id == user_id)
            .where(Session.revoked_at.is_(None))
            .where(Session.expires_at > now)
        )
        result = await db.execute(stmt)
        return result.scalar() or 0

    async def count_active(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID | None = None,
    ) -> int:
        """Return the number of currently active (non-revoked, non-expired) sessions.

        When ``user_id`` is provided, the count is restricted to that user.
        """
        now = datetime.now(UTC)
        stmt = (
            select(func.count())
            .select_from(Session)
            .where(Session.revoked_at.is_(None))
            .where(Session.expires_at > now)
        )
        if user_id is not None:
            stmt = stmt.where(Session.user_id == user_id)
        result = await db.execute(stmt)
        return result.scalar() or 0

    async def add(self, db: AsyncSession, session: Session) -> None:
        """Stage a new session row and flush."""
        db.add(session)
        await db.flush()

    async def revoke(
        self,
        db: AsyncSession,
        session: Session,
        *,
        at: datetime | None = None,
    ) -> None:
        """Mark ``session`` as revoked (sets ``revoked_at``) and flush."""
        session.revoked_at = at or datetime.now(UTC)
        await db.flush()

    async def revoke_many(
        self,
        db: AsyncSession,
        sessions: BuiltinList[Session],
        *,
        at: datetime | None = None,
    ) -> None:
        """Mark every session in ``sessions`` as revoked and flush."""
        revoked_at = at or datetime.now(UTC)
        for session in sessions:
            session.revoked_at = revoked_at
        await db.flush()

    async def touch_expiry(
        self,
        db: AsyncSession,
        session: Session,
        expires_at: datetime,
    ) -> None:
        """Update ``session.expires_at`` and flush."""
        session.expires_at = expires_at
        await db.flush()

    async def delete(self, db: AsyncSession, session: Session) -> None:
        """Stage a session deletion (no commit)."""
        await db.delete(session)


__all__ = ["SessionRepository"]
