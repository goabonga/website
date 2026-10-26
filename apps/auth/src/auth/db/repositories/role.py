# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""RoleRepository — SQL access for Role, RoleScope and UserRole rows."""

from __future__ import annotations

import uuid
from builtins import list as BuiltinList

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth.db.models.rbac import Role, RoleScope, Scope, UserRole
from auth.db.models.user import User, UserEmail


class RoleRepository:
    """Data access for Role, RoleScope and UserRole rows.

    Encapsulates every SQL query touching the ``roles``, ``role_scopes`` and
    ``user_roles`` tables. Methods return SQLAlchemy model instances and
    never commit — the caller owns the transaction boundary.
    """

    # ------------------------------------------------------------------
    # Role reads
    # ------------------------------------------------------------------

    async def find_by_id(
        self,
        db: AsyncSession,
        role_id: uuid.UUID,
        *,
        load_scopes: bool = False,
    ) -> Role | None:
        """Fetch a role by ID.

        When ``load_scopes`` is True, ``role_scopes`` and their associated
        ``scope`` relation are eager-loaded.
        """
        query = select(Role).where(Role.id == role_id)
        if load_scopes:
            query = query.options(selectinload(Role.role_scopes).selectinload(RoleScope.scope))
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def find_by_name(
        self,
        db: AsyncSession,
        name: str,
        *,
        case_insensitive: bool = False,
    ) -> Role | None:
        """Fetch a role by name.

        When ``case_insensitive`` is True, the comparison is made via
        ``lower(name)``.
        """
        if case_insensitive:
            query = select(Role).where(func.lower(Role.name) == name.lower())
        else:
            query = select(Role).where(Role.name == name)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def list(
        self,
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        is_system: bool | None = None,
        load_scopes: bool = True,
        order_by_system_first: bool = False,
    ) -> tuple[BuiltinList[Role], int]:
        """List roles with filters and pagination.

        Returns a ``(roles, total)`` tuple. Roles are eager-loaded with
        ``role_scopes`` and their ``scope`` by default. Filters are ANDed.

        Args:
            db: Database session.
            page: 1-indexed page number.
            page_size: Items per page.
            search: Case-insensitive substring match on ``Role.name``.
            is_system: Filter on ``Role.is_system``.
            load_scopes: Eager-load role_scopes + scope when True.
            order_by_system_first: When True, order system roles first then by
                name. Otherwise order by ``created_at`` descending.
        """
        offset = (page - 1) * page_size

        query = select(Role)
        count_query = select(func.count()).select_from(Role)

        if is_system is not None:
            query = query.where(Role.is_system.is_(is_system))
            count_query = count_query.where(Role.is_system.is_(is_system))

        if search:
            query = query.where(Role.name.ilike(f"%{search}%"))
            count_query = count_query.where(Role.name.ilike(f"%{search}%"))

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        if load_scopes:
            query = query.options(selectinload(Role.role_scopes).selectinload(RoleScope.scope))

        if order_by_system_first:
            query = query.order_by(Role.is_system.desc(), Role.name)
        else:
            query = query.order_by(Role.created_at.desc())

        query = query.offset(offset).limit(page_size)
        result = await db.execute(query)
        roles = list(result.scalars().all())

        return roles, total

    async def count_users_for_role(
        self,
        db: AsyncSession,
        role_id: uuid.UUID,
    ) -> int:
        """Return the number of users currently assigned to ``role_id``."""
        result = await db.execute(
            select(func.count()).select_from(UserRole).where(UserRole.role_id == role_id)
        )
        return result.scalar() or 0

    async def count(
        self,
        db: AsyncSession,
        *,
        is_system: bool | None = None,
    ) -> int:
        """Count roles, optionally restricted by ``is_system``."""
        query = select(func.count()).select_from(Role)
        if is_system is not None:
            query = query.where(Role.is_system.is_(is_system))
        result = await db.execute(query)
        return result.scalar() or 0

    async def list_user_roles_with_scopes(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> BuiltinList[Role]:
        """List all roles assigned to ``user_id`` with ``role_scopes.scope`` eager-loaded."""
        result = await db.execute(
            select(Role)
            .join(UserRole, UserRole.role_id == Role.id)
            .options(selectinload(Role.role_scopes).selectinload(RoleScope.scope))
            .where(UserRole.user_id == user_id)
        )
        return list(result.scalars().all())

    async def list_user_role_assignments_with_scopes(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> BuiltinList[UserRole]:
        """List ``UserRole`` assignments for ``user_id`` with role + scopes loaded.

        Unlike :meth:`list_user_roles_with_scopes`, this returns the
        ``UserRole`` association rows so callers can filter on
        ``UserRole.is_expired`` before using the related ``Role``.
        """
        result = await db.execute(
            select(UserRole)
            .where(UserRole.user_id == user_id)
            .options(
                selectinload(UserRole.role)
                .selectinload(Role.role_scopes)
                .selectinload(RoleScope.scope)
            )
        )
        return list(result.scalars().all())

    async def list_users_for_role(
        self,
        db: AsyncSession,
        role_id: uuid.UUID,
    ) -> BuiltinList[tuple[UserRole, User, UserEmail | None]]:
        """List ``(user_role, user, primary_email)`` tuples for a role."""
        result = await db.execute(
            select(UserRole, User, UserEmail)
            .join(User, UserRole.user_id == User.id)
            .outerjoin(
                UserEmail,
                (UserEmail.user_id == User.id) & (UserEmail.is_primary.is_(True)),
            )
            .where(UserRole.role_id == role_id)
            .order_by(UserRole.created_at.desc())
        )
        return [(ur, u, e) for ur, u, e in result.all()]

    # ------------------------------------------------------------------
    # RoleScope / UserRole reads
    # ------------------------------------------------------------------

    async def find_role_scope(
        self,
        db: AsyncSession,
        role_id: uuid.UUID,
        scope_id: uuid.UUID,
    ) -> RoleScope | None:
        """Fetch a ``RoleScope`` association by ``(role_id, scope_id)``."""
        result = await db.execute(
            select(RoleScope)
            .where(RoleScope.role_id == role_id)
            .where(RoleScope.scope_id == scope_id)
        )
        return result.scalar_one_or_none()

    async def find_user_role(
        self,
        db: AsyncSession,
        role_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> UserRole | None:
        """Fetch a ``UserRole`` association by ``(role_id, user_id)``."""
        result = await db.execute(
            select(UserRole).where(UserRole.role_id == role_id).where(UserRole.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_user_roles_for_user(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> BuiltinList[Role]:
        """List all roles assigned to ``user_id``."""
        result = await db.execute(
            select(Role)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Scope reads (kept here until a dedicated ScopeRepository lands)
    # ------------------------------------------------------------------

    async def find_scope_by_id(
        self,
        db: AsyncSession,
        scope_id: uuid.UUID,
    ) -> Scope | None:
        """Fetch a :class:`Scope` by ID."""
        result = await db.execute(select(Scope).where(Scope.id == scope_id))
        return result.scalar_one_or_none()

    async def find_scope_by_name(
        self,
        db: AsyncSession,
        name: str,
    ) -> Scope | None:
        """Fetch a :class:`Scope` by unique name."""
        result = await db.execute(select(Scope).where(Scope.name == name))
        return result.scalar_one_or_none()

    async def find_scopes_by_names(
        self,
        db: AsyncSession,
        names: BuiltinList[str],
    ) -> dict[str, Scope]:
        """Return a ``{name: Scope}`` map for each existing name in ``names``.

        Missing names are simply absent from the returned dict; callers
        should detect and report them.
        """
        if not names:
            return {}
        result = await db.execute(select(Scope).where(Scope.name.in_(names)))
        return {s.name: s for s in result.scalars().all()}

    async def list_active_scopes(self, db: AsyncSession) -> BuiltinList[Scope]:
        """List all active :class:`Scope` rows ordered by category/name."""
        result = await db.execute(
            select(Scope).where(Scope.is_active.is_(True)).order_by(Scope.category, Scope.name)
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Writes (staging only — caller commits)
    # ------------------------------------------------------------------

    async def add(
        self,
        db: AsyncSession,
        instance: Role | RoleScope | UserRole,
    ) -> None:
        """Stage a Role / RoleScope / UserRole row and flush to obtain its ID."""
        db.add(instance)
        await db.flush()

    async def delete(
        self,
        db: AsyncSession,
        instance: Role | RoleScope | UserRole,
    ) -> None:
        """Stage a Role / RoleScope / UserRole deletion (no commit)."""
        await db.delete(instance)
