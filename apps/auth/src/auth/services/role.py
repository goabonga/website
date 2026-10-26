# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Global RBAC role management service."""

from __future__ import annotations

import logging
import uuid
from builtins import list as BuiltinList
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from auth.db.models.rbac import DEFAULT_ROLES, Role, RoleScope, Scope, UserRole
from auth.db.models.user import User, UserEmail
from auth.db.repositories.role import RoleRepository

logger = logging.getLogger(__name__)


class RoleService:
    """Service for global RBAC role management.

    Orchestrates role-related business flows (create, update, delete,
    assign). SQL access for ``Role``, ``RoleScope`` and ``UserRole`` is
    delegated to :class:`RoleRepository`. Queries on :class:`Scope` are
    kept here temporarily until a dedicated ``ScopeRepository`` lands in a
    parallel refactor; this service owns transaction boundaries.

    This service is distinct from :mod:`auth.services.tenant_role`, which
    handles per-tenant custom roles (``TenantCustomRole``).
    """

    def __init__(self, repository: RoleRepository | None = None) -> None:
        self._repo = repository or RoleRepository()

    # ------------------------------------------------------------------
    # Role reads
    # ------------------------------------------------------------------

    async def get_by_id(
        self,
        db: AsyncSession,
        role_id: uuid.UUID,
        *,
        load_scopes: bool = False,
    ) -> Role | None:
        """Get role by ID, optionally with scopes eager-loaded."""
        return await self._repo.find_by_id(db, role_id, load_scopes=load_scopes)

    async def get_by_name(
        self,
        db: AsyncSession,
        name: str,
        *,
        case_insensitive: bool = False,
    ) -> Role | None:
        """Get role by name."""
        return await self._repo.find_by_name(db, name, case_insensitive=case_insensitive)

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
        """List roles with filters and pagination. See RoleRepository.list."""
        return await self._repo.list(
            db,
            page=page,
            page_size=page_size,
            search=search,
            is_system=is_system,
            load_scopes=load_scopes,
            order_by_system_first=order_by_system_first,
        )

    async def count_users_for_role(
        self,
        db: AsyncSession,
        role_id: uuid.UUID,
    ) -> int:
        """Count the users currently assigned to ``role_id``."""
        return await self._repo.count_users_for_role(db, role_id)

    async def count(
        self,
        db: AsyncSession,
        *,
        is_system: bool | None = None,
    ) -> int:
        """Count roles, optionally restricted by ``is_system``."""
        return await self._repo.count(db, is_system=is_system)

    async def list_user_roles_with_scopes(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> BuiltinList[Role]:
        """List all roles for ``user_id`` with ``role_scopes.scope`` eager-loaded."""
        return await self._repo.list_user_roles_with_scopes(db, user_id)

    async def list_users_for_role(
        self,
        db: AsyncSession,
        role_id: uuid.UUID,
    ) -> BuiltinList[tuple[UserRole, User, UserEmail | None]]:
        """List ``(user_role, user, primary_email)`` tuples for ``role_id``."""
        return await self._repo.list_users_for_role(db, role_id)

    # ------------------------------------------------------------------
    # RoleScope / UserRole reads
    # ------------------------------------------------------------------

    async def get_role_scope(
        self,
        db: AsyncSession,
        role_id: uuid.UUID,
        scope_id: uuid.UUID,
    ) -> RoleScope | None:
        """Fetch an existing ``(role_id, scope_id)`` association if any."""
        return await self._repo.find_role_scope(db, role_id, scope_id)

    async def get_user_role(
        self,
        db: AsyncSession,
        role_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> UserRole | None:
        """Fetch an existing ``(role_id, user_id)`` association if any."""
        return await self._repo.find_user_role(db, role_id, user_id)

    async def list_roles_for_user(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> BuiltinList[Role]:
        """Return all roles assigned to ``user_id``."""
        return await self._repo.list_user_roles_for_user(db, user_id)

    # ------------------------------------------------------------------
    # Scope helpers (temporary — ScopeService lands in parallel refactor)
    # ------------------------------------------------------------------

    async def _get_scope_by_id(
        self,
        db: AsyncSession,
        scope_id: uuid.UUID,
    ) -> Scope | None:
        """Lookup a :class:`Scope` by ID.

        TODO: delegate to ``ScopeService`` once the scopes refactor lands.
        """
        return await self._repo.find_scope_by_id(db, scope_id)

    async def _get_scope_by_name(
        self,
        db: AsyncSession,
        name: str,
    ) -> Scope | None:
        """Lookup a :class:`Scope` by name.

        TODO: delegate to ``ScopeService`` once the scopes refactor lands.
        """
        return await self._repo.find_scope_by_name(db, name)

    async def _get_scopes_by_names(
        self,
        db: AsyncSession,
        names: BuiltinList[str],
    ) -> dict[str, Scope]:
        """Return a ``{scope_name: Scope}`` map for each existing name.

        TODO: delegate to ``ScopeService`` once the scopes refactor lands.
        """
        return await self._repo.find_scopes_by_names(db, names)

    async def _list_active_scopes(self, db: AsyncSession) -> BuiltinList[Scope]:
        """List all active :class:`Scope` rows ordered by category/name.

        TODO: delegate to ``ScopeService`` once the scopes refactor lands.
        """
        return await self._repo.list_active_scopes(db)

    async def list_active_scopes(self, db: AsyncSession) -> BuiltinList[Scope]:
        """Public proxy over :meth:`_list_active_scopes`."""
        return await self._list_active_scopes(db)

    # ------------------------------------------------------------------
    # Write primitives (staging only — caller commits)
    # ------------------------------------------------------------------

    async def add_role(self, db: AsyncSession, role: Role) -> Role:
        """Stage a pre-built :class:`Role` row and flush to obtain its ID.

        Exposed so routes can build the row themselves without touching
        ``db.add`` directly. The caller owns the transaction boundary.
        """
        await self._repo.add(db, role)
        return role

    async def add_role_scope(self, db: AsyncSession, role_scope: RoleScope) -> RoleScope:
        """Stage a pre-built :class:`RoleScope` row (caller owns the commit)."""
        await self._repo.add(db, role_scope)
        return role_scope

    # ------------------------------------------------------------------
    # Business flows — roles
    # ------------------------------------------------------------------

    async def create_role(
        self,
        db: AsyncSession,
        *,
        name: str,
        description: str | None,
        scope_ids: BuiltinList[uuid.UUID] | None = None,
    ) -> Role:
        """Create a custom (non-system) role with optional scope assignments.

        Raises:
            ValueError: If ``name`` already exists (caller renders 409) or if
                one of ``scope_ids`` cannot be resolved (caller renders 400).
        """
        existing = await self._repo.find_by_name(db, name)
        if existing is not None:
            raise ValueError(f"Role with name '{name}' already exists")

        role = Role(name=name, description=description, is_system=False)
        await self._repo.add(db, role)

        if scope_ids:
            for scope_id in scope_ids:
                scope = await self._get_scope_by_id(db, scope_id)
                if scope is None:
                    raise ValueError(f"Scope {scope_id} not found")
                await self._repo.add(db, RoleScope(role_id=role.id, scope_id=scope_id))

        await db.commit()
        return role

    async def create_role_by_scope_names(
        self,
        db: AsyncSession,
        *,
        name: str,
        description: str | None,
        scope_names: BuiltinList[str],
    ) -> Role:
        """Create a role from scope *names* (admin-HTML flow).

        Raises:
            ValueError: If ``name`` is already in use (case-insensitive) or
                if one of ``scope_names`` cannot be resolved.
        """
        existing = await self._repo.find_by_name(db, name, case_insensitive=True)
        if existing is not None:
            raise ValueError("Role name already exists")

        db_scopes = await self._get_scopes_by_names(db, scope_names)
        invalid = [s for s in scope_names if s not in db_scopes]
        if invalid:
            raise ValueError(f"Invalid scopes: {', '.join(invalid)}")

        role = Role(name=name, description=description, is_system=False)
        await self._repo.add(db, role)

        for scope_name in scope_names:
            await self._repo.add(db, RoleScope(role_id=role.id, scope_id=db_scopes[scope_name].id))

        await db.commit()
        await db.refresh(role)
        return role

    async def update_role(
        self,
        db: AsyncSession,
        role: Role,
        *,
        name: str | None = None,
        description: str | None = None,
        scope_ids: BuiltinList[uuid.UUID] | None = None,
    ) -> Role:
        """Update an existing role in place.

        When ``scope_ids`` is provided (even empty list) the full set of
        scope assignments is replaced.

        Raises:
            ValueError: If ``name`` is already taken by another role or a
                scope id cannot be resolved.
        """
        if name is not None and name != role.name:
            dup = await self._repo.find_by_name(db, name)
            if dup is not None:
                raise ValueError(f"Role with name '{name}' already exists")
            role.name = name

        if description is not None:
            role.description = description

        if scope_ids is not None:
            for rs in list(role.role_scopes):
                await self._repo.delete(db, rs)
            await db.flush()
            for scope_id in scope_ids:
                scope = await self._get_scope_by_id(db, scope_id)
                if scope is None:
                    raise ValueError(f"Scope {scope_id} not found")
                await self._repo.add(db, RoleScope(role_id=role.id, scope_id=scope_id))

        await db.commit()
        return role

    async def update_role_by_scope_names(
        self,
        db: AsyncSession,
        role: Role,
        *,
        description: str | None,
        scope_names: BuiltinList[str],
    ) -> Role:
        """Update the description and the scopes of a custom role from scope *names*.

        The scopes of the role become exactly ``scope_names`` (admin-HTML flow); the
        assignments that stay are kept, and so are those of disabled scopes (a form lists
        the active scopes only). ``role.role_scopes`` must be loaded.

        Raises:
            ValueError: If the role is a system role or if one of ``scope_names``
                cannot be resolved.
        """
        if role.is_system:
            raise ValueError("System roles cannot be modified")

        db_scopes = await self._get_scopes_by_names(db, scope_names)
        invalid = [s for s in scope_names if s not in db_scopes]
        if invalid:
            raise ValueError(f"Invalid scopes: {', '.join(invalid)}")

        role.description = description
        wanted = {db_scopes[name].id for name in scope_names}
        held = set()
        for link in list(role.role_scopes):
            if link.scope_id in wanted:
                held.add(link.scope_id)
            elif link.scope is not None and not link.scope.is_active:
                continue
            else:
                await self._repo.delete(db, link)
        for scope_id in wanted - held:
            await self._repo.add(db, RoleScope(role_id=role.id, scope_id=scope_id))

        await db.commit()
        await db.refresh(role)
        return role

    async def delete_role(self, db: AsyncSession, role: Role) -> None:
        """Delete a custom role.

        Raises:
            ValueError: If the role is marked ``is_system``.
        """
        if role.is_system:
            raise ValueError("System roles cannot be deleted")
        await self._repo.delete(db, role)
        await db.commit()

    async def seed_default_roles(self, db: AsyncSession) -> BuiltinList[str]:
        """Idempotently create the ``DEFAULT_ROLES`` and return the names added."""
        created: BuiltinList[str] = []
        for name, config in DEFAULT_ROLES.items():
            existing = await self._repo.find_by_name(db, name)
            if existing is not None:
                continue

            role = Role(
                name=name,
                description=config["description"],
                is_system=config["is_system"],
            )
            await self._repo.add(db, role)

            scope_names = cast(BuiltinList[str], config["scopes"])
            for scope_name in scope_names:
                scope = await self._get_scope_by_name(db, scope_name)
                if scope is not None:
                    await self._repo.add(db, RoleScope(role_id=role.id, scope_id=scope.id))

            created.append(name)

        await db.commit()
        return created

    # ------------------------------------------------------------------
    # Business flows — assignments
    # ------------------------------------------------------------------

    async def assign_role_to_user(
        self,
        db: AsyncSession,
        *,
        role_id: uuid.UUID,
        user_id: uuid.UUID,
        expires_at=None,
    ) -> UserRole:
        """Assign a role to a user.

        Raises:
            ValueError: If the assignment already exists. Caller enforces the
                existence of the role/user independently.
        """
        existing = await self._repo.find_user_role(db, role_id, user_id)
        if existing is not None:
            raise ValueError("User already has this role")

        user_role = UserRole(role_id=role_id, user_id=user_id, expires_at=expires_at)
        await self._repo.add(db, user_role)
        await db.commit()
        return user_role

    async def remove_role_from_user(
        self,
        db: AsyncSession,
        user_role: UserRole,
    ) -> None:
        """Delete a ``UserRole`` association and commit."""
        await self._repo.delete(db, user_role)
        await db.commit()

    async def assign_scope_to_role(
        self,
        db: AsyncSession,
        *,
        role_id: uuid.UUID,
        scope_id: uuid.UUID,
    ) -> RoleScope:
        """Attach a scope to a role.

        Raises:
            ValueError: If the association already exists.
        """
        existing = await self._repo.find_role_scope(db, role_id, scope_id)
        if existing is not None:
            raise ValueError("Role already has this scope")

        rs = RoleScope(role_id=role_id, scope_id=scope_id)
        await self._repo.add(db, rs)
        await db.commit()
        return rs

    async def remove_scope_from_role(
        self,
        db: AsyncSession,
        role_scope: RoleScope,
    ) -> None:
        """Delete a ``RoleScope`` association and commit."""
        await self._repo.delete(db, role_scope)
        await db.commit()


role_service = RoleService()
