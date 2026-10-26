# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tenant resolution middleware for multi-tenancy support."""

import logging
import re
from contextvars import ContextVar
from dataclasses import dataclass

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
    1. Subdomain: acme.auth.example.com → tenant "acme"
    2. Custom domain (CNAME): login.acme.com → lookup in database
    3. Path prefix: /t/acme/oauth2/authorize → tenant "acme"

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
            base_domain: The base domain (e.g., "auth.example.com").
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

        # Check if host is an unresolved subdomain — redirect to base domain
        headers = dict(scope.get("headers", []))
        host = headers.get(b"host", b"").decode("utf-8").lower()
        if ":" in host:
            host = host.split(":")[0]

        # Resolve tenant
        tenant_context = await self._resolve_tenant(scope)

        # If the host is a subdomain of base_domain but resolved to platform
        # fallback (no matching tenant), redirect to the base domain
        if (
            tenant_context
            and tenant_context.resolution_method == "platform"
            and host != self.base_domain
            and host.endswith(f".{self.base_domain}")
        ):
            path = scope.get("path", "/")
            query_string = scope.get("query_string", b"").decode("utf-8")
            redirect_url = f"https://{self.base_domain}{path}"
            if query_string:
                redirect_url += f"?{query_string}"

            logger.info(
                "Unknown subdomain %s, redirecting to %s",
                host,
                redirect_url,
            )
            await self._send_redirect(send, redirect_url)
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
        4. Fallback to platform tenant (main domain)
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
        tenant_context = await self._resolve_from_subdomain(host)
        if tenant_context:
            return tenant_context

        # 3. Try custom domain lookup
        if self.custom_domain_lookup and host and host != self.base_domain:
            tenant_context = await self._resolve_from_custom_domain(host)
            if tenant_context:
                return tenant_context

        # 4. Fallback to platform tenant (main domain)
        return await self._resolve_platform_tenant()

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
        """Look up tenant ID from database by slug.

        Delegates to :class:`TenantService` — which in turn calls
        :class:`TenantRepository`. Kept as a method on the middleware for
        test compatibility (tests patch this entry point directly).
        """
        from auth.core.database import async_session_factory
        from auth.services.tenant import tenant_service

        try:
            async with async_session_factory() as db:
                return await tenant_service.find_id_by_active_slug(db, slug)
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

        # Look up tenant_id from database
        tenant_id = await self._lookup_tenant_id_by_slug(subdomain)

        if not tenant_id:
            logger.debug("No tenant found for subdomain slug: %s, falling through", subdomain)
            return None

        logger.debug("Resolved tenant from subdomain: slug=%s", subdomain)

        return TenantContext(
            tenant_id=tenant_id,
            tenant_slug=subdomain,
            resolution_method="subdomain",
        )

    async def _resolve_from_custom_domain(self, host: str) -> TenantContext | None:
        """Resolve tenant from custom domain (CNAME) via database lookup.

        Delegates to :class:`TenantService` — which in turn calls
        :class:`TenantRepository`. Kept as a method on the middleware for
        test compatibility.
        """
        from auth.core.database import async_session_factory
        from auth.services.tenant import tenant_service

        try:
            async with async_session_factory() as db:
                match = await tenant_service.find_id_slug_by_active_custom_domain(db, host)
                if match is not None:
                    tenant_id, tenant_slug = match
                    logger.debug(
                        "Resolved tenant from custom domain: host=%s, slug=%s",
                        host,
                        tenant_slug,
                    )
                    return TenantContext(
                        tenant_id=tenant_id,
                        tenant_slug=tenant_slug,
                        resolution_method="custom_domain",
                    )
        except Exception as e:
            logger.exception("Error looking up custom domain %s: %s", host, e)

        return None

    @staticmethod
    async def _send_redirect(send: Send, url: str) -> None:
        """Send a 302 redirect response at the ASGI level."""
        await send(
            {
                "type": "http.response.start",
                "status": 302,
                "headers": [
                    [b"location", url.encode("utf-8")],
                    [b"content-length", b"0"],
                ],
            }
        )
        await send({"type": "http.response.body", "body": b""})

    async def _resolve_platform_tenant(self) -> TenantContext | None:
        """Resolve the platform tenant (main domain fallback).

        Delegates to :class:`TenantService` — which in turn calls
        :class:`TenantRepository`. Kept as a method on the middleware for
        test compatibility.
        """
        from auth.core.database import async_session_factory
        from auth.services.tenant import tenant_service

        try:
            async with async_session_factory() as db:
                match = await tenant_service.find_platform_id_slug(db)
                if match is not None:
                    tenant_id, tenant_slug = match
                    logger.debug(
                        "Resolved platform tenant: slug=%s",
                        tenant_slug,
                    )
                    return TenantContext(
                        tenant_id=tenant_id,
                        tenant_slug=tenant_slug,
                        resolution_method="platform",
                    )
        except Exception as e:
            logger.exception("Error looking up platform tenant: %s", e)

        logger.warning("No platform tenant found - this may cause issues")
        return None


def get_session_cookie_name() -> str:
    """Get the session cookie name based on current tenant context.

    For tenant subdomain/path resolution, returns a tenant-scoped name
    (e.g., "session_acme") to isolate tenant sessions from the platform.
    For platform and custom domains, returns the default name.
    """
    from auth.config import settings

    tenant_ctx = get_tenant_context()
    if (
        tenant_ctx
        and tenant_ctx.tenant_slug
        and tenant_ctx.resolution_method
        in (
            "subdomain",
            "path",
        )
    ):
        return f"{settings.session_cookie_name}_{tenant_ctx.tenant_slug}"
    return settings.session_cookie_name


def get_csrf_cookie_name() -> str:
    """Get the CSRF cookie name based on current tenant context."""
    tenant_ctx = get_tenant_context()
    if (
        tenant_ctx
        and tenant_ctx.tenant_slug
        and tenant_ctx.resolution_method
        in (
            "subdomain",
            "path",
        )
    ):
        return f"csrf_{tenant_ctx.tenant_slug}"
    return "csrf_token"


def get_session_cookie_domain() -> str | None:
    """Get the cookie domain based on current tenant resolution method.

    For subdomain/path resolution, returns ".base_domain" so the cookie
    is shared between slug.base_domain and base_domain/t/slug/.
    For platform and custom domains, returns None (host-only cookie).
    """
    from auth.config import settings

    tenant_ctx = get_tenant_context()
    if (
        tenant_ctx
        and tenant_ctx.resolution_method in ("subdomain", "path")
        and settings.tenant_base_domain
    ):
        return f".{settings.tenant_base_domain}"
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
