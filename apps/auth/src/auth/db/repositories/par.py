# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""PARRepository — SQL access for Pushed Authorization Requests (RFC 9126)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.db.models.oauth2 import OAuth2Client, PARRequest


class PARRepository:
    """Data access for :class:`PARRequest` rows.

    Encapsulates every SQL query touching the ``par_requests`` table.
    Methods return SQLAlchemy model instances and never commit — the
    caller owns the transaction boundary.
    """

    async def find_by_uri(
        self,
        db: AsyncSession,
        request_uri: str,
    ) -> PARRequest | None:
        """Fetch a PAR request by its ``request_uri``."""
        result = await db.execute(select(PARRequest).where(PARRequest.request_uri == request_uri))
        return result.scalar_one_or_none()

    async def find_by_uri_and_client(
        self,
        db: AsyncSession,
        request_uri: str,
        client_id: str,
    ) -> PARRequest | None:
        """Fetch a PAR request matching both ``request_uri`` and ``client_id``."""
        result = await db.execute(
            select(PARRequest)
            .join(OAuth2Client)
            .where(
                PARRequest.request_uri == request_uri,
                OAuth2Client.client_id == client_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_expired(
        self,
        db: AsyncSession,
        now: datetime,
    ) -> Sequence[PARRequest]:
        """Return every PAR request whose ``expires_at`` is strictly before ``now``."""
        result = await db.execute(select(PARRequest).where(PARRequest.expires_at < now))
        return result.scalars().all()

    async def add(self, db: AsyncSession, par_request: PARRequest) -> None:
        """Stage a new PAR request row and flush."""
        db.add(par_request)
        await db.flush()

    async def delete(self, db: AsyncSession, par_request: PARRequest) -> None:
        """Stage a PAR request deletion (no commit)."""
        await db.delete(par_request)
