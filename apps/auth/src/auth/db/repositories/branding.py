# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""BrandingRepository — SQL access for tenant branding and per-tenant templates."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth.db.models.tenant import Tenant, TenantBranding, TenantTemplate


class BrandingRepository:
    """Data access for tenant branding and tenant template overrides.

    Encapsulates every SQL query touching ``tenant_branding`` and
    ``tenant_templates`` rows consumed by :class:`BrandingService`. Returns
    SQLAlchemy model instances and never commits — the caller owns the
    transaction boundary.
    """

    # ------------------------------------------------------------------
    # Tenant + branding reads
    # ------------------------------------------------------------------

    async def find_tenant_with_branding(
        self,
        db: AsyncSession,
        tenant_id: UUID,
    ) -> Tenant | None:
        """Fetch a tenant with its ``branding`` relation eager-loaded."""
        result = await db.execute(
            select(Tenant).options(selectinload(Tenant.branding)).where(Tenant.id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def find_branding(
        self,
        db: AsyncSession,
        tenant_id: UUID,
    ) -> TenantBranding | None:
        """Fetch the :class:`TenantBranding` row for ``tenant_id`` (or ``None``)."""
        result = await db.execute(
            select(TenantBranding).where(TenantBranding.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Template reads
    # ------------------------------------------------------------------

    async def find_active_template(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        template_name: str,
    ) -> TenantTemplate | None:
        """Fetch an *active* per-tenant template override by name.

        Used by the Jinja2 loader that prefers a DB-backed override when
        ``is_active`` is true. Inactive overrides are hidden from this query
        so the filesystem fallback wins.
        """
        result = await db.execute(
            select(TenantTemplate)
            .where(TenantTemplate.tenant_id == tenant_id)
            .where(TenantTemplate.template_name == template_name)
            .where(TenantTemplate.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    async def find_template(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        template_name: str,
    ) -> TenantTemplate | None:
        """Fetch a per-tenant template override regardless of ``is_active``."""
        result = await db.execute(
            select(TenantTemplate)
            .where(TenantTemplate.tenant_id == tenant_id)
            .where(TenantTemplate.template_name == template_name)
        )
        return result.scalar_one_or_none()

    async def list_templates(
        self,
        db: AsyncSession,
        tenant_id: UUID,
    ) -> list[TenantTemplate]:
        """List every template override for ``tenant_id`` ordered by template name."""
        result = await db.execute(
            select(TenantTemplate)
            .where(TenantTemplate.tenant_id == tenant_id)
            .order_by(TenantTemplate.template_name)
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Writes (staging only — caller commits)
    # ------------------------------------------------------------------

    async def add(
        self,
        db: AsyncSession,
        instance: TenantBranding | TenantTemplate,
    ) -> None:
        """Stage a branding/template row and flush to populate generated columns."""
        db.add(instance)
        await db.flush()

    async def delete(
        self,
        db: AsyncSession,
        instance: TenantBranding | TenantTemplate,
    ) -> None:
        """Stage a row deletion and flush so the DELETE is issued immediately."""
        await db.delete(instance)
        await db.flush()

    async def flush(self, db: AsyncSession) -> None:
        """Flush pending mutations (no commit)."""
        await db.flush()
