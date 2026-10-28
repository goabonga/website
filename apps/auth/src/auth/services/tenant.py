# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tenant management service."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from auth.db.models.tenant import (
    IdentityProvider,
    Tenant,
    TenantBranding,
    TenantCustomRole,
    TenantMember,
    TenantTemplate,
)
from auth.db.models.user import UserEmail
from auth.db.repositories.tenant import TenantRepository
from auth.services.tenant_role import tenant_role_service

logger = logging.getLogger(__name__)


class TenantService:
    """Service for tenant, member and identity-provider operations.

    Orchestrates tenant-related business flows. SQL access is delegated to
    :class:`TenantRepository`. Transaction boundaries remain at the caller:
    service methods flush but never commit.

    Scope covers Tenant, TenantMember, IdentityProvider and TenantTemplate.
    Branding and webhooks are handled by their own services (follow-up work).
    """

    def __init__(self, repository: TenantRepository | None = None) -> None:
        self._repo = repository or TenantRepository()

    # ------------------------------------------------------------------
    # Tenant reads
    # ------------------------------------------------------------------

    async def get_by_id(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Tenant | None:
        """Fetch a tenant by ID."""
        return await self._repo.find_by_id(db, tenant_id)

    async def get_by_id_with_branding(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Tenant | None:
        """Fetch a tenant by ID with its branding relation eager-loaded."""
        return await self._repo.find_by_id_with_branding(db, tenant_id)

    async def get_by_id_with_templates(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Tenant | None:
        """Fetch a tenant by ID with its templates relation eager-loaded."""
        return await self._repo.find_by_id_with_templates(db, tenant_id)

    async def get_active_by_id(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Tenant | None:
        """Fetch an active tenant by ID."""
        return await self._repo.find_active_by_id(db, tenant_id)

    async def get_by_slug(
        self,
        db: AsyncSession,
        slug: str,
    ) -> Tenant | None:
        """Fetch a tenant by slug."""
        return await self._repo.find_by_slug(db, slug)

    async def find_id_by_active_slug(
        self,
        db: AsyncSession,
        slug: str,
    ) -> str | None:
        """Return the active tenant's ID (as string) for ``slug``.

        Tenant-resolution middleware entry point.
        """
        return await self._repo.find_id_by_active_slug(db, slug)

    async def get_by_custom_domain(
        self,
        db: AsyncSession,
        domain: str,
    ) -> Tenant | None:
        """Return the tenant that holds ``domain`` as its custom domain, if any."""
        return await self._repo.find_by_custom_domain(db, domain)

    async def find_id_slug_by_active_custom_domain(
        self,
        db: AsyncSession,
        host: str,
    ) -> tuple[str, str] | None:
        """Return ``(id, slug)`` for the active tenant bound to ``host``.

        Tenant-resolution middleware entry point for CNAME lookups.
        """
        return await self._repo.find_id_slug_by_active_custom_domain(db, host)

    async def find_platform_id_slug(
        self,
        db: AsyncSession,
    ) -> tuple[str, str] | None:
        """Return ``(id, slug)`` for the active platform tenant (if any).

        Tenant-resolution middleware fallback.
        """
        return await self._repo.find_platform_id_slug(db)

    async def get_display_name(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> str | None:
        """Return the ``display_name`` of a tenant (or ``None``)."""
        return await self._repo.find_display_name(db, tenant_id)

    async def get_settings(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> dict | None:
        """Return the ``settings`` JSON blob for ``tenant_id`` (or None)."""
        return await self._repo.find_settings_by_id(db, tenant_id)

    async def list_id_name_pairs(
        self,
        db: AsyncSession,
        *,
        ids: list[uuid.UUID] | set[uuid.UUID] | None = None,
    ) -> list[tuple[uuid.UUID, str]]:
        """List ``(id, display_name)`` pairs for dropdowns/lookups."""
        return await self._repo.list_id_name_pairs(db, ids=ids)

    async def list_active_dropdown(
        self,
        db: AsyncSession,
    ) -> list[tuple[uuid.UUID, str, str]]:
        """List active tenants as ``(id, display_name, slug)`` rows.

        Intended for admin dropdown/filter UIs.
        """
        return await self._repo.list_active_dropdown(db)

    async def list_tenants(
        self,
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        is_active: bool | None = None,
        eager_members: bool = False,
        eager_idps: bool = False,
    ) -> tuple[list[Tenant], int]:
        """List tenants with filters and pagination."""
        return await self._repo.list_tenants(
            db,
            page=page,
            page_size=page_size,
            search=search,
            is_active=is_active,
            eager_members=eager_members,
            eager_idps=eager_idps,
        )

    async def resolve(
        self,
        db: AsyncSession,
        tenant_id_or_slug: str,
    ) -> Tenant | None:
        """Resolve a tenant by either UUID or slug.

        If ``tenant_id_or_slug`` parses as a UUID, first look up by ID;
        otherwise fall back to a slug lookup. This mirrors the common
        admin-page pattern.
        """
        try:
            tenant_uuid = uuid.UUID(tenant_id_or_slug)
        except ValueError:
            return await self._repo.find_by_slug(db, tenant_id_or_slug)
        return await self._repo.find_by_id(db, tenant_uuid)

    async def resolve_with_detail(
        self,
        db: AsyncSession,
        tenant_id_or_slug: str,
    ) -> Tenant | None:
        """Resolve a tenant with members/IdPs/roles eager-loaded for detail page."""
        try:
            tenant_uuid = uuid.UUID(tenant_id_or_slug)
        except ValueError:
            return await self._repo.find_by_slug_with_detail(db, tenant_id_or_slug)
        return await self._repo.find_by_id_with_detail(db, tenant_uuid)

    async def resolve_with_branding(
        self,
        db: AsyncSession,
        tenant_id_or_slug: str,
    ) -> Tenant | None:
        """Resolve a tenant with its ``branding`` relation eager-loaded."""
        try:
            tenant_uuid = uuid.UUID(tenant_id_or_slug)
        except ValueError:
            return await self._repo.find_by_slug_with_branding(db, tenant_id_or_slug)
        return await self._repo.find_by_id_with_branding(db, tenant_uuid)

    async def resolve_with_templates(
        self,
        db: AsyncSession,
        tenant_id_or_slug: str,
    ) -> Tenant | None:
        """Resolve a tenant with its ``templates`` relation eager-loaded."""
        try:
            tenant_uuid = uuid.UUID(tenant_id_or_slug)
        except ValueError:
            return await self._repo.find_by_slug_with_templates(db, tenant_id_or_slug)
        return await self._repo.find_by_id_with_templates(db, tenant_uuid)

    # ------------------------------------------------------------------
    # Tenant writes
    # ------------------------------------------------------------------

    async def slug_exists(self, db: AsyncSession, slug: str) -> bool:
        """Return ``True`` if a tenant already uses this slug."""
        return (await self._repo.find_by_slug(db, slug)) is not None

    async def create_tenant(
        self,
        db: AsyncSession,
        *,
        slug: str,
        display_name: str,
        custom_domain: str | None = None,
        is_active: bool = True,
        settings: dict | None = None,
        create_default_roles: bool = True,
    ) -> Tenant:
        """Provision a tenant and optionally seed it with default RBAC roles.

        Flushes to obtain the generated ID but does not commit; the caller
        owns the transaction boundary.

        Raises:
            ValueError: If the slug is already taken.
        """
        if await self._repo.find_by_slug(db, slug):
            raise ValueError("Slug already exists")

        tenant = Tenant(
            slug=slug,
            display_name=display_name,
            custom_domain=custom_domain,
            is_active=is_active,
            settings=settings if settings is not None else {},
        )
        await self._repo.add(db, tenant)

        if create_default_roles:
            await tenant_role_service.create_default_roles(db, tenant)

        logger.info("Tenant created: id=%s slug=%s", tenant.id, slug)
        return tenant

    async def update_tenant(
        self,
        db: AsyncSession,
        tenant: Tenant,
        *,
        display_name: str | None = None,
        custom_domain: str | None = None,
        is_active: bool | None = None,
        settings: dict | None = None,
    ) -> Tenant:
        """Apply a sparse update to a tenant and flush."""
        if display_name is not None:
            tenant.display_name = display_name
        if custom_domain is not None:
            tenant.custom_domain = custom_domain or None
        if is_active is not None:
            tenant.is_active = is_active
        if settings is not None:
            tenant.settings = settings
        await db.flush()
        return tenant

    async def set_active(
        self,
        db: AsyncSession,
        tenant: Tenant,
        *,
        active: bool,
    ) -> Tenant:
        """Toggle ``tenant.is_active`` and flush."""
        tenant.is_active = active
        await db.flush()
        return tenant

    async def delete_tenant(self, db: AsyncSession, tenant: Tenant) -> None:
        """Stage a tenant deletion (caller owns the commit)."""
        await self._repo.delete(db, tenant)

    async def add_tenant(self, db: AsyncSession, tenant: Tenant) -> Tenant:
        """Stage a pre-built :class:`Tenant` row and flush.

        Exposed for flows that build the row themselves (e.g. self-service
        organisation creation) but should not touch ``db.add`` directly.
        The caller owns the transaction boundary.
        """
        await self._repo.add(db, tenant)
        return tenant

    # ------------------------------------------------------------------
    # Members
    # ------------------------------------------------------------------

    async def list_members(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        page: int | None = None,
        page_size: int | None = None,
    ) -> list[TenantMember]:
        """List members of a tenant."""
        return await self._repo.list_members(db, tenant_id, page=page, page_size=page_size)

    async def count_members(self, db: AsyncSession, tenant_id: uuid.UUID) -> int:
        """Count members of a tenant."""
        return await self._repo.count_members(db, tenant_id)

    async def get_member(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> TenantMember | None:
        """Fetch a membership."""
        return await self._repo.find_member(db, tenant_id, user_id)

    async def get_member_by_id(
        self,
        db: AsyncSession,
        member_id: uuid.UUID,
        *,
        eager_role: bool = False,
    ) -> TenantMember | None:
        """Fetch a membership by primary key."""
        return await self._repo.find_member_by_id(db, member_id, eager_role=eager_role)

    async def list_user_memberships(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> list[TenantMember]:
        """List memberships for a user with tenant + role eager-loaded."""
        return await self._repo.list_user_memberships(db, user_id)

    async def list_user_memberships_with_idps(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> list[TenantMember]:
        """List memberships with tenant (+idps) and custom role eager-loaded.

        Used by the user settings "organisations" page that needs the
        linkable/linked IdP list for each tenant the user belongs to, ordered
        by most recently joined.
        """
        return await self._repo.list_user_memberships_with_idps(db, user_id)

    async def list_user_memberships_with_custom_role(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> list[TenantMember]:
        """List memberships with ``custom_role`` eager-loaded only."""
        return await self._repo.list_user_memberships_with_custom_role(db, user_id)

    async def add_member(self, db: AsyncSession, member: TenantMember) -> TenantMember:
        """Stage a new membership row and flush."""
        await self._repo.add(db, member)
        return member

    async def remove_member(self, db: AsyncSession, member: TenantMember) -> None:
        """Stage a membership deletion (caller owns the commit)."""
        await self._repo.delete(db, member)

    async def create_organisation_with_owner(
        self,
        db: AsyncSession,
        *,
        slug: str,
        display_name: str,
        owner_user_id: uuid.UUID,
    ) -> tuple[Tenant, TenantMember]:
        """Provision a new organisation and enroll ``owner_user_id`` as owner.

        Creates the tenant, seeds the default RBAC roles and attaches the
        caller as a member bound to the ``owner`` role. Flushes so generated
        IDs are populated and refreshes the membership's ``custom_role``
        relation. Does not commit; the caller owns the transaction boundary.

        Raises:
            ValueError: If the slug is already taken.
        """
        if await self._repo.find_by_slug(db, slug):
            raise ValueError("Slug already exists")

        tenant = Tenant(slug=slug, display_name=display_name, settings={})
        await self._repo.add(db, tenant)

        roles = await tenant_role_service.create_default_roles(db, tenant)
        owner_role = next((r for r in roles if r.name == "owner"), None)

        member = TenantMember(
            tenant_id=tenant.id,
            user_id=owner_user_id,
            role_id=owner_role.id if owner_role else None,
            joined_at=datetime.now(UTC),
        )
        await self._repo.add(db, member)
        await db.refresh(member, ["custom_role"])

        logger.info(
            "Tenant created with owner: id=%s slug=%s owner=%s", tenant.id, slug, owner_user_id
        )
        return tenant, member

    # ------------------------------------------------------------------
    # Identity providers
    # ------------------------------------------------------------------

    async def list_idps(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        page: int | None = None,
        page_size: int | None = None,
    ) -> list[IdentityProvider]:
        """List identity providers for a tenant."""
        return await self._repo.list_idps(db, tenant_id, page=page, page_size=page_size)

    async def count_idps(self, db: AsyncSession, tenant_id: uuid.UUID) -> int:
        """Count identity providers for a tenant."""
        return await self._repo.count_idps(db, tenant_id)

    async def get_idp(
        self,
        db: AsyncSession,
        idp_id: uuid.UUID,
    ) -> IdentityProvider | None:
        """Fetch an identity provider by ID."""
        return await self._repo.find_idp(db, idp_id)

    async def get_idp_scoped(
        self,
        db: AsyncSession,
        idp_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> IdentityProvider | None:
        """Fetch an identity provider by ID scoped to ``tenant_id``."""
        return await self._repo.find_idp_scoped(db, idp_id, tenant_id)

    async def add_idp(self, db: AsyncSession, idp: IdentityProvider) -> IdentityProvider:
        """Stage a new identity provider row and flush."""
        await self._repo.add(db, idp)
        return idp

    async def delete_idp(self, db: AsyncSession, idp: IdentityProvider) -> None:
        """Stage an identity-provider deletion (caller owns the commit)."""
        await self._repo.delete(db, idp)

    # ------------------------------------------------------------------
    # Branding
    # ------------------------------------------------------------------

    async def get_branding(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> TenantBranding | None:
        """Fetch the ``TenantBranding`` row for ``tenant_id`` (or ``None``)."""
        return await self._repo.find_branding(db, tenant_id)

    async def delete_branding(self, db: AsyncSession, branding: TenantBranding) -> None:
        """Stage a branding deletion (caller owns the commit)."""
        await self._repo.delete(db, branding)

    async def add_branding(self, db: AsyncSession, branding: TenantBranding) -> TenantBranding:
        """Stage a new branding row (no flush — row is attached to tenant)."""
        await self._repo.add_branding(db, branding)
        return branding

    # ------------------------------------------------------------------
    # Custom roles (scoped)
    # ------------------------------------------------------------------

    async def get_custom_role_by_name(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        name: str,
    ) -> TenantCustomRole | None:
        """Fetch a custom role by (tenant_id, name)."""
        return await self._repo.find_custom_role_by_name(db, tenant_id, name)

    async def get_custom_role_scoped(
        self,
        db: AsyncSession,
        role_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> TenantCustomRole | None:
        """Fetch a custom role scoped to ``tenant_id``."""
        return await self._repo.find_custom_role_scoped(db, role_id, tenant_id)

    async def count_members_for_role(
        self,
        db: AsyncSession,
        role_id: uuid.UUID,
    ) -> int:
        """Count members assigned to ``role_id``."""
        return await self._repo.count_members_for_role(db, role_id)

    async def delete_custom_role(self, db: AsyncSession, role: TenantCustomRole) -> None:
        """Stage a custom role deletion (caller owns the commit)."""
        await self._repo.delete(db, role)

    # ------------------------------------------------------------------
    # Member/user email helpers for admin flows
    # ------------------------------------------------------------------

    async def get_existing_membership(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> TenantMember | None:
        """Return an existing membership row for (tenant_id, user_id)."""
        return await self._repo.existing_membership(db, tenant_id, user_id)

    async def get_user_email_row(
        self,
        db: AsyncSession,
        email: str,
    ) -> UserEmail | None:
        """Fetch a :class:`UserEmail` row by address (exact match)."""
        return await self._repo.find_user_email_row(db, email)

    async def get_member_primary_email(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> str | None:
        """Return the primary email for ``user_id`` (or ``None``)."""
        return await self._repo.find_primary_email_for_user(db, user_id)

    # ------------------------------------------------------------------
    # Templates
    # ------------------------------------------------------------------

    async def list_templates(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> list[TenantTemplate]:
        """List every template override for a tenant ordered by template name."""
        return await self._repo.list_templates(db, tenant_id)

    async def get_template(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        template_name: str,
    ) -> TenantTemplate | None:
        """Fetch a template override by (tenant_id, template_name)."""
        return await self._repo.find_template(db, tenant_id, template_name)

    async def upsert_template(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        template_name: str,
        *,
        content: str,
        description: str | None,
        is_active: bool,
    ) -> TenantTemplate:
        """Create or update a template override.

        Flushes so the caller can serialise the returned row; does not commit.
        The caller owns the transaction boundary.
        """
        template = await self._repo.find_template(db, tenant_id, template_name)
        if template is not None:
            template.content = content
            template.description = description
            template.is_active = is_active
            await db.flush()
            return template

        template = TenantTemplate(
            tenant_id=tenant_id,
            template_name=template_name,
            content=content,
            description=description,
            is_active=is_active,
        )
        await self._repo.add(db, template)
        return template

    async def toggle_template(
        self,
        db: AsyncSession,
        template: TenantTemplate,
    ) -> TenantTemplate:
        """Flip ``is_active`` on a template override and flush."""
        template.is_active = not template.is_active
        await db.flush()
        return template

    async def delete_template(
        self,
        db: AsyncSession,
        template: TenantTemplate,
    ) -> None:
        """Stage a template-override deletion (caller owns the commit)."""
        await self._repo.delete(db, template)

    # ------------------------------------------------------------------
    # Rich eager-loaded reads
    # ------------------------------------------------------------------

    async def get_by_id_with_all_relations(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Tenant | None:
        """Fetch a tenant with members, IdPs, branding, templates and roles."""
        return await self._repo.find_by_id_with_all_relations(db, tenant_id)

    async def get_idp_scoped_with_federated(
        self,
        db: AsyncSession,
        idp_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> IdentityProvider | None:
        """Fetch an IdP scoped to ``tenant_id`` with federated identities."""
        return await self._repo.find_idp_scoped_with_federated(db, idp_id, tenant_id)

    async def get_member_in_tenant(
        self,
        db: AsyncSession,
        member_id: uuid.UUID,
        tenant_id: uuid.UUID,
        *,
        eager_role: bool = True,
    ) -> TenantMember | None:
        """Fetch a membership by PK scoped to ``tenant_id``."""
        return await self._repo.find_member_in_tenant(
            db, member_id, tenant_id, eager_role=eager_role
        )


# Singleton instance
tenant_service = TenantService()
