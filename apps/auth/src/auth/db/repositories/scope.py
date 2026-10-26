# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""ScopeRepository — SQL access for Scope rows."""

from __future__ import annotations

import uuid
from builtins import list as BuiltinList

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.db.models.rbac import Role, RoleScope, Scope


class ScopeRepository:
    """Data access for Scope rows.

    Encapsulates every SQL query touching the ``scopes`` table. Methods
    return SQLAlchemy model instances and never commit — the caller owns
    the transaction boundary.
    """

    async def find_by_id(
        self,
        db: AsyncSession,
        scope_id: uuid.UUID,
    ) -> Scope | None:
        """Fetch a scope by its primary key."""
        result = await db.execute(select(Scope).where(Scope.id == scope_id))
        return result.scalar_one_or_none()

    async def find_by_name(
        self,
        db: AsyncSession,
        name: str,
    ) -> Scope | None:
        """Fetch a scope by its unique ``name``."""
        result = await db.execute(select(Scope).where(Scope.name == name))
        return result.scalar_one_or_none()

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
        """List scopes with optional filters and pagination.

        Returns a ``(scopes, total)`` tuple. Filters are ANDed together.

        Args:
            db: Database session.
            page: 1-indexed page number.
            page_size: Items per page.
            search: Case-insensitive substring match on ``Scope.name``.
            category: Exact match on ``Scope.category``.
            is_active: Filter on ``Scope.is_active``.
            order_by_created_desc: When ``True`` (default) sort by
                ``created_at`` descending. When ``False`` sort by
                ``category, resource, action`` ascending (used by the
                admin HTML page).
        """
        offset = (page - 1) * page_size

        query = select(Scope)
        count_query = select(func.count()).select_from(Scope)

        if category is not None:
            query = query.where(Scope.category == category)
            count_query = count_query.where(Scope.category == category)

        if is_active is not None:
            query = query.where(Scope.is_active.is_(is_active))
            count_query = count_query.where(Scope.is_active.is_(is_active))

        if search:
            query = query.where(Scope.name.ilike(f"%{search}%"))
            count_query = count_query.where(Scope.name.ilike(f"%{search}%"))

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        if order_by_created_desc:
            query = query.order_by(Scope.created_at.desc())
        else:
            query = query.order_by(Scope.category, Scope.resource, Scope.action)

        query = query.offset(offset).limit(page_size)
        result = await db.execute(query)
        scopes = list(result.scalars().all())

        return scopes, total

    async def list_distinct_categories(self, db: AsyncSession) -> BuiltinList[str]:
        """Return every distinct ``category`` value present in ``scopes``."""
        result = await db.execute(select(Scope.category).distinct().order_by(Scope.category))
        return [row[0] for row in result.all()]

    async def list_active_ordered_by_resource_action(
        self,
        db: AsyncSession,
    ) -> BuiltinList[Scope]:
        """Return every active scope ordered by ``(resource, action)``."""
        result = await db.execute(
            select(Scope).where(Scope.is_active.is_(True)).order_by(Scope.resource, Scope.action)
        )
        return list(result.scalars().all())

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
        query = select(Scope).where(Scope.is_active.is_(True))
        if names is not None:
            query = query.where(Scope.name.in_(list(names)))
        query = query.order_by(Scope.category, Scope.name)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def count_roles_for_scope(
        self,
        db: AsyncSession,
        scope_id: uuid.UUID,
    ) -> int:
        """Return the number of roles currently using ``scope_id``."""
        result = await db.execute(
            select(func.count()).select_from(RoleScope).where(RoleScope.scope_id == scope_id)
        )
        return result.scalar() or 0

    async def list_roles_for_scope(
        self,
        db: AsyncSession,
        scope_id: uuid.UUID,
    ) -> BuiltinList[Role]:
        """List every :class:`Role` referencing ``scope_id`` ordered by name."""
        result = await db.execute(
            select(Role)
            .join(RoleScope, RoleScope.role_id == Role.id)
            .where(RoleScope.scope_id == scope_id)
            .order_by(Role.name)
        )
        return list(result.scalars().all())

    async def add(self, db: AsyncSession, scope: Scope) -> None:
        """Stage a new scope row (no commit)."""
        db.add(scope)

    async def delete(self, db: AsyncSession, scope: Scope) -> None:
        """Stage a scope deletion (no commit)."""
        await db.delete(scope)
