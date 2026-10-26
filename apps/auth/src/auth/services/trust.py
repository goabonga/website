# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tenant trust policy service."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from auth.db.models.tenant import Tenant, TenantTrustedSource, TenantTrustMode
from auth.db.models.user import User
from auth.db.repositories.trust import TrustRepository

logger = logging.getLogger(__name__)


class TrustPolicyService:
    """Service for evaluating tenant trust policies.

    Orchestrates the tenant trust-policy business flows (mode evaluation,
    trusted-source configuration). SQL access is delegated to
    :class:`TrustRepository`; this service keeps ownership of pattern
    matching, validation, and transaction boundaries.
    """

    def __init__(self, repository: TrustRepository | None = None) -> None:
        self._repo = repository or TrustRepository()

    async def can_user_access_tenant(
        self,
        db: AsyncSession,
        user: User,
        tenant_id: UUID | str,
    ) -> tuple[bool, str | None]:
        """Check if a user can access a tenant based on trust policies.

        Args:
            db: Database session.
            user: The authenticated user.
            tenant_id: The target tenant ID.

        Returns:
            Tuple of (allowed: bool, error_message: str | None).
        """
        # Ensure tenant_id is a UUID (may be passed as string from tenant context)
        if isinstance(tenant_id, str):
            tenant_id = UUID(tenant_id)

        # Load tenant with trust configuration
        tenant = await self._repo.find_tenant_with_trusted_sources(db, tenant_id)

        if not tenant:
            logger.warning("Trust check failed: tenant not found: %s", tenant_id)
            return False, "Organization not found"

        if not tenant.is_active:
            logger.warning("Trust check failed: tenant inactive: %s", tenant.slug)
            return False, "This organization is currently inactive"

        user_registration_tenant_id = user.registration_tenant_id

        # Evaluate trust mode
        match tenant.trust_mode:
            case TenantTrustMode.NONE:
                # Users registered on this tenant can login
                if user_registration_tenant_id == tenant_id:
                    return True, None
                # Members of the tenant can always login (they were explicitly added)
                is_member = await self._repo.is_member(db, user.id, tenant_id)
                if is_member:
                    return True, None
                logger.info(
                    "Trust denied (NONE mode): user=%s registered_on=%s target=%s",
                    user.id,
                    user_registration_tenant_id,
                    tenant_id,
                )
                return False, "You must be registered on this organization to sign in"

            case TenantTrustMode.ALL:
                # Any authenticated user can login
                return True, None

            case TenantTrustMode.MEMBERS_ONLY:
                # Only members of the tenant can login
                is_member = await self._repo.is_member(db, user.id, tenant_id)
                if is_member:
                    return True, None
                logger.info(
                    "Trust denied (MEMBERS_ONLY mode): user=%s is not member of %s",
                    user.id,
                    tenant_id,
                )
                return False, "You must be a member of this organization to sign in"

            case TenantTrustMode.SPECIFIC:
                # Check trusted sources
                is_trusted = self._is_from_trusted_source(
                    user_registration_tenant_id, tenant.trusted_sources
                )
                if is_trusted:
                    return True, None

                # Also check if user is a member (members always allowed in SPECIFIC mode)
                is_member = await self._repo.is_member(db, user.id, tenant_id)
                if is_member:
                    return True, None

                logger.info(
                    "Trust denied (SPECIFIC mode): user=%s "
                    "registered_on=%s "
                    "not in trusted list for %s",
                    user.id,
                    user_registration_tenant_id,
                    tenant_id,
                )
                return False, "Your account is not authorized to sign in to this organization"

            case _:
                # Unknown trust mode, deny by default
                logger.error("Unknown trust mode: %s for tenant %s", tenant.trust_mode, tenant_id)
                return False, "Configuration error"

    def _is_from_trusted_source(
        self,
        user_registration_tenant_id: UUID | None,
        trusted_sources: list[TenantTrustedSource],
    ) -> bool:
        """Check if user's registration tenant is in the trusted sources list.

        Args:
            user_registration_tenant_id: The tenant where the user registered.
            trusted_sources: List of trusted source configurations.

        Returns:
            True if the user's origin is trusted.
        """
        if user_registration_tenant_id is None:
            return False

        for source in trusted_sources:
            if source.trusted_tenant_id == user_registration_tenant_id:
                return True
        return False

    async def get_tenant_trust_config(
        self,
        db: AsyncSession,
        tenant_id: UUID,
    ) -> dict | None:
        """Get trust configuration for a tenant.

        Args:
            db: Database session.
            tenant_id: Tenant ID.

        Returns:
            Dictionary with trust configuration or None if tenant not found.
        """
        tenant = await self._repo.find_tenant_with_trusted_sources_and_tenants(db, tenant_id)

        if not tenant:
            return None

        trusted_sources = []
        for source in tenant.trusted_sources:
            trusted_sources.append(
                {
                    "id": str(source.id),
                    "trusted_tenant_id": str(source.trusted_tenant_id)
                    if source.trusted_tenant_id
                    else None,
                    "trusted_tenant_name": source.trusted_tenant.display_name
                    if source.trusted_tenant
                    else "Unknown",
                    "trusted_tenant_slug": source.trusted_tenant.slug
                    if source.trusted_tenant
                    else None,
                    "is_platform": source.trusted_tenant.is_platform
                    if source.trusted_tenant
                    else False,
                    "description": source.description,
                }
            )

        return {
            "trust_mode": tenant.trust_mode.value,
            "trusted_sources": trusted_sources,
        }

    async def update_trust_mode(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        trust_mode: TenantTrustMode,
    ) -> bool:
        """Update the trust mode for a tenant.

        Args:
            db: Database session.
            tenant_id: Tenant ID.
            trust_mode: New trust mode.

        Returns:
            True if updated successfully.
        """
        tenant = await self._repo.find_tenant(db, tenant_id)

        if not tenant:
            return False

        tenant.trust_mode = trust_mode
        await db.flush()
        logger.info("Trust mode updated: tenant=%s mode=%s", tenant_id, trust_mode.value)
        return True

    async def add_trusted_source(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        trusted_tenant_id: UUID,
        description: str | None = None,
    ) -> TenantTrustedSource | None:
        """Add a trusted source tenant.

        Args:
            db: Database session.
            tenant_id: The tenant to configure.
            trusted_tenant_id: The trusted source tenant.
            description: Optional description.

        Returns:
            The created TenantTrustedSource or None if already exists.
        """
        existing = await self._repo.find_trusted_source(db, tenant_id, trusted_tenant_id)
        if existing:
            return None

        source = TenantTrustedSource(
            tenant_id=tenant_id,
            trusted_tenant_id=trusted_tenant_id,
            description=description,
        )
        await self._repo.add(db, source)

        logger.info(
            "Trusted source added: tenant=%s trusted=%s",
            tenant_id,
            trusted_tenant_id,
        )
        return source

    async def remove_trusted_source(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        source_id: UUID,
    ) -> bool:
        """Remove a trusted source.

        Args:
            db: Database session.
            tenant_id: The tenant ID (for security validation).
            source_id: The trusted source ID to remove.

        Returns:
            True if removed, False if not found.
        """
        source = await self._repo.find_trusted_source_scoped(db, source_id, tenant_id)

        if not source:
            return False

        await self._repo.delete(db, source)

        logger.info("Trusted source removed: id=%s tenant=%s", source_id, tenant_id)
        return True

    async def get_available_tenants_for_trust(
        self,
        db: AsyncSession,
        tenant_id: UUID,
    ) -> list[dict]:
        """Get list of tenants that can be added as trusted sources.

        Args:
            db: Database session.
            tenant_id: The current tenant (excluded from results).

        Returns:
            List of tenant dicts with id, slug, display_name, and is_platform flag.
        """
        # Get currently trusted tenant IDs
        trusted_ids_raw = await self._repo.list_trusted_tenant_ids(db, tenant_id)
        excluded_ids: set[UUID] = {tid for tid in trusted_ids_raw if tid is not None}
        excluded_ids.add(tenant_id)  # Exclude self

        # Get all active tenants not in trusted list
        tenants = await self._repo.list_available_tenants(db, excluded_ids)

        return [
            {
                "id": str(t.id),
                "slug": t.slug,
                "display_name": t.display_name,
                "is_platform": t.is_platform,
            }
            for t in tenants
        ]

    async def get_platform_tenant(self, db: AsyncSession) -> Tenant | None:
        """Get the platform tenant.

        Args:
            db: Database session.

        Returns:
            The platform tenant or None if not found.
        """
        return await self._repo.find_platform_tenant(db)

    async def is_platform_trusted(
        self,
        db: AsyncSession,
        tenant_id: UUID,
    ) -> bool:
        """Check if platform tenant users are trusted by this tenant.

        Args:
            db: Database session.
            tenant_id: The tenant ID.

        Returns:
            True if platform tenant is in trusted sources.
        """
        platform = await self.get_platform_tenant(db)
        if not platform:
            return False

        return await self._repo.platform_source_exists(db, tenant_id, platform.id)
