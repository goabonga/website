# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""BootstrapRepository — SQL access used to bootstrap the platform tenant."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from auth.db.models.oauth2 import OAuth2Client
from auth.db.models.tenant import (
    Tenant,
    TenantBranding,
    TenantCustomRole,
    TenantMember,
    TenantTrustedSource,
)
from auth.db.models.user import User


class BootstrapRepository:
    """Reads, and idempotent fix-ups, for ``auth bootstrap``.

    Methods never commit: the caller owns the transaction boundary, which lets a dry run roll
    everything back.
    """

    async def find_platform_tenant(self, db: AsyncSession) -> Tenant | None:
        """The tenant flagged ``is_platform``, if any."""
        result = await db.execute(select(Tenant).where(Tenant.is_platform.is_(True)).limit(1))
        return result.scalar_one_or_none()

    async def find_tenant_by_slug(self, db: AsyncSession, slug: str) -> Tenant | None:
        """The tenant with this slug, if any."""
        result = await db.execute(select(Tenant).where(Tenant.slug == slug))
        return result.scalar_one_or_none()

    async def find_branding(self, db: AsyncSession, tenant_id: uuid.UUID) -> TenantBranding | None:
        """The branding row of a tenant, if any."""
        result = await db.execute(
            select(TenantBranding).where(TenantBranding.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def find_role(
        self, db: AsyncSession, tenant_id: uuid.UUID, name: str
    ) -> TenantCustomRole | None:
        """A role of a tenant, by name."""
        result = await db.execute(
            select(TenantCustomRole).where(
                TenantCustomRole.tenant_id == tenant_id, TenantCustomRole.name == name
            )
        )
        return result.scalar_one_or_none()

    async def find_client(self, db: AsyncSession, client_id: str) -> OAuth2Client | None:
        """The OAuth2 client with this public ``client_id``, if any."""
        result = await db.execute(select(OAuth2Client).where(OAuth2Client.client_id == client_id))
        return result.scalar_one_or_none()

    async def add(self, db: AsyncSession, instance: object) -> None:
        """Stage a row and flush so that its identifier is known."""
        db.add(instance)
        await db.flush()

    async def register_orphan_users(self, db: AsyncSession, tenant_id: uuid.UUID) -> int:
        """Register on ``tenant_id`` the users that have no registration tenant; returns how many."""
        result = await db.execute(
            update(User)
            .where(User.registration_tenant_id.is_(None))
            .values(registration_tenant_id=tenant_id)
        )
        return result.rowcount or 0

    async def trust_platform_in_open_sources(self, db: AsyncSession, tenant_id: uuid.UUID) -> int:
        """Point the trusted sources without a trusted tenant at ``tenant_id``; returns how many.

        A tenant that already trusts ``tenant_id`` keeps its row as it is (the pair is unique).
        """
        other = aliased(TenantTrustedSource)
        result = await db.execute(
            update(TenantTrustedSource)
            .where(
                TenantTrustedSource.trusted_tenant_id.is_(None),
                ~exists().where(
                    other.tenant_id == TenantTrustedSource.tenant_id,
                    other.trusted_tenant_id == tenant_id,
                ),
            )
            .values(trusted_tenant_id=tenant_id)
        )
        return result.rowcount or 0

    async def add_missing_members(
        self, db: AsyncSession, tenant_id: uuid.UUID, role_id: uuid.UUID
    ) -> int:
        """Make members, with ``role_id``, of the users registered on the tenant; returns how many."""
        member = aliased(TenantMember)
        result = await db.execute(
            select(User.id).where(
                User.registration_tenant_id == tenant_id,
                ~exists().where(member.tenant_id == tenant_id, member.user_id == User.id),
            )
        )
        user_ids = list(result.scalars().all())
        now = datetime.now(UTC)
        for user_id in user_ids:
            db.add(
                TenantMember(tenant_id=tenant_id, user_id=user_id, role_id=role_id, joined_at=now)
            )
        if user_ids:
            await db.flush()
        return len(user_ids)
