# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tenant service for CRUD operations."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.models import Organization as Tenant
from knowledge.models.enums import PlanType
from knowledge.schemas.tenant import TenantCreate


class TenantService:
    """Service for managing tenants."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, data: TenantCreate) -> Tenant:
        """Create a new tenant.

        Args:
            data: Tenant creation data.

        Returns:
            The created tenant.
        """
        tenant = Tenant(
            name=data.name,
            slug=data.slug,
            plan=PlanType.FREE,
            settings={},
        )
        self.db.add(tenant)
        await self.db.flush()
        await self.db.refresh(tenant)
        return tenant

    async def get_by_id(self, tenant_id: UUID) -> Tenant | None:
        """Get a tenant by ID.

        Args:
            tenant_id: The tenant ID.

        Returns:
            The tenant or None if not found.
        """
        result = await self.db.execute(select(Tenant).where(Tenant.id == tenant_id))
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Tenant | None:
        """Get a tenant by slug.

        Args:
            slug: The tenant slug.

        Returns:
            The tenant or None if not found.
        """
        result = await self.db.execute(select(Tenant).where(Tenant.slug == slug))
        return result.scalar_one_or_none()

    async def list(self, offset: int = 0, limit: int = 100) -> list[Tenant]:
        """List all tenants.

        Args:
            offset: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of tenants.
        """
        result = await self.db.execute(
            select(Tenant).order_by(Tenant.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def update_plan(self, tenant_id: UUID, plan: PlanType) -> Tenant | None:
        """Update a tenant's plan.

        Args:
            tenant_id: The tenant ID.
            plan: The new plan.

        Returns:
            The updated tenant or None if not found.
        """
        tenant = await self.get_by_id(tenant_id)
        if not tenant:
            return None

        tenant.plan = plan
        await self.db.flush()
        await self.db.refresh(tenant)
        return tenant

    async def deactivate(self, tenant_id: UUID) -> bool:
        """Deactivate a tenant.

        Args:
            tenant_id: The tenant ID.

        Returns:
            True if deactivated, False if not found.
        """
        tenant = await self.get_by_id(tenant_id)
        if not tenant:
            return False

        tenant.is_active = False
        await self.db.flush()
        return True
