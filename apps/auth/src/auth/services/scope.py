# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Scope management service."""

from __future__ import annotations

import logging
import uuid
from builtins import list as BuiltinList

from sqlalchemy.ext.asyncio import AsyncSession

from auth.db.models.rbac import Role, Scope
from auth.db.repositories.scope import ScopeRepository

logger = logging.getLogger(__name__)


class ScopeService:
    """Service for scope management operations.

    Thin wrapper that orchestrates scope reads/writes. SQL access is
    delegated to :class:`ScopeRepository`; this service owns transaction
    boundaries (commit/refresh) so handlers stay free of ORM details.
    """

    def __init__(self, repository: ScopeRepository | None = None) -> None:
        self._repo = repository or ScopeRepository()

    # ------------------------------------------------------------------
    # Read passthroughs
    # ------------------------------------------------------------------

    async def get_by_id(
        self,
        db: AsyncSession,
        scope_id: uuid.UUID,
    ) -> Scope | None:
        """Fetch a scope by its UUID."""
        return await self._repo.find_by_id(db, scope_id)

    async def get_by_name(
        self,
        db: AsyncSession,
        name: str,
    ) -> Scope | None:
        """Fetch a scope by its unique name."""
        return await self._repo.find_by_name(db, name)

    async def name_exists(
        self,
        db: AsyncSession,
        name: str,
    ) -> bool:
        """Return ``True`` when a scope with ``name`` is already registered."""
        return await self._repo.find_by_name(db, name) is not None

    async def list(
        self,
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        category: str | None = None,
        is_active: bool | None = None,
        order_by_created_desc: bool = True,
    ) -> tuple[BuiltinList[Scope], int]:
        """List scopes with filters and pagination. See ScopeRepository.list."""
        return await self._repo.list(
            db,
            page=page,
            page_size=page_size,
            search=search,
            category=category,
            is_active=is_active,
            order_by_created_desc=order_by_created_desc,
        )

    async def list_distinct_categories(self, db: AsyncSession) -> BuiltinList[str]:
        """Return every distinct ``category`` value present in ``scopes``."""
        return await self._repo.list_distinct_categories(db)

    async def list_active_ordered_by_resource_action(
        self,
        db: AsyncSession,
    ) -> BuiltinList[Scope]:
        """Return every active scope ordered by ``(resource, action)``."""
        return await self._repo.list_active_ordered_by_resource_action(db)

    async def list_active(
        self,
        db: AsyncSession,
        *,
        names: BuiltinList[str] | set[str] | None = None,
    ) -> BuiltinList[Scope]:
        """List active scopes ordered by ``(category, name)``.

        When ``names`` is provided, restricts the result to scopes whose
        ``name`` is in the given set.
        """
        return await self._repo.list_active(db, names=names)

    async def count_roles_for_scope(
        self,
        db: AsyncSession,
        scope_id: uuid.UUID,
    ) -> int:
        """Return the number of roles currently using ``scope_id``."""
        return await self._repo.count_roles_for_scope(db, scope_id)

    async def list_roles_for_scope(
        self,
        db: AsyncSession,
        scope_id: uuid.UUID,
    ) -> BuiltinList[Role]:
        """List every :class:`Role` referencing ``scope_id`` ordered by name."""
        return await self._repo.list_roles_for_scope(db, scope_id)

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    async def stage(self, db: AsyncSession, scope: Scope) -> None:
        """Stage a new scope row (no commit)."""
        await self._repo.add(db, scope)

    async def delete(self, db: AsyncSession, scope: Scope) -> None:
        """Stage a scope deletion (no commit)."""
        await self._repo.delete(db, scope)


scope_service = ScopeService()
