# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""IssuerRepository — thin SQL wrapper for tenant-based issuer resolution.

The issuer service only needs to fetch an **active** tenant by ID. This
repository delegates to :class:`TenantRepository.find_active_by_id` to
avoid duplicating the ``Tenant.is_active`` predicate across modules.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from auth.db.models.tenant import Tenant
from auth.db.repositories.tenant import TenantRepository


class IssuerRepository:
    """Data access helper for issuer/tenant resolution.

    Kept deliberately tiny: it only exposes the single read needed by
    :mod:`auth.services.issuer`. All other tenant SQL lives in
    :class:`TenantRepository`.
    """

    def __init__(self, tenant_repository: TenantRepository | None = None) -> None:
        self._tenants = tenant_repository or TenantRepository()

    async def find_active_tenant(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Tenant | None:
        """Return an active :class:`Tenant` by ID, or ``None``."""
        return await self._tenants.find_active_by_id(db, tenant_id)
