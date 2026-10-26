# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""TenantRoleRepository — SQL access for TenantCustomRole rows."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from auth.db.models.rbac import Scope
from auth.db.models.tenant import TenantCustomRole, TenantMember


class TenantRoleRepository:
    """Data access for :class:`TenantCustomRole` rows.

    Encapsulates every SQL query touching the ``tenant_custom_roles``
    table (and the ``tenant_members`` / ``scopes`` tables when needed to
    compute role-related counts or validate scope names). Methods return
    SQLAlchemy model instances and never commit — the caller owns the
    transaction boundary.
    """

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def find_by_id(
        self,
        db: AsyncSession,
        role_id: uuid.UUID,
    ) -> TenantCustomRole | None:
        """Fetch a tenant custom role by its ID."""
        result = await db.execute(select(TenantCustomRole).where(TenantCustomRole.id == role_id))
        return result.scalar_one_or_none()

    async def find_by_name_in_tenant(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        name: str,
    ) -> TenantCustomRole | None:
        """Fetch a tenant custom role by its ``(tenant_id, name)`` pair."""
        result = await db.execute(
            select(TenantCustomRole).where(
                TenantCustomRole.tenant_id == tenant_id,
                TenantCustomRole.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def list_roles_for_tenant(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> list[TenantCustomRole]:
        """List all roles for ``tenant_id`` ordered by ``display_order`` then name."""
        result = await db.execute(
            select(TenantCustomRole)
            .where(TenantCustomRole.tenant_id == tenant_id)
            .order_by(TenantCustomRole.display_order, TenantCustomRole.name)
        )
        return list(result.scalars().all())

    async def find_default_role(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> TenantCustomRole | None:
        """Return the role flagged as ``is_default=True`` for ``tenant_id``."""
        result = await db.execute(
            select(TenantCustomRole).where(
                TenantCustomRole.tenant_id == tenant_id,
                TenantCustomRole.is_default.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def max_display_order(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> int:
        """Return the highest ``display_order`` used in ``tenant_id`` (0 if none)."""
        result = await db.execute(
            select(func.max(TenantCustomRole.display_order)).where(
                TenantCustomRole.tenant_id == tenant_id
            )
        )
        return result.scalar() or 0

    async def count_members_for_role(
        self,
        db: AsyncSession,
        role_id: uuid.UUID,
    ) -> int:
        """Return the number of members currently assigned to ``role_id``."""
        result = await db.execute(
            select(func.count(TenantMember.id)).where(TenantMember.role_id == role_id)
        )
        return result.scalar() or 0

    async def list_active_scope_names(
        self,
        db: AsyncSession,
    ) -> set[str]:
        """Return the set of active application scope names from the DB."""
        result = await db.execute(select(Scope.name).where(Scope.is_active.is_(True)))
        return {row[0] for row in result.all()}

    # ------------------------------------------------------------------
    # Writes (staging only — caller commits)
    # ------------------------------------------------------------------

    async def add(self, db: AsyncSession, role: TenantCustomRole) -> None:
        """Stage a new tenant custom role row and flush to obtain its ID."""
        db.add(role)
        await db.flush()

    async def stage(self, db: AsyncSession, role: TenantCustomRole) -> TenantCustomRole:
        """Stage a new tenant custom role row without flushing.

        Intended for batch creation flows (e.g. seeding the default role set
        on a new tenant) that share a single flush at the end.
        """
        db.add(role)
        return role

    async def delete(self, db: AsyncSession, role: TenantCustomRole) -> None:
        """Stage a tenant custom role deletion (no commit)."""
        await db.delete(role)

    async def flush(self, db: AsyncSession) -> None:
        """Flush staged mutations (no commit)."""
        await db.flush()

    async def clear_default_flag(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        except_role_id: uuid.UUID | None = None,
    ) -> None:
        """Unset ``is_default`` on every role of ``tenant_id``.

        When ``except_role_id`` is provided, that role is left untouched so
        callers can first clear siblings and then flip the target role on.
        """
        stmt = (
            update(TenantCustomRole)
            .where(
                TenantCustomRole.tenant_id == tenant_id,
                TenantCustomRole.is_default.is_(True),
            )
            .values(is_default=False)
        )
        if except_role_id is not None:
            stmt = stmt.where(TenantCustomRole.id != except_role_id)
        await db.execute(stmt)
