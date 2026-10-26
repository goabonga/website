# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""OAuth2ClientRepository — SQL access for OAuth2Client and AuthorizationCode rows."""

from __future__ import annotations

import uuid
from builtins import list as BuiltinList
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.db.models.oauth2 import AuthorizationCode, OAuth2Client


class OAuth2ClientRepository:
    """Data access for OAuth2Client rows.

    Encapsulates every SQL query touching the ``oauth2_clients`` table.
    Methods return SQLAlchemy model instances and never commit — the caller
    owns the transaction boundary.
    """

    async def find_by_id(
        self,
        db: AsyncSession,
        client_uuid: uuid.UUID,
    ) -> OAuth2Client | None:
        """Fetch an OAuth2 client by its internal UUID."""
        result = await db.execute(select(OAuth2Client).where(OAuth2Client.id == client_uuid))
        return result.scalar_one_or_none()

    async def find_by_client_id(
        self,
        db: AsyncSession,
        client_id_str: str,
    ) -> OAuth2Client | None:
        """Fetch an OAuth2 client by its public ``client_id`` string."""
        result = await db.execute(
            select(OAuth2Client).where(OAuth2Client.client_id == client_id_str)
        )
        return result.scalar_one_or_none()

    async def find_by_id_or_client_id(
        self,
        db: AsyncSession,
        identifier: str,
    ) -> OAuth2Client | None:
        """Fetch a client by internal UUID or public ``client_id`` string.

        Tries to parse ``identifier`` as a UUID first and looks up by
        primary key; falls back to matching ``client_id`` when parsing
        fails. Returns ``None`` when no client matches.
        """
        try:
            client_uuid = uuid.UUID(identifier)
            result = await db.execute(select(OAuth2Client).where(OAuth2Client.id == client_uuid))
        except ValueError:
            result = await db.execute(
                select(OAuth2Client).where(OAuth2Client.client_id == identifier)
            )
        return result.scalar_one_or_none()

    async def find_scoped_to_tenant(
        self,
        db: AsyncSession,
        client_uuid: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> OAuth2Client | None:
        """Fetch a client by internal UUID scoped to ``tenant_id``."""
        result = await db.execute(
            select(OAuth2Client).where(
                OAuth2Client.id == client_uuid,
                OAuth2Client.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
        tenant_id: uuid.UUID | None = None,
        filter_no_tenant: bool = False,
        search: str | None = None,
    ) -> tuple[BuiltinList[OAuth2Client], int]:
        """List OAuth2 clients with filters and pagination.

        Returns a ``(clients, total)`` tuple ordered by ``created_at``
        descending. Filters are ANDed together.

        Args:
            db: Database session.
            page: 1-indexed page number.
            page_size: Items per page.
            tenant_id: Only return clients scoped to this tenant. Ignored
                when ``filter_no_tenant`` is True.
            filter_no_tenant: Only return clients with no ``tenant_id``
                (global clients). Overrides ``tenant_id``.
            search: Case-insensitive substring match on either the client
                display ``name`` or the public ``client_id`` string.
        """
        offset = (page - 1) * page_size

        query = select(OAuth2Client)
        count_query = select(func.count()).select_from(OAuth2Client)

        if filter_no_tenant:
            query = query.where(OAuth2Client.tenant_id.is_(None))
            count_query = count_query.where(OAuth2Client.tenant_id.is_(None))
        elif tenant_id is not None:
            query = query.where(OAuth2Client.tenant_id == tenant_id)
            count_query = count_query.where(OAuth2Client.tenant_id == tenant_id)

        if search:
            like = f"%{search}%"
            query = query.where(OAuth2Client.name.ilike(like) | OAuth2Client.client_id.ilike(like))
            count_query = count_query.where(
                OAuth2Client.name.ilike(like) | OAuth2Client.client_id.ilike(like)
            )

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(OAuth2Client.created_at.desc()).offset(offset).limit(page_size)
        result = await db.execute(query)
        clients = list(result.scalars().all())

        return clients, total

    async def list_active_cors_tuples(
        self,
        db: AsyncSession,
    ) -> BuiltinList[tuple[BuiltinList[str] | None, BuiltinList[str]]]:
        """List ``(allowed_origins, redirect_uris)`` for every active client.

        Used by :class:`OAuth2CORSMiddleware` to validate request origins
        against the registered OAuth2 clients without pulling full rows.
        """
        result = await db.execute(
            select(OAuth2Client.allowed_origins, OAuth2Client.redirect_uris).where(
                OAuth2Client.is_active.is_(True)
            )
        )
        return [(row[0], row[1]) for row in result.all()]

    async def count(
        self,
        db: AsyncSession,
        *,
        is_active: bool | None = None,
    ) -> int:
        """Count OAuth2 clients, optionally restricted by ``is_active``."""
        query = select(func.count()).select_from(OAuth2Client)
        if is_active is not None:
            query = query.where(OAuth2Client.is_active == is_active)
        result = await db.execute(query)
        return result.scalar() or 0

    async def add(self, db: AsyncSession, client: OAuth2Client) -> None:
        """Stage a new client row and flush to obtain its generated ID."""
        db.add(client)
        await db.flush()

    async def delete(self, db: AsyncSession, client: OAuth2Client) -> None:
        """Stage a client deletion (no commit)."""
        await db.delete(client)

    # ------------------------------------------------------------------
    # AuthorizationCode
    # ------------------------------------------------------------------

    async def find_valid_authorization_code(
        self,
        db: AsyncSession,
        code_hash: str,
        *,
        now: datetime | None = None,
    ) -> AuthorizationCode | None:
        """Fetch a non-expired, unused :class:`AuthorizationCode` by its hash.

        Returns ``None`` when the hash does not match, the code has already
        been consumed, or it has expired. ``now`` defaults to the current UTC
        instant and is exposed for deterministic testing.
        """
        current = now or datetime.now(UTC)
        result = await db.execute(
            select(AuthorizationCode)
            .where(AuthorizationCode.code_hash == code_hash)
            .where(AuthorizationCode.expires_at > current)
            .where(AuthorizationCode.used_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def add_authorization_code(
        self,
        db: AsyncSession,
        auth_code: AuthorizationCode,
    ) -> None:
        """Stage an authorization code row and flush to populate its ID."""
        db.add(auth_code)
        await db.flush()
