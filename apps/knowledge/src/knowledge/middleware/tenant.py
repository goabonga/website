# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tenant resolution middleware for multi-tenancy support.

Resolves the current tenant from the incoming request using multiple strategies:
1. Path prefix: /t/{slug}/...
2. Subdomain: {slug}.base_domain
3. Custom domain (CNAME): lookup in database (Enterprise feature)
4. Fallback: no tenant (main domain)
"""

import logging
import re
from contextvars import ContextVar
from dataclasses import dataclass

from starlette.responses import RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

# Context variable for tenant in async context
_tenant_context: ContextVar["TenantContext | None"] = ContextVar("tenant_context", default=None)


@dataclass
class TenantContext:
    """Tenant context for the current request."""

    tenant_id: str | None = None
    tenant_slug: str | None = None
    resolution_method: str | None = None  # "subdomain", "path", "custom_domain"


def get_tenant_context() -> TenantContext | None:
    """Get the current tenant context from the context variable."""
    return _tenant_context.get()


def set_tenant_context(context: TenantContext | None) -> None:
    """Set the tenant context in the context variable."""
    _tenant_context.set(context)


class TenantMiddleware:
    """ASGI middleware for tenant resolution.

    Resolves the tenant from:
    1. Path prefix: /t/{slug}/... -> tenant slug, path rewritten
    2. Subdomain: {slug}.base_domain -> tenant slug
    3. Custom domain (CNAME): login.acme.com -> lookup in database
    4. Fallback: no tenant context (main domain)

    The resolved tenant is stored in:
    - scope["tenant"]: TenantContext object
    - Context variable: accessible via get_tenant_context()
    """

    # Regex for valid tenant slug (subdomain-safe)
    SLUG_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")

    # Path prefix pattern: /t/{slug}/...
    PATH_PREFIX_PATTERN = re.compile(r"^/t/([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)(/.*)$")

    def __init__(
        self,
        app: ASGIApp,
        base_domain: str,
        custom_domain_lookup: bool = True,
    ) -> None:
        """Initialize the tenant middleware.

        Args:
            app: The ASGI application.
            base_domain: The base domain (e.g., "knowledge.example.com").
                         Subdomains of this domain are treated as tenant slugs.
            custom_domain_lookup: Whether to lookup custom domains in database.
        """
        self.app = app
        self.base_domain = base_domain.lower()
        self.custom_domain_lookup = custom_domain_lookup
        logger.info(
            "TenantMiddleware initialized with base_domain=%s, custom_domain_lookup=%s",
            self.base_domain,
            self.custom_domain_lookup,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Resolve tenant
        tenant_context = await self._resolve_tenant(scope)

        # Redirect to base domain if subdomain doesn't match any tenant
        if (
            tenant_context
            and tenant_context.resolution_method == "subdomain"
            and tenant_context.tenant_id is None
        ):
            path = scope.get("path", "/")
            query_string = scope.get("query_string", b"")
            redirect_url = f"https://{self.base_domain}{path}"
            if query_string:
                redirect_url += f"?{query_string.decode('utf-8')}"

            logger.info(
                "Unknown tenant subdomain '%s', redirecting to %s",
                tenant_context.tenant_slug,
                redirect_url,
            )
            response = RedirectResponse(url=redirect_url, status_code=302)
            await response(scope, receive, send)
            return

        # Store in scope and context variable
        scope["tenant"] = tenant_context
        set_tenant_context(tenant_context)

        logger.debug(
            "Tenant resolved: slug=%s, method=%s",
            tenant_context.tenant_slug if tenant_context else None,
            tenant_context.resolution_method if tenant_context else None,
        )

        try:
            await self.app(scope, receive, send)
        finally:
            # Clear context after request
            set_tenant_context(None)

    async def _resolve_tenant(self, scope: Scope) -> TenantContext | None:
        """Resolve tenant from request.

        Resolution order:
        1. Path prefix (/t/{slug}/...)
        2. Subdomain ({slug}.base_domain)
        3. Custom domain (CNAME lookup)
        """
        path = scope.get("path", "")
        headers = dict(scope.get("headers", []))
        host = headers.get(b"host", b"").decode("utf-8").lower()

        # Remove port from host if present
        if ":" in host:
            host = host.split(":")[0]

        # 1. Try path prefix resolution
        tenant_context = await self._resolve_from_path(path, scope)
        if tenant_context:
            return tenant_context

        # 2. Try subdomain resolution
        if self.base_domain:
            tenant_context = await self._resolve_from_subdomain(host)
            if tenant_context:
                return tenant_context

        # 3. Try custom domain lookup
        if self.custom_domain_lookup and host and host != self.base_domain:
            tenant_context = await self._resolve_from_custom_domain(host)
            if tenant_context:
                return tenant_context

        # 4. No tenant resolved (main domain without tenant prefix)
        return None

    async def _resolve_from_path(self, path: str, scope: Scope) -> TenantContext | None:
        """Resolve tenant from path prefix /t/{slug}/..."""
        match = self.PATH_PREFIX_PATTERN.match(path)
        if match:
            slug = match.group(1)
            # Rewrite path to remove tenant prefix
            new_path = match.group(3) or "/"
            scope["path"] = new_path
            scope["raw_path"] = new_path.encode("utf-8")

            logger.debug("Resolved tenant from path: slug=%s, new_path=%s", slug, new_path)

            # Look up tenant_id from database
            tenant_id = await self._lookup_tenant_id_by_slug(slug)

            return TenantContext(
                tenant_id=tenant_id,
                tenant_slug=slug,
                resolution_method="path",
            )
        return None

    async def _lookup_tenant_id_by_slug(self, slug: str) -> str | None:
        """Look up tenant ID from database by slug."""
        from sqlalchemy import select

        from knowledge.database import async_session_factory
        from knowledge.models.organization import Organization

        try:
            async with async_session_factory() as db:
                result = await db.execute(
                    select(Organization.id).where(
                        Organization.slug == slug,
                        Organization.is_active == True,  # noqa: E712
                    )
                )
                row = result.first()
                if row:
                    return str(row.id)
        except Exception as e:
            logger.exception("Error looking up tenant by slug %s: %s", slug, e)

        return None

    async def _resolve_from_subdomain(self, host: str) -> TenantContext | None:
        """Resolve tenant from subdomain {slug}.base_domain."""
        if not host.endswith(f".{self.base_domain}"):
            return None

        # Extract subdomain
        subdomain = host[: -(len(self.base_domain) + 1)]

        # Validate slug format
        if not self.SLUG_PATTERN.match(subdomain):
            logger.warning("Invalid tenant slug from subdomain: %s", subdomain)
            return None

        logger.debug("Resolved tenant from subdomain: slug=%s", subdomain)

        # Look up tenant_id from database
        tenant_id = await self._lookup_tenant_id_by_slug(subdomain)

        return TenantContext(
            tenant_id=tenant_id,
            tenant_slug=subdomain,
            resolution_method="subdomain",
        )

    async def _resolve_from_custom_domain(self, host: str) -> TenantContext | None:
        """Resolve tenant from custom domain (CNAME) via database lookup."""
        from sqlalchemy import select

        from knowledge.database import async_session_factory
        from knowledge.models.enums import CustomDomainStatus
        from knowledge.models.organization import Organization

        try:
            async with async_session_factory() as db:
                result = await db.execute(
                    select(Organization.id, Organization.slug).where(
                        Organization.custom_domain == host,
                        Organization.custom_domain_status == CustomDomainStatus.ACTIVE,
                        Organization.is_active == True,  # noqa: E712
                    )
                )
                row = result.first()

                if row:
                    logger.debug(
                        "Resolved tenant from custom domain: host=%s, slug=%s",
                        host,
                        row.slug,
                    )
                    return TenantContext(
                        tenant_id=str(row.id),
                        tenant_slug=row.slug,
                        resolution_method="custom_domain",
                    )
        except Exception as e:
            logger.exception("Error looking up custom domain %s: %s", host, e)

        return None


def require_tenant() -> TenantContext:
    """Get the current tenant context, raising an error if not set.

    Returns:
        The current tenant context.

    Raises:
        ValueError: If no tenant context is set.
    """
    context = get_tenant_context()
    if context is None or context.tenant_slug is None:
        raise ValueError("No tenant context available")
    return context
