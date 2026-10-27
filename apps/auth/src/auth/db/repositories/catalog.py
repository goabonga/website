# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""CatalogRepository — SQL access used to synchronise the catalog of scopes and roles."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth.db.models.oauth2 import OAuth2Client
from auth.db.models.rbac import Role, RoleScope, Scope


class CatalogRepository:
    """Reads and stages the rows that a catalog describes.

    Methods never commit: the caller owns the transaction boundary, which lets a
    dry run roll everything back.
    """

    async def scopes_by_name(self, db: AsyncSession) -> dict[str, Scope]:
        """Every scope, keyed by name."""
        result = await db.execute(select(Scope))
        return {scope.name: scope for scope in result.scalars().all()}

    async def roles_by_name(self, db: AsyncSession) -> dict[str, Role]:
        """Every role with its scope links loaded, keyed by name."""
        result = await db.execute(
            select(Role).options(selectinload(Role.role_scopes).selectinload(RoleScope.scope))
        )
        return {role.name: role for role in result.scalars().all()}

    async def find_client(self, db: AsyncSession, client_id: str) -> OAuth2Client | None:
        """The OAuth2 client with this public ``client_id``, if any."""
        result = await db.execute(select(OAuth2Client).where(OAuth2Client.client_id == client_id))
        return result.scalar_one_or_none()

    async def add(self, db: AsyncSession, instance: Scope | Role | RoleScope) -> None:
        """Stage a row and flush so that its identifier is known."""
        db.add(instance)
        await db.flush()
