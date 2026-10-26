# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""UserRepository — SQL access for User rows."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth.db.models.user import User, UserEmail, UserPassword, UserProfile


class UserRepository:
    """Data access for User rows.

    Encapsulates every SQL query touching the ``users`` table. Methods
    return SQLAlchemy model instances and never commit — the caller owns
    the transaction boundary.
    """

    async def find_by_id(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> User | None:
        """Fetch a user by ID with ``emails`` and ``profile`` eager-loaded."""
        result = await db.execute(
            select(User)
            .options(selectinload(User.emails), selectinload(User.profile))
            .where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def find_by_email(
        self,
        db: AsyncSession,
        email: str,
    ) -> User | None:
        """Fetch a user by primary email address (case-insensitive)."""
        result = await db.execute(
            select(User).join(UserEmail).where(UserEmail.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def find_verified_email_with_user(
        self,
        db: AsyncSession,
        email: str,
    ) -> UserEmail | None:
        """Fetch a verified :class:`UserEmail` row with ``user`` eager-loaded.

        Used by authentication flows that need both the email row and the
        owning user without issuing a second query.
        """
        result = await db.execute(
            select(UserEmail)
            .where(UserEmail.email == email.lower())
            .where(UserEmail.is_verified == True)  # noqa: E712
            .options(selectinload(UserEmail.user))
        )
        return result.scalar_one_or_none()

    async def find_by_id_with_passwords(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> User | None:
        """Fetch a user by ID with ``passwords`` eager-loaded."""
        result = await db.execute(
            select(User).where(User.id == user_id).options(selectinload(User.passwords))
        )
        return result.scalar_one_or_none()

    async def find_primary_email_row(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> UserEmail | None:
        """Fetch the primary :class:`UserEmail` row for ``user_id`` (or ``None``)."""
        result = await db.execute(
            select(UserEmail)
            .where(UserEmail.user_id == user_id)
            .where(UserEmail.is_primary == True)  # noqa: E712
        )
        return result.scalar_one_or_none()

    async def find_first_verified_email_row(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> UserEmail | None:
        """Fetch the oldest verified :class:`UserEmail` row for ``user_id``.

        Intended as a fallback when a user has no primary email. Ordered by
        ``created_at`` ascending and limited to one row.
        """
        result = await db.execute(
            select(UserEmail)
            .where(UserEmail.user_id == user_id)
            .where(UserEmail.is_verified == True)  # noqa: E712
            .order_by(UserEmail.created_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def email_exists(
        self,
        db: AsyncSession,
        email: str,
    ) -> bool:
        """Return True if an email address is already registered."""
        result = await db.execute(select(UserEmail.id).where(UserEmail.email == email.lower()))
        return result.scalar_one_or_none() is not None

    async def find_user_email_row(
        self,
        db: AsyncSession,
        email: str,
    ) -> UserEmail | None:
        """Fetch a :class:`UserEmail` row by exact address (lowercased)."""
        result = await db.execute(select(UserEmail).where(UserEmail.email == email.lower()))
        return result.scalar_one_or_none()

    async def find_primary_email(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> str | None:
        """Return the primary email address for ``user_id`` (if any)."""
        result = await db.execute(
            select(UserEmail.email)
            .where(UserEmail.user_id == user_id)
            .where(UserEmail.is_primary.is_(True))
        )
        return result.scalar_one_or_none()

    async def search_with_primary_email(
        self,
        db: AsyncSession,
        *,
        search: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[tuple[User, UserEmail]], int]:
        """Search users by substring on their *primary* email.

        Returns ``(rows, total)`` where each row is a ``(User, UserEmail)``
        tuple for the user's primary email. Ordered by ``User.created_at``
        descending. Used by admin flows that need to expose the email
        alongside the user without eager-loading the full ``emails``
        collection.
        """
        offset = (page - 1) * page_size

        filter_clause = (UserEmail.user_id == User.id) & (UserEmail.is_primary.is_(True))

        count_query = (
            select(func.count())
            .select_from(User)
            .join(UserEmail, filter_clause)
            .where(UserEmail.email.ilike(f"%{search}%"))
        )
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        query = (
            select(User, UserEmail)
            .join(UserEmail, filter_clause)
            .where(UserEmail.email.ilike(f"%{search}%"))
            .order_by(User.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await db.execute(query)
        rows = [(u, e) for u, e in result.all()]

        return rows, total

    async def list(
        self,
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        is_active: bool | None = None,
        registration_tenant_id: uuid.UUID | None = None,
        filter_no_tenant: bool = False,
    ) -> tuple[list[User], int]:
        """List users with filters and pagination.

        Returns a ``(users, total)`` tuple. Users are eager-loaded with
        their ``emails`` and ``profile`` relations and ordered by
        ``created_at`` descending. Filters are ANDed together.

        Args:
            db: Database session.
            page: 1-indexed page number.
            page_size: Items per page.
            search: Case-insensitive substring match on any of the user's
                email addresses. Joins ``user_emails``.
            is_active: Filter on ``User.is_active``.
            registration_tenant_id: Only return users registered under this
                tenant. Ignored when ``filter_no_tenant`` is True.
            filter_no_tenant: Only return users with no
                ``registration_tenant_id``. Overrides ``registration_tenant_id``.
        """
        offset = (page - 1) * page_size

        query = select(User).options(
            selectinload(User.emails),
            selectinload(User.profile),
        )
        count_query = select(func.count()).select_from(User)

        if is_active is not None:
            query = query.where(User.is_active == is_active)
            count_query = count_query.where(User.is_active == is_active)

        if filter_no_tenant:
            query = query.where(User.registration_tenant_id.is_(None))
            count_query = count_query.where(User.registration_tenant_id.is_(None))
        elif registration_tenant_id is not None:
            query = query.where(User.registration_tenant_id == registration_tenant_id)
            count_query = count_query.where(User.registration_tenant_id == registration_tenant_id)

        if search:
            query = query.join(UserEmail).where(UserEmail.email.ilike(f"%{search}%"))
            count_query = count_query.join(UserEmail).where(UserEmail.email.ilike(f"%{search}%"))

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(User.created_at.desc()).offset(offset).limit(page_size)
        result = await db.execute(query)
        users = list(result.scalars().unique().all())

        return users, total

    async def count(
        self,
        db: AsyncSession,
        *,
        is_active: bool | None = None,
        created_since: datetime | None = None,
    ) -> int:
        """Count users matching optional filters.

        Args:
            db: Database session.
            is_active: Restrict to users with this ``is_active`` value.
            created_since: Only count users whose ``created_at`` is greater
                than or equal to this timestamp.
        """
        query = select(func.count()).select_from(User)
        if is_active is not None:
            query = query.where(User.is_active == is_active)
        if created_since is not None:
            query = query.where(User.created_at >= created_since)
        result = await db.execute(query)
        return result.scalar() or 0

    async def add(self, db: AsyncSession, user: User) -> None:
        """Stage a new user row and flush to obtain its generated ID."""
        db.add(user)
        await db.flush()

    async def delete(self, db: AsyncSession, user: User) -> None:
        """Stage a user deletion (no commit)."""
        await db.delete(user)

    async def add_email(self, db: AsyncSession, email: UserEmail) -> UserEmail:
        """Stage a new :class:`UserEmail` row (no flush — attached to user)."""
        db.add(email)
        return email

    async def delete_email(self, db: AsyncSession, email: UserEmail) -> None:
        """Stage a :class:`UserEmail` deletion (no commit)."""
        await db.delete(email)

    async def add_password(
        self,
        db: AsyncSession,
        password: UserPassword,
    ) -> UserPassword:
        """Stage a new :class:`UserPassword` row (no flush — attached to user)."""
        db.add(password)
        return password

    async def add_profile(
        self,
        db: AsyncSession,
        profile: UserProfile,
    ) -> UserProfile:
        """Stage a new :class:`UserProfile` row (no flush — attached to user)."""
        db.add(profile)
        return profile
