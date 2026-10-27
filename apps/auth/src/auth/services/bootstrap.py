# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Bootstrap of a deployment: what auth needs to exist before it can serve anything.

``auth bootstrap`` is idempotent and driven by the settings, so that no deployment value
(slug, name, branding, redirect URI) is written in the code or in a migration. It makes sure
that:

* the built-in scopes and roles of auth (``ADMIN_SCOPES``, ``DEFAULT_ROLES``) exist;
* a platform tenant exists, the one flagged ``is_platform`` (found by the flag, never by its
  slug or id, so a tenant created earlier under any name is adopted), with its default roles and,
  once, the branding of the settings;
* the users without a registration tenant are registered on the platform tenant, its trusted
  sources without a trusted tenant point at it, and every user registered on it is a member;
* the OAuth2 client of Swagger UI exists with the redirect URIs and scopes of the settings.

Existing rows are left as they are, except the redirect URIs and scopes of the Swagger UI
client, which follow the settings.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from auth.config import Settings
from auth.db.models.oauth2 import OAuth2Client
from auth.db.models.tenant import Tenant, TenantBranding, TenantTrustMode
from auth.db.repositories.bootstrap import BootstrapRepository
from auth.services.catalog import Catalog, SyncReport, sync_catalog
from auth.services.tenant_role import tenant_role_service

logger = logging.getLogger(__name__)

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$")
BRANDING_FIELDS = frozenset(
    column.name
    for column in TenantBranding.__table__.columns
    if column.name not in {"id", "tenant_id", "created_at", "updated_at"}
)
MEMBER_ROLE = "member"


class BootstrapError(Exception):
    """The settings or the database do not allow the bootstrap."""


@dataclass(frozen=True)
class BootstrapOptions:
    """The settings that drive the bootstrap, validated."""

    slug: str
    display_name: str
    tenant_id: uuid.UUID | None = None
    branding: dict[str, str] = field(default_factory=dict)
    swagger_client_id: str = "swagger-ui"
    swagger_scopes: tuple[str, ...] = ("openid", "profile", "email")
    swagger_redirect_uris: tuple[str, ...] = ("/docs/oauth2-redirect",)

    @classmethod
    def from_settings(cls, source: Settings) -> BootstrapOptions:
        """Read and validate the settings; raises :class:`BootstrapError`."""
        if not SLUG.match(source.platform_tenant_slug):
            raise BootstrapError(
                f"PLATFORM_TENANT_SLUG {source.platform_tenant_slug!r} is not a valid slug "
                "(lower case letters, digits and hyphens)"
            )
        if not source.platform_tenant_display_name.strip():
            raise BootstrapError("PLATFORM_TENANT_DISPLAY_NAME is empty")
        tenant_id = None
        if source.platform_tenant_id:
            try:
                tenant_id = uuid.UUID(source.platform_tenant_id)
            except ValueError as exc:
                raise BootstrapError("PLATFORM_TENANT_ID is not a UUID") from exc
        unknown = sorted(set(source.platform_tenant_branding) - BRANDING_FIELDS)
        if unknown:
            raise BootstrapError(
                f"PLATFORM_TENANT_BRANDING has unknown keys: {', '.join(unknown)} "
                f"(known: {', '.join(sorted(BRANDING_FIELDS))})"
            )
        if not source.swagger_client_id:
            raise BootstrapError("SWAGGER_CLIENT_ID is empty")
        return cls(
            slug=source.platform_tenant_slug,
            display_name=source.platform_tenant_display_name.strip(),
            tenant_id=tenant_id,
            branding=dict(source.platform_tenant_branding),
            swagger_client_id=source.swagger_client_id,
            swagger_scopes=tuple(source.swagger_scopes.split()),
            swagger_redirect_uris=tuple(source.swagger_redirect_uris),
        )


async def bootstrap(
    db: AsyncSession,
    options: BootstrapOptions,
    repository: BootstrapRepository | None = None,
) -> SyncReport:
    """Bring the database to the state described in the module docstring.

    Stages the changes on ``db`` and flushes them; the caller commits (or rolls back for a dry
    run).

    Raises:
        BootstrapError: The slug of the platform tenant is taken by another tenant.
    """
    repo = repository or BootstrapRepository()
    report = SyncReport()

    report.extend(await sync_catalog(db, Catalog.builtin()))

    tenant = await repo.find_platform_tenant(db)
    if tenant is None:
        if await repo.find_tenant_by_slug(db, options.slug) is not None:
            raise BootstrapError(
                f"the slug {options.slug!r} belongs to a tenant that is not the platform "
                "tenant: choose another PLATFORM_TENANT_SLUG"
            )
        tenant = Tenant(
            id=options.tenant_id or uuid.uuid4(),
            slug=options.slug,
            display_name=options.display_name,
            is_active=True,
            is_platform=True,
            trust_mode=TenantTrustMode.ALL,
            settings={},
        )
        await repo.add(db, tenant)
        await tenant_role_service.create_default_roles(db, tenant)
        report.created.append(f"platform tenant {tenant.slug}")
    elif tenant.slug != options.slug:
        report.skipped.append(
            f"platform tenant slug (the existing tenant is {tenant.slug!r}, the settings say "
            f"{options.slug!r}; it is left as it is)"
        )

    if options.branding and await repo.find_branding(db, tenant.id) is None:
        await repo.add(db, TenantBranding(tenant_id=tenant.id, **options.branding))
        report.created.append(f"branding of the platform tenant ({', '.join(options.branding)})")

    registered = await repo.register_orphan_users(db, tenant.id)
    if registered:
        report.updated.append(f"{registered} user(s) registered on the platform tenant")
    trusted = await repo.trust_platform_in_open_sources(db, tenant.id)
    if trusted:
        report.updated.append(f"{trusted} trusted source(s) pointed at the platform tenant")
    role = await repo.find_role(db, tenant.id, MEMBER_ROLE)
    if role is None:
        report.skipped.append(f"membership of the platform tenant (it has no {MEMBER_ROLE!r} role)")
    else:
        members = await repo.add_missing_members(db, tenant.id, role.id)
        if members:
            report.updated.append(f"{members} user(s) made member of the platform tenant")

    await _swagger_client(db, repo, options, report)
    await db.flush()
    return report


async def _swagger_client(
    db: AsyncSession,
    repo: BootstrapRepository,
    options: BootstrapOptions,
    report: SyncReport,
) -> None:
    redirect_uris = list(options.swagger_redirect_uris)
    scopes = list(options.swagger_scopes)
    client = await repo.find_client(db, options.swagger_client_id)
    if client is None:
        client = OAuth2Client(
            client_id=options.swagger_client_id,
            name="Swagger UI",
            description="Built-in OAuth2 client of the API documentation (/docs)",
            redirect_uris=redirect_uris,
            allowed_scopes=scopes,
            allowed_grant_types=["authorization_code"],
            token_endpoint_auth_method="none",
            is_confidential=False,
            is_active=True,
            require_pkce=True,
            require_consent=False,
        )
        await repo.add(db, client)
        report.created.append(f"client {client.client_id}")
        return
    changes = []
    if client.redirect_uris != redirect_uris:
        client.redirect_uris = redirect_uris
        changes.append("redirect URIs")
    if client.allowed_scopes != scopes:
        client.allowed_scopes = scopes
        changes.append("scopes")
    if changes:
        report.updated.append(f"client {client.client_id} ({', '.join(changes)})")
