# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Admin-facing token service for listing and revoking OAuth2 tokens.

This service orchestrates admin flows around ``AccessToken`` and
``RefreshToken`` rows that do not belong to :class:`TokenService` (which
focuses on the OAuth2 runtime lifecycle). SQL access is delegated to
:class:`TokenRepository`; this service owns no transaction boundaries and
leaves commit decisions to its callers.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from auth.db.models.oauth2 import AccessToken, RefreshToken
from auth.db.repositories.token import TokenRepository


class TokenAdminService:
    """Admin flows for inspecting and revoking OAuth2 tokens."""

    def __init__(self, repository: TokenRepository | None = None) -> None:
        self._repo = repository or TokenRepository()

    # ------------------------------------------------------------------
    # Access tokens — reads
    # ------------------------------------------------------------------

    async def get_access_token_for_client(
        self,
        db: AsyncSession,
        token_id: uuid.UUID,
        client_id: uuid.UUID,
    ) -> AccessToken | None:
        """Fetch an access token by ``(id, client_id)`` pair."""
        return await self._repo.find_access_token_by_id_for_client(db, token_id, client_id)

    async def list_access_tokens_for_client(
        self,
        db: AsyncSession,
        client_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 10,
    ) -> list[AccessToken]:
        """List paginated access tokens for a client (most-recent first)."""
        return await self._repo.list_access_tokens_for_client(
            db, client_id, page=page, page_size=page_size
        )

    async def count_access_tokens_for_client(
        self,
        db: AsyncSession,
        client_id: uuid.UUID,
    ) -> int:
        """Count all access tokens for a client."""
        return await self._repo.count_access_tokens_for_client(db, client_id)

    async def count_active_access_tokens_for_client(
        self,
        db: AsyncSession,
        client_id: uuid.UUID,
        *,
        now: datetime,
    ) -> int:
        """Count non-revoked, non-expired access tokens for a client."""
        return await self._repo.count_active_access_tokens_for_client(db, client_id, now=now)

    async def count_revoked_access_tokens_for_client(
        self,
        db: AsyncSession,
        client_id: uuid.UUID,
    ) -> int:
        """Count access tokens that have been revoked for a client."""
        return await self._repo.count_revoked_access_tokens_for_client(db, client_id)

    async def count_expired_access_tokens_for_client(
        self,
        db: AsyncSession,
        client_id: uuid.UUID,
        *,
        now: datetime,
    ) -> int:
        """Count access tokens that are expired and not revoked for a client."""
        return await self._repo.count_expired_access_tokens_for_client(db, client_id, now=now)

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
        """Filter access tokens for a client by status/user/scope."""
        return await self._repo.search_access_tokens_for_client(
            db,
            client_id,
            page=page,
            page_size=page_size,
            status_filter=status_filter,
            user_ids=user_ids,
            scope_filter=scope_filter,
            now=now,
        )

    async def list_distinct_scopes_for_client(
        self,
        db: AsyncSession,
        client_id: uuid.UUID,
    ) -> list[str]:
        """Return every distinct scope seen on access tokens for a client."""
        return await self._repo.list_distinct_scopes_for_client(db, client_id)

    async def list_active_access_tokens_for_client(
        self,
        db: AsyncSession,
        client_id: uuid.UUID,
        *,
        now: datetime,
    ) -> list[AccessToken]:
        """Fetch every non-revoked, non-expired access token for a client."""
        return await self._repo.list_active_access_tokens_for_client(db, client_id, now=now)

    # ------------------------------------------------------------------
    # Refresh tokens — reads
    # ------------------------------------------------------------------

    async def list_refresh_tokens_for_access_token(
        self,
        db: AsyncSession,
        access_token_id: uuid.UUID,
    ) -> list[RefreshToken]:
        """Return every refresh token bound to a specific access token."""
        return await self._repo.list_refresh_tokens_for_access_token(db, access_token_id)

    async def list_active_refresh_tokens_for_client(
        self,
        db: AsyncSession,
        client_id: uuid.UUID,
        *,
        now: datetime,
    ) -> list[RefreshToken]:
        """Fetch every non-revoked, non-expired refresh token for a client."""
        return await self._repo.list_active_refresh_tokens_for_client(db, client_id, now=now)

    # ------------------------------------------------------------------
    # User email helpers (scoped to admin token listings)
    # ------------------------------------------------------------------

    async def list_user_ids_by_email_search(
        self,
        db: AsyncSession,
        email_pattern: str,
    ) -> list[uuid.UUID]:
        """Return user IDs whose emails match ``email_pattern``."""
        return await self._repo.list_user_ids_by_email_search(db, email_pattern)


# Singleton instance
token_admin_service = TokenAdminService()
