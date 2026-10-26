# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Issuer resolution service for multi-tenant OAuth2/OIDC.

This module provides secure issuer resolution based on tenant configuration
stored in the database, NOT from user-controlled HTTP headers.

Security note: The issuer is derived from trusted configuration (database/settings),
not from the Host header, to prevent host header injection attacks.
"""

import logging
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from auth.config import settings
from auth.db.models.tenant import CustomDomainStatus, Tenant
from auth.db.repositories.issuer import IssuerRepository
from auth.middlewares.tenant import get_tenant_context

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Module-level repository singleton (stateless).
_issuer_repository = IssuerRepository()


async def get_tenant_by_id(db: AsyncSession, tenant_id: str) -> Tenant | None:
    """Get an active tenant by ID.

    Args:
        db: Database session.
        tenant_id: Tenant UUID as string.

    Returns:
        Tenant if found and active, None otherwise.
    """
    try:
        from uuid import UUID

        return await _issuer_repository.find_active_tenant(db, UUID(tenant_id))
    except (ValueError, Exception) as e:
        logger.warning("Error fetching tenant %s: %s", tenant_id, e)
        return None


async def get_tenant_issuer(db: AsyncSession, tenant: Tenant | None = None) -> str:
    """Get the issuer URL for a tenant.

    The issuer is derived from trusted configuration (database/settings),
    NOT from user-controlled HTTP headers.

    Priority:
    1. Custom domain (if active) -> https://{custom_domain}
    2. Subdomain tenant -> https://{slug}.{tenant_base_domain}
    3. Platform tenant -> https://{tenant_base_domain}
    4. Fallback to settings.issuer or default

    Args:
        db: Database session.
        tenant: Tenant object (optional, will be resolved from context if not provided).

    Returns:
        Issuer URL as string.
    """
    # If no tenant provided, try to resolve from context
    if tenant is None:
        tenant_ctx = get_tenant_context()
        if tenant_ctx and tenant_ctx.tenant_id:
            tenant = await get_tenant_by_id(db, tenant_ctx.tenant_id)

    # If still no tenant, fall back to settings
    if tenant is None:
        issuer = settings.issuer or f"https://{settings.tenant_base_domain}"
        logger.debug("No tenant context, using fallback issuer: %s", issuer)
        return issuer

    # 1. Custom domain (if active)
    if tenant.custom_domain and tenant.custom_domain_status == CustomDomainStatus.ACTIVE:
        issuer = f"https://{tenant.custom_domain}"
        logger.debug("Using custom domain issuer for tenant %s: %s", tenant.slug, issuer)
        return issuer

    # 2. Subdomain tenant (non-platform)
    if not tenant.is_platform and settings.tenant_base_domain:
        issuer = f"https://{tenant.slug}.{settings.tenant_base_domain}"
        logger.debug("Using subdomain issuer for tenant %s: %s", tenant.slug, issuer)
        return issuer

    # 3. Platform tenant - use base domain
    if settings.tenant_base_domain:
        issuer = f"https://{settings.tenant_base_domain}"
        logger.debug("Using platform issuer for tenant %s: %s", tenant.slug, issuer)
        return issuer

    # 4. Fallback to settings.issuer
    issuer = settings.issuer or "http://localhost:8000"
    logger.debug("Using settings.issuer fallback: %s", issuer)
    return issuer


async def get_issuer_from_context(db: AsyncSession) -> str:
    """Get the issuer URL from the current tenant context.

    Convenience function that resolves the tenant from the request context
    and returns the appropriate issuer.

    Args:
        db: Database session.

    Returns:
        Issuer URL as string.
    """
    return await get_tenant_issuer(db, tenant=None)


def validate_issuer_for_tenant(
    issuer: str,
    tenant: Tenant,
) -> bool:
    """Validate that an issuer URL is valid for a tenant.

    Used to validate tokens - ensures the issuer claim matches
    what we would issue for this tenant.

    Args:
        issuer: Issuer URL to validate.
        tenant: Tenant to validate against.

    Returns:
        True if the issuer is valid for this tenant, False otherwise.
    """
    # Custom domain issuer
    if tenant.custom_domain and tenant.custom_domain_status == CustomDomainStatus.ACTIVE:
        expected = f"https://{tenant.custom_domain}"
        if issuer == expected:
            return True

    # Subdomain issuer
    if not tenant.is_platform and settings.tenant_base_domain:
        expected = f"https://{tenant.slug}.{settings.tenant_base_domain}"
        if issuer == expected:
            return True

    # Platform issuer
    if tenant.is_platform:
        if settings.tenant_base_domain:
            expected = f"https://{settings.tenant_base_domain}"
            if issuer == expected:
                return True
        if settings.issuer and issuer == settings.issuer:
            return True

    return False
