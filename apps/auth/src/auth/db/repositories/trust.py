# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""TrustRepository — SQL access for Tenant trust policy rows."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth.db.models.tenant import Tenant, TenantMember, TenantTrustedSource


class TrustRepository:
    """Data access for tenant trust policy rows.

    Encapsulates every SQL query touching the ``tenants`` and
    ``tenant_trusted_sources`` tables for the trust-policy domain. Methods
    return SQLAlchemy model instances and never commit — the caller owns the
    transaction boundary.
    """

    # ------------------------------------------------------------------
    # Tenant reads (trust-scoped eager loads)
    # ------------------------------------------------------------------

    async def find_tenant_with_trusted_sources(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Tenant | None:
        """Fetch a tenant with its ``trusted_sources`` relation eager-loaded."""
        result = await db.execute(
            select(Tenant)
            .where(Tenant.id == tenant_id)
            .options(selectinload(Tenant.trusted_sources))
        )
        return result.scalar_one_or_none()

    async def find_tenant_with_trusted_sources_and_tenants(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Tenant | None:
        """Fetch a tenant with ``trusted_sources`` + ``trusted_tenant`` eager-loaded."""
        result = await db.execute(
            select(Tenant)
            .where(Tenant.id == tenant_id)
            .options(
                selectinload(Tenant.trusted_sources).selectinload(
                    TenantTrustedSource.trusted_tenant
                )
            )
        )
        return result.scalar_one_or_none()

    async def find_tenant(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Tenant | None:
        """Fetch a tenant by ID (no eager loads)."""
        result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
        return result.scalar_one_or_none()

    async def find_platform_tenant(self, db: AsyncSession) -> Tenant | None:
        """Return the platform tenant (``is_platform = True``) if any."""
        result = await db.execute(
            select(Tenant).where(Tenant.is_platform == True)  # noqa: E712
        )
        return result.scalar_one_or_none()

    async def list_available_tenants(
        self,
        db: AsyncSession,
        excluded_ids: set[uuid.UUID],
    ) -> list[Tenant]:
        """List active tenants not in ``excluded_ids``, platform first then name."""
        result = await db.execute(
            select(Tenant)
            .where(Tenant.is_active == True)  # noqa: E712
            .where(Tenant.id.notin_(excluded_ids))
            .order_by(Tenant.is_platform.desc(), Tenant.display_name)
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # TenantMember reads
    # ------------------------------------------------------------------

    async def is_member(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> bool:
        """Return True if ``user_id`` is a member of ``tenant_id``."""
        result = await db.execute(
            select(TenantMember.id)
            .where(TenantMember.user_id == user_id)
            .where(TenantMember.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none() is not None

    # ------------------------------------------------------------------
    # TenantTrustedSource reads
    # ------------------------------------------------------------------

    async def find_trusted_source(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        trusted_tenant_id: uuid.UUID,
    ) -> TenantTrustedSource | None:
        """Fetch a trusted source by (tenant_id, trusted_tenant_id)."""
        result = await db.execute(
            select(TenantTrustedSource)
            .where(TenantTrustedSource.tenant_id == tenant_id)
            .where(TenantTrustedSource.trusted_tenant_id == trusted_tenant_id)
        )
        return result.scalar_one_or_none()

    async def find_trusted_source_scoped(
        self,
        db: AsyncSession,
        source_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> TenantTrustedSource | None:
        """Fetch a trusted source by ID scoped to ``tenant_id``."""
        result = await db.execute(
            select(TenantTrustedSource)
            .where(TenantTrustedSource.id == source_id)
            .where(TenantTrustedSource.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def list_trusted_tenant_ids(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> list[uuid.UUID | None]:
        """List ``trusted_tenant_id`` values for a tenant's trusted sources."""
        result = await db.execute(
            select(TenantTrustedSource.trusted_tenant_id).where(
                TenantTrustedSource.tenant_id == tenant_id
            )
        )
        return list(result.scalars().all())

    async def platform_source_exists(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        platform_tenant_id: uuid.UUID,
    ) -> bool:
        """Return True if a trusted source from the platform tenant exists."""
        result = await db.execute(
            select(TenantTrustedSource.id)
            .where(TenantTrustedSource.tenant_id == tenant_id)
            .where(TenantTrustedSource.trusted_tenant_id == platform_tenant_id)
        )
        return result.scalar_one_or_none() is not None

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def add(self, db: AsyncSession, instance: object) -> None:
        """Stage a new row and flush so generated columns (id) are populated."""
        db.add(instance)
        await db.flush()

    async def delete(self, db: AsyncSession, instance: object) -> None:
        """Stage a row deletion and flush."""
        await db.delete(instance)
        await db.flush()
