# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""JWKRepository — SQL access for JWK rows."""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from auth.db.models.jwk import JWK


class JWKRepository:
    """Data access for JWK rows.

    Encapsulates every SQL query touching the ``jwks`` table. Methods
    return SQLAlchemy model instances and never commit — the caller owns
    the transaction boundary.
    """

    async def find_by_id(
        self,
        db: AsyncSession,
        key_uuid: uuid.UUID,
    ) -> JWK | None:
        """Fetch a key by its primary-key UUID."""
        result = await db.execute(select(JWK).where(JWK.id == key_uuid))
        return result.scalar_one_or_none()

    async def find_by_kid(
        self,
        db: AsyncSession,
        kid: str,
    ) -> JWK | None:
        """Fetch a key by its ``kid`` identifier."""
        result = await db.execute(select(JWK).where(JWK.kid == kid))
        return result.scalar_one_or_none()

    async def find_active(self, db: AsyncSession) -> JWK | None:
        """Fetch the currently active signing key, if any."""
        result = await db.execute(
            select(JWK).where(JWK.is_active == True).limit(1)  # noqa: E712
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        db: AsyncSession,
        *,
        include_revoked: bool = False,
        active_only: bool = False,
    ) -> list[JWK]:
        """List keys ordered by ``created_at`` descending.

        Args:
            db: Database session.
            include_revoked: If False (default), revoked keys are excluded.
                If True, every key (including revoked) is returned.
            active_only: If True, only the active key is returned. Overrides
                ``include_revoked``.
        """
        query = select(JWK)

        if active_only:
            query = query.where(JWK.is_active == True)  # noqa: E712
        elif not include_revoked:
            query = query.where(JWK.revoked_at == None)  # noqa: E711

        query = query.order_by(JWK.created_at.desc())
        result = await db.execute(query)
        return list(result.scalars().all())

    async def deactivate_all(self, db: AsyncSession) -> None:
        """Deactivate every key (bulk update, no commit)."""
        await db.execute(update(JWK).values(is_active=False))

    async def deactivate_active(self, db: AsyncSession) -> None:
        """Deactivate keys currently marked active (bulk update, no commit)."""
        await db.execute(
            update(JWK).where(JWK.is_active == True).values(is_active=False)  # noqa: E712
        )

    async def add(self, db: AsyncSession, jwk: JWK) -> None:
        """Stage a new JWK row (no commit)."""
        db.add(jwk)

    async def delete(self, db: AsyncSession, jwk: JWK) -> None:
        """Stage a JWK deletion (no commit)."""
        await db.delete(jwk)
