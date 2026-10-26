# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Pairwise subject identifier service."""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from auth.db.models.oauth2 import OAuth2Client
from auth.db.models.pairwise import PairwiseSubject
from auth.db.repositories.pairwise import PairwiseSubjectRepository

logger = logging.getLogger(__name__)


class PairwiseSubjectService:
    """Service for managing pairwise subject identifiers.

    Provides per-tenant opaque ``sub`` values so that each OAuth2 client
    (scoped to a tenant) sees a different subject identifier for the same
    user.  Global clients (``tenant_id IS NULL``) fall back to the platform
    tenant.

    SQL access is delegated to :class:`PairwiseSubjectRepository`; this
    service orchestrates the INSERT-then-SELECT flow, platform-tenant
    resolution, and client-tenant fallback logic.
    """

    _platform_tenant_id: uuid.UUID | None = None

    def __init__(self, repository: PairwiseSubjectRepository | None = None) -> None:
        self._repo = repository or PairwiseSubjectRepository()

    async def get_or_create_sub(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> str:
        """Get or create a pairwise sub for a (user, tenant) pair.

        Uses PostgreSQL ``INSERT ... ON CONFLICT DO NOTHING`` followed by a
        ``SELECT`` to safely handle concurrent requests for the same pair.

        Args:
            db: Database session.
            user_id: The user's real ID.
            tenant_id: The tenant ID to scope the sub to.

        Returns:
            The pairwise sub_value as a string.
        """
        new_sub = uuid.uuid4()
        await self._repo.add(db, user_id, tenant_id, new_sub)

        # Always SELECT to get the definitive row (ours or the winner's)
        sub_value = await self._repo.find_by_user_and_tenant(db, user_id, tenant_id)
        if sub_value is None:
            raise RuntimeError("Pairwise subject not found after insert")
        return str(sub_value)

    async def get_sub_for_client(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        client: OAuth2Client,
    ) -> str:
        """Resolve the pairwise sub for a user given an OAuth2 client.

        If the client has a ``tenant_id``, use it directly.  Otherwise fall
        back to the platform tenant (``is_platform=True``).

        Args:
            db: Database session.
            user_id: The user's real ID.
            client: The OAuth2 client requesting the token.

        Returns:
            The pairwise sub_value as a string.
        """
        if client.tenant_id is not None:
            tenant_id = client.tenant_id
        else:
            tenant_id = await self._get_platform_tenant_id(db)

        return await self.get_or_create_sub(db, user_id, tenant_id)

    async def resolve_user_id(
        self,
        db: AsyncSession,
        sub_value: str,
        tenant_id: uuid.UUID,
    ) -> uuid.UUID | None:
        """Resolve a pairwise sub back to the real user_id for a tenant.

        Args:
            db: Database session.
            sub_value: The pairwise sub string.
            tenant_id: The tenant context.

        Returns:
            The real user_id, or ``None`` if the sub is unknown.
        """
        try:
            sub_uuid = uuid.UUID(sub_value)
        except ValueError:
            return None

        return await self._repo.find_by_sub(db, sub_uuid, tenant_id)

    async def resolve_user_id_for_client(
        self,
        db: AsyncSession,
        sub_value: str,
        client: OAuth2Client,
    ) -> uuid.UUID | None:
        """Resolve a pairwise sub using the client's tenant context.

        Args:
            db: Database session.
            sub_value: The pairwise sub string.
            client: The OAuth2 client.

        Returns:
            The real user_id, or ``None`` if the sub is unknown.
        """
        if client.tenant_id is not None:
            tenant_id = client.tenant_id
        else:
            tenant_id = await self._get_platform_tenant_id(db)

        return await self.resolve_user_id(db, sub_value, tenant_id)

    async def get_all_subs_for_user(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> list[PairwiseSubject]:
        """Get all pairwise subs for a user (admin use).

        Args:
            db: Database session.
            user_id: The user's real ID.

        Returns:
            List of PairwiseSubject records.
        """
        return await self._repo.list_for_user(db, user_id)

    async def delete_subs_for_tenant(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> int:
        """Delete all pairwise subs for a tenant.

        Args:
            db: Database session.
            tenant_id: The tenant whose subs to delete.

        Returns:
            The number of deleted rows.
        """
        return await self._repo.delete_for_tenant(db, tenant_id)

    async def _get_platform_tenant_id(self, db: AsyncSession) -> uuid.UUID:
        """Get the platform tenant ID (where ``is_platform=True``).

        The result is cached as a class attribute after the first query.

        Args:
            db: Database session.

        Returns:
            The platform tenant's UUID.

        Raises:
            RuntimeError: If no platform tenant exists.
        """
        if PairwiseSubjectService._platform_tenant_id is not None:
            return PairwiseSubjectService._platform_tenant_id

        tenant_id = await self._repo.find_platform_tenant_id(db)

        if tenant_id is None:
            raise RuntimeError("No platform tenant found (is_platform=True)")

        PairwiseSubjectService._platform_tenant_id = tenant_id
        return tenant_id
