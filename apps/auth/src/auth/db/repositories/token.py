# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""TokenRepository — SQL access for AccessToken and RefreshToken rows."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth.db.models.oauth2 import AccessToken, OAuth2Client, RefreshToken
from auth.db.models.user import UserEmail


class TokenRepository:
    """Data access for ``access_tokens`` and ``refresh_tokens`` rows.

    Encapsulates every SQL query touching these tables. Methods return
    SQLAlchemy model instances and never commit — the caller owns the
    transaction boundary.
    """

    # ------------------------------------------------------------------
    # Access tokens — reads
    # ------------------------------------------------------------------

    async def find_access_token_by_id_for_client(
        self,
        db: AsyncSession,
        token_id: uuid.UUID,
        client_id: uuid.UUID,
    ) -> AccessToken | None:
        """Fetch an access token by ``(id, client_id)`` pair."""
        result = await db.execute(
            select(AccessToken).where(
                AccessToken.id == token_id,
                AccessToken.client_id == client_id,
            )
        )
        return result.scalar_one_or_none()

    async def find_access_token_by_jti(
        self,
        db: AsyncSession,
        jti: str,
    ) -> AccessToken | None:
        """Fetch an access token by ``jti`` (regardless of status)."""
        result = await db.execute(select(AccessToken).where(AccessToken.jti == jti))
        return result.scalar_one_or_none()

    async def find_revoked_access_token_by_jti(
        self,
        db: AsyncSession,
        jti: str,
    ) -> AccessToken | None:
        """Fetch an access token by ``jti`` only if it is revoked.

        Used by token validation to reject revoked JWTs even though the
        signature is still valid.
        """
        result = await db.execute(
            select(AccessToken)
            .where(AccessToken.jti == jti)
            .where(AccessToken.revoked_at.isnot(None))
        )
        return result.scalar_one_or_none()

    async def find_active_access_token_by_jti(
        self,
        db: AsyncSession,
        jti: str,
    ) -> AccessToken | None:
        """Fetch an access token by ``jti`` only if it is not revoked.

        Used by token exchange (RFC 8693) where only live subject tokens
        may be swapped for new tokens.
        """
        result = await db.execute(
            select(AccessToken)
            .where(AccessToken.jti == jti)
            .where(AccessToken.revoked_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def list_access_tokens_for_client(
        self,
        db: AsyncSession,
        client_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 10,
        eager_user: bool = True,
    ) -> list[AccessToken]:
        """List paginated access tokens for a client ordered by ``created_at`` desc."""
        offset = (page - 1) * page_size
        query = select(AccessToken).where(AccessToken.client_id == client_id)
        if eager_user:
            query = query.options(selectinload(AccessToken.user))
        query = query.order_by(AccessToken.created_at.desc()).offset(offset).limit(page_size)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def count_access_tokens_for_client(
        self,
        db: AsyncSession,
        client_id: uuid.UUID,
    ) -> int:
        """Count all access tokens for a client."""
        result = await db.execute(
            select(func.count()).select_from(AccessToken).where(AccessToken.client_id == client_id)
        )
        return result.scalar() or 0

    async def count_active_access_tokens_for_client(
        self,
        db: AsyncSession,
        client_id: uuid.UUID,
        *,
        now: datetime,
    ) -> int:
        """Count non-revoked, non-expired access tokens for a client at ``now``."""
        result = await db.execute(
            select(func.count())
            .select_from(AccessToken)
            .where(
                AccessToken.client_id == client_id,
                AccessToken.revoked_at.is_(None),
                AccessToken.expires_at > now,
            )
        )
        return result.scalar() or 0

    async def count_revoked_access_tokens_for_client(
        self,
        db: AsyncSession,
        client_id: uuid.UUID,
    ) -> int:
        """Count access tokens that have been revoked for a client."""
        result = await db.execute(
            select(func.count())
            .select_from(AccessToken)
            .where(
                AccessToken.client_id == client_id,
                AccessToken.revoked_at.isnot(None),
            )
        )
        return result.scalar() or 0

    async def count_expired_access_tokens_for_client(
        self,
        db: AsyncSession,
        client_id: uuid.UUID,
        *,
        now: datetime,
    ) -> int:
        """Count access tokens that are expired and not revoked for a client."""
        result = await db.execute(
            select(func.count())
            .select_from(AccessToken)
            .where(
                AccessToken.client_id == client_id,
                AccessToken.revoked_at.is_(None),
                AccessToken.expires_at <= now,
            )
        )
        return result.scalar() or 0

    async def search_access_tokens_for_client(
        self,
        db: AsyncSession,
        client_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
        status_filter: str | None = None,
        user_ids: list[uuid.UUID] | None = None,
        scope_filter: str | None = None,
        now: datetime,
    ) -> tuple[list[AccessToken], int]:
        """Filter access tokens for a client with status/user/scope filters.

        Returns ``(tokens, total)``. ``status_filter`` may be one of
        ``active`` / ``revoked`` / ``expired``; any other value is ignored.
        ``user_ids`` when empty list returns no rows. ``scope_filter`` applies
        a ``scopes @> [scope]`` contains check.
        """
        offset = (page - 1) * page_size

        query = select(AccessToken).where(AccessToken.client_id == client_id)
        count_query = (
            select(func.count()).select_from(AccessToken).where(AccessToken.client_id == client_id)
        )

        if status_filter == "active":
            query = query.where(
                AccessToken.revoked_at.is_(None),
                AccessToken.expires_at > now,
            )
            count_query = count_query.where(
                AccessToken.revoked_at.is_(None),
                AccessToken.expires_at > now,
            )
        elif status_filter == "revoked":
            query = query.where(AccessToken.revoked_at.isnot(None))
            count_query = count_query.where(AccessToken.revoked_at.isnot(None))
        elif status_filter == "expired":
            query = query.where(
                AccessToken.revoked_at.is_(None),
                AccessToken.expires_at <= now,
            )
            count_query = count_query.where(
                AccessToken.revoked_at.is_(None),
                AccessToken.expires_at <= now,
            )

        if user_ids is not None:
            if not user_ids:
                # Caller wants user filtering but no users matched -> no rows.
                query = query.where(
                    AccessToken.user_id.is_(None),
                    AccessToken.user_id.isnot(None),
                )
                count_query = count_query.where(
                    AccessToken.user_id.is_(None),
                    AccessToken.user_id.isnot(None),
                )
            else:
                query = query.where(AccessToken.user_id.in_(user_ids))
                count_query = count_query.where(AccessToken.user_id.in_(user_ids))

        if scope_filter:
            query = query.where(AccessToken.scopes.contains([scope_filter]))
            count_query = count_query.where(AccessToken.scopes.contains([scope_filter]))

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        query = (
            query.options(selectinload(AccessToken.user))
            .order_by(AccessToken.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await db.execute(query)
        tokens = list(result.scalars().all())

        return tokens, total

    async def list_distinct_scopes_for_client(
        self,
        db: AsyncSession,
        client_id: uuid.UUID,
    ) -> list[str]:
        """Return every distinct scope seen on access tokens for a client."""
        result = await db.execute(
            select(func.unnest(AccessToken.scopes).label("scope"))
            .where(AccessToken.client_id == client_id)
            .distinct()
        )
        return sorted([row[0] for row in result.all()])

    async def list_active_access_tokens_for_client(
        self,
        db: AsyncSession,
        client_id: uuid.UUID,
        *,
        now: datetime,
    ) -> list[AccessToken]:
        """Fetch every non-revoked, non-expired access token for a client."""
        result = await db.execute(
            select(AccessToken).where(
                AccessToken.client_id == client_id,
                AccessToken.revoked_at.is_(None),
                AccessToken.expires_at > now,
            )
        )
        return list(result.scalars().all())

    async def list_active_access_tokens_for_user_client(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        client_id: uuid.UUID,
    ) -> list[AccessToken]:
        """Fetch every non-revoked access token for a ``(user, client)`` pair.

        Used by "revoke application access" flows where every live access
        token for a given user/client must be revoked in one pass.
        """
        result = await db.execute(
            select(AccessToken)
            .where(AccessToken.user_id == user_id)
            .where(AccessToken.client_id == client_id)
            .where(AccessToken.revoked_at.is_(None))
        )
        return list(result.scalars().all())

    async def aggregate_authorized_clients_for_user(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        *,
        now: datetime,
    ) -> list[sa.Row]:
        """Return grouped ``(client_id, first_authorized, last_used)`` rows.

        Considers only non-revoked, non-expired access tokens owned by
        ``user_id``.
        """
        result = await db.execute(
            select(
                AccessToken.client_id,
                func.min(AccessToken.created_at).label("first_authorized"),
                func.max(AccessToken.created_at).label("last_used"),
            )
            .where(AccessToken.user_id == user_id)
            .where(AccessToken.revoked_at.is_(None))
            .where(AccessToken.expires_at > now)
            .group_by(AccessToken.client_id)
        )
        return list(result.all())

    async def find_latest_active_scopes(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        client_id: uuid.UUID,
        *,
        now: datetime,
    ) -> list[str] | None:
        """Return the scopes of the most recent non-revoked, non-expired token.

        Returns ``None`` when no active token is found.
        """
        result = await db.execute(
            select(AccessToken.scopes)
            .where(AccessToken.client_id == client_id)
            .where(AccessToken.user_id == user_id)
            .where(AccessToken.revoked_at.is_(None))
            .where(AccessToken.expires_at > now)
            .order_by(AccessToken.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Access tokens — writes
    # ------------------------------------------------------------------

    async def add_access_token(self, db: AsyncSession, token: AccessToken) -> None:
        """Stage a new access token row and flush to obtain its generated ID."""
        db.add(token)
        await db.flush()

    async def revoke_access_tokens_for_refresh_cascade(
        self,
        db: AsyncSession,
        *,
        client_id: uuid.UUID,
        user_id: uuid.UUID | None,
        now: datetime,
    ) -> None:
        """Revoke every live access token for a ``(client, user)`` pair.

        Invoked when a refresh token is revoked: any outstanding access
        token tied to the same client and user is also invalidated.
        """
        await db.execute(
            sa.update(AccessToken)
            .where(AccessToken.client_id == client_id)
            .where(AccessToken.user_id == user_id)
            .where(AccessToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    # ------------------------------------------------------------------
    # Refresh tokens — reads
    # ------------------------------------------------------------------

    async def list_refresh_tokens_for_access_token(
        self,
        db: AsyncSession,
        access_token_id: uuid.UUID,
    ) -> list[RefreshToken]:
        """Return every refresh token bound to a specific access token."""
        result = await db.execute(
            select(RefreshToken).where(RefreshToken.access_token_id == access_token_id)
        )
        return list(result.scalars().all())

    async def list_active_refresh_tokens_for_client(
        self,
        db: AsyncSession,
        client_id: uuid.UUID,
        *,
        now: datetime,
    ) -> list[RefreshToken]:
        """Fetch every non-revoked, non-expired refresh token for a client."""
        result = await db.execute(
            select(RefreshToken).where(
                RefreshToken.client_id == client_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
        )
        return list(result.scalars().all())

    async def list_active_refresh_tokens_for_user_client(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        client_id: uuid.UUID,
    ) -> list[RefreshToken]:
        """Fetch every non-revoked refresh token for a ``(user, client)`` pair."""
        result = await db.execute(
            select(RefreshToken)
            .where(RefreshToken.user_id == user_id)
            .where(RefreshToken.client_id == client_id)
            .where(RefreshToken.revoked_at.is_(None))
        )
        return list(result.scalars().all())

    async def find_refresh_token_by_hash(
        self,
        db: AsyncSession,
        token_hash: str,
    ) -> RefreshToken | None:
        """Fetch a refresh token by its hashed value (no status filter)."""
        result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        return result.scalar_one_or_none()

    async def find_valid_refresh_token_by_hash(
        self,
        db: AsyncSession,
        token_hash: str,
        *,
        now: datetime,
    ) -> RefreshToken | None:
        """Fetch a non-revoked, non-used, non-expired refresh token by hash."""
        result = await db.execute(
            select(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .where(RefreshToken.expires_at > now)
            .where(RefreshToken.revoked_at.is_(None))
            .where(RefreshToken.used_at.is_(None))
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Refresh tokens — writes
    # ------------------------------------------------------------------

    async def add_refresh_token(self, db: AsyncSession, token: RefreshToken) -> None:
        """Stage a new refresh token row and flush to obtain its generated ID."""
        db.add(token)
        await db.flush()

    # ------------------------------------------------------------------
    # OAuth2 client lookup helpers (for token flows)
    # ------------------------------------------------------------------

    async def find_client_by_string_id(
        self,
        db: AsyncSession,
        client_id: str,
    ) -> OAuth2Client | None:
        """Fetch an OAuth2 client by its public ``client_id`` string."""
        result = await db.execute(select(OAuth2Client).where(OAuth2Client.client_id == client_id))
        return result.scalar_one_or_none()

    async def find_clients_by_ids(
        self,
        db: AsyncSession,
        client_ids: list[uuid.UUID],
    ) -> list[OAuth2Client]:
        """Fetch multiple OAuth2 clients by their primary key IDs."""
        if not client_ids:
            return []
        result = await db.execute(select(OAuth2Client).where(OAuth2Client.id.in_(client_ids)))
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # User email helpers (scoped to admin token listings)
    # ------------------------------------------------------------------

    async def list_user_ids_by_email_search(
        self,
        db: AsyncSession,
        email_pattern: str,
    ) -> list[uuid.UUID]:
        """Return user IDs whose emails match ``email_pattern`` (case-insensitive)."""
        result = await db.execute(
            select(UserEmail.user_id).where(UserEmail.email.ilike(f"%{email_pattern}%"))
        )
        return [row[0] for row in result.all()]
