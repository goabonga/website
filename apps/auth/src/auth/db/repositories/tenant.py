# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""TenantRepository — SQL access for Tenant, TenantMember, IdP and TenantTemplate rows."""

from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth.db.models.tenant import (
    IdentityProvider,
    Tenant,
    TenantBranding,
    TenantCustomRole,
    TenantMember,
    TenantTemplate,
)
from auth.db.models.user import User, UserEmail


class TenantRepository:
    """Data access for Tenant, TenantMember, IdentityProvider and TenantTemplate rows.

    Encapsulates every SQL query touching the ``tenants``, ``tenant_members``,
    ``identity_providers`` and ``tenant_templates`` tables. Methods return
    SQLAlchemy model instances and never commit — the caller owns the
    transaction boundary.

    Branding and webhooks are intentionally out of scope and handled by their
    own future repositories.
    """

    # ------------------------------------------------------------------
    # Tenant reads
    # ------------------------------------------------------------------

    async def find_by_id(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Tenant | None:
        """Fetch a tenant by ID."""
        result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
        return result.scalar_one_or_none()

    async def find_active_by_id(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Tenant | None:
        """Fetch an active tenant by ID."""
        result = await db.execute(
            select(Tenant).where(Tenant.id == tenant_id, Tenant.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    async def find_by_slug(
        self,
        db: AsyncSession,
        slug: str,
    ) -> Tenant | None:
        """Fetch a tenant by slug."""
        result = await db.execute(select(Tenant).where(Tenant.slug == slug))
        return result.scalar_one_or_none()

    async def find_by_custom_domain(
        self,
        db: AsyncSession,
        domain: str,
    ) -> Tenant | None:
        """Fetch the tenant that holds ``domain`` as its custom domain (case-insensitive)."""
        result = await db.execute(
            select(Tenant).where(func.lower(Tenant.custom_domain) == domain.lower())
        )
        return result.scalar_one_or_none()

    async def find_id_by_active_slug(
        self,
        db: AsyncSession,
        slug: str,
    ) -> str | None:
        """Return the active tenant's ID (as string) matching ``slug``.

        Used by the tenant-resolution middleware which only needs the ID.
        Returns ``None`` when no active tenant matches.
        """
        result = await db.execute(
            select(Tenant.id).where(
                Tenant.slug == slug,
                Tenant.is_active.is_(True),
            )
        )
        row = result.first()
        if row is None:
            return None
        return str(row.id)

    async def find_id_slug_by_active_custom_domain(
        self,
        db: AsyncSession,
        host: str,
    ) -> tuple[str, str] | None:
        """Return ``(id, slug)`` for the active tenant bound to ``host``.

        Used by the tenant-resolution middleware for CNAME-based lookups.
        """
        result = await db.execute(
            select(Tenant.id, Tenant.slug).where(
                Tenant.custom_domain == host,
                Tenant.is_active.is_(True),
            )
        )
        row = result.first()
        if row is None:
            return None
        return str(row.id), row.slug

    async def find_platform_id_slug(
        self,
        db: AsyncSession,
    ) -> tuple[str, str] | None:
        """Return ``(id, slug)`` for the active platform tenant (if any)."""
        result = await db.execute(
            select(Tenant.id, Tenant.slug).where(
                Tenant.is_platform.is_(True),
                Tenant.is_active.is_(True),
            )
        )
        row = result.first()
        if row is None:
            return None
        return str(row.id), row.slug

    async def find_display_name(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> str | None:
        """Fetch a tenant's ``display_name`` by ID (single-column lookup)."""
        result = await db.execute(select(Tenant.display_name).where(Tenant.id == tenant_id))
        return result.scalar_one_or_none()

    async def find_settings_by_id(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> dict | None:
        """Fetch a tenant's ``settings`` JSON blob by ID (single-column lookup)."""
        result = await db.execute(select(Tenant.settings).where(Tenant.id == tenant_id))
        return result.scalar_one_or_none()

    async def list_id_name_pairs(
        self,
        db: AsyncSession,
        *,
        ids: list[uuid.UUID] | set[uuid.UUID] | None = None,
    ) -> list[tuple[uuid.UUID, str]]:
        """List ``(id, display_name)`` pairs for dropdowns/lookups.

        When ``ids`` is ``None`` return every tenant ordered by
        ``display_name``. When provided, restrict to the given IDs
        (no ordering guarantee).
        """
        if ids is not None:
            if not ids:
                return []
            query = select(Tenant.id, Tenant.display_name).where(Tenant.id.in_(list(ids)))
        else:
            query = select(Tenant.id, Tenant.display_name).order_by(Tenant.display_name)
        result = await db.execute(query)
        return [(row[0], row[1]) for row in result.all()]

    async def list_active_dropdown(
        self,
        db: AsyncSession,
    ) -> list[tuple[uuid.UUID, str, str]]:
        """List active tenants as ``(id, display_name, slug)`` rows.

        Intended for admin dropdown/filter UIs that need lightweight
        identifiers sorted by ``display_name``.
        """
        result = await db.execute(
            select(Tenant.id, Tenant.display_name, Tenant.slug)
            .where(Tenant.is_active.is_(True))
            .order_by(Tenant.display_name)
        )
        return [(row[0], row[1], row[2]) for row in result.all()]

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
        """List tenants with filters and pagination.

        Returns a ``(tenants, total)`` tuple. Tenants are ordered by
        ``created_at`` descending. Filters are ANDed together.

        Args:
            db: Database session.
            page: 1-indexed page number.
            page_size: Items per page.
            search: Case-insensitive substring match on slug, display_name
                or custom_domain.
            is_active: Filter on ``Tenant.is_active``.
            eager_members: Eager-load the ``members`` relation.
            eager_idps: Eager-load the ``identity_providers`` relation.
        """
        offset = (page - 1) * page_size

        query = select(Tenant)
        options = []
        if eager_members:
            options.append(selectinload(Tenant.members))
        if eager_idps:
            options.append(selectinload(Tenant.identity_providers))
        if options:
            query = query.options(*options)

        count_query = select(func.count()).select_from(Tenant)

        if is_active is not None:
            query = query.where(Tenant.is_active == is_active)
            count_query = count_query.where(Tenant.is_active == is_active)

        if search:
            pattern = f"%{search}%"
            condition = or_(
                Tenant.slug.ilike(pattern),
                Tenant.display_name.ilike(pattern),
                Tenant.custom_domain.ilike(pattern),
            )
            query = query.where(condition)
            count_query = count_query.where(condition)

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(Tenant.created_at.desc()).offset(offset).limit(page_size)
        result = await db.execute(query)
        tenants = list(result.scalars().all())

        return tenants, total

    # ------------------------------------------------------------------
    # Member reads
    # ------------------------------------------------------------------

    async def list_members(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        page: int | None = None,
        page_size: int | None = None,
        eager_role: bool = True,
    ) -> list[TenantMember]:
        """List members of a tenant ordered by ``created_at`` desc.

        When both ``page`` and ``page_size`` are provided, apply offset/limit;
        otherwise return every member.
        """
        query = select(TenantMember).where(TenantMember.tenant_id == tenant_id)
        if eager_role:
            query = query.options(selectinload(TenantMember.custom_role))
        query = query.order_by(TenantMember.created_at.desc())

        if page is not None and page_size is not None:
            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)

        result = await db.execute(query)
        return list(result.scalars().all())

    async def count_members(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> int:
        """Count members of a tenant."""
        result = await db.execute(
            select(func.count())
            .select_from(TenantMember)
            .where(TenantMember.tenant_id == tenant_id)
        )
        return result.scalar() or 0

    async def find_member(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        eager_role: bool = True,
    ) -> TenantMember | None:
        """Fetch a membership by (tenant_id, user_id)."""
        query = select(TenantMember).where(
            TenantMember.tenant_id == tenant_id,
            TenantMember.user_id == user_id,
        )
        if eager_role:
            query = query.options(selectinload(TenantMember.custom_role))
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def find_member_by_id(
        self,
        db: AsyncSession,
        member_id: uuid.UUID,
        *,
        eager_role: bool = False,
    ) -> TenantMember | None:
        """Fetch a membership by primary key."""
        query = select(TenantMember).where(TenantMember.id == member_id)
        if eager_role:
            query = query.options(selectinload(TenantMember.custom_role))
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def list_user_memberships(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> list[TenantMember]:
        """List all memberships for a user, with tenant + role eager-loaded."""
        result = await db.execute(
            select(TenantMember)
            .options(
                selectinload(TenantMember.tenant),
                selectinload(TenantMember.custom_role),
            )
            .where(TenantMember.user_id == user_id)
        )
        return list(result.scalars().all())

    async def list_user_memberships_with_idps(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> list[TenantMember]:
        """List memberships with tenant (+idps) and custom role eager-loaded.

        Ordered by ``created_at`` descending so the most recently joined
        organisation appears first.
        """
        result = await db.execute(
            select(TenantMember)
            .options(
                selectinload(TenantMember.tenant).selectinload(Tenant.identity_providers),
                selectinload(TenantMember.custom_role),
            )
            .where(TenantMember.user_id == user_id)
            .order_by(TenantMember.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_user_memberships_with_custom_role(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> list[TenantMember]:
        """List memberships for a user with ``custom_role`` eager-loaded only."""
        result = await db.execute(
            select(TenantMember)
            .options(selectinload(TenantMember.custom_role))
            .where(TenantMember.user_id == user_id)
        )
        return list(result.scalars().all())

    async def find_by_id_with_all_relations(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Tenant | None:
        """Fetch a tenant with members, IdPs, branding, templates and roles.

        Eager-loads ``members → user → profile``, ``members → custom_role``,
        ``identity_providers → federated_identities``, ``branding``,
        ``templates`` and ``roles`` so admin pages can render the full object
        graph in a single query.
        """
        result = await db.execute(
            select(Tenant)
            .options(
                selectinload(Tenant.members)
                .selectinload(TenantMember.user)
                .selectinload(User.profile),
                selectinload(Tenant.members).selectinload(TenantMember.custom_role),
                selectinload(Tenant.identity_providers).selectinload(
                    IdentityProvider.federated_identities
                ),
                selectinload(Tenant.branding),
                selectinload(Tenant.templates),
                selectinload(Tenant.roles),
            )
            .where(Tenant.id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def find_idp_scoped_with_federated(
        self,
        db: AsyncSession,
        idp_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> IdentityProvider | None:
        """Fetch an IdP scoped to ``tenant_id`` with ``federated_identities`` loaded."""
        result = await db.execute(
            select(IdentityProvider)
            .options(selectinload(IdentityProvider.federated_identities))
            .where(
                IdentityProvider.id == idp_id,
                IdentityProvider.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def find_member_in_tenant(
        self,
        db: AsyncSession,
        member_id: uuid.UUID,
        tenant_id: uuid.UUID,
        *,
        eager_role: bool = True,
    ) -> TenantMember | None:
        """Fetch a membership by PK scoped to ``tenant_id``.

        When ``eager_role`` is True (default), eager-loads the
        ``custom_role`` relation so callers can read the role name/scopes.
        """
        query = select(TenantMember).where(
            TenantMember.id == member_id,
            TenantMember.tenant_id == tenant_id,
        )
        if eager_role:
            query = query.options(selectinload(TenantMember.custom_role))
        result = await db.execute(query)
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # IdP reads
    # ------------------------------------------------------------------

    async def list_idps(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        page: int | None = None,
        page_size: int | None = None,
    ) -> list[IdentityProvider]:
        """List identity providers for a tenant.

        Ordered by ``display_order`` then ``created_at`` desc. When both
        ``page`` and ``page_size`` are provided, apply offset/limit.
        """
        query = (
            select(IdentityProvider)
            .where(IdentityProvider.tenant_id == tenant_id)
            .order_by(IdentityProvider.display_order, IdentityProvider.created_at.desc())
        )
        if page is not None and page_size is not None:
            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)

        result = await db.execute(query)
        return list(result.scalars().all())

    async def count_idps(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> int:
        """Count identity providers for a tenant."""
        result = await db.execute(
            select(func.count())
            .select_from(IdentityProvider)
            .where(IdentityProvider.tenant_id == tenant_id)
        )
        return result.scalar() or 0

    async def find_idp(
        self,
        db: AsyncSession,
        idp_id: uuid.UUID,
    ) -> IdentityProvider | None:
        """Fetch an identity provider by ID."""
        result = await db.execute(select(IdentityProvider).where(IdentityProvider.id == idp_id))
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Template reads
    # ------------------------------------------------------------------

    async def list_templates(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> list[TenantTemplate]:
        """List every template override for a tenant ordered by template name."""
        result = await db.execute(
            select(TenantTemplate)
            .where(TenantTemplate.tenant_id == tenant_id)
            .order_by(TenantTemplate.template_name)
        )
        return list(result.scalars().all())

    async def find_template(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        template_name: str,
    ) -> TenantTemplate | None:
        """Fetch a template override by (tenant_id, template_name)."""
        result = await db.execute(
            select(TenantTemplate).where(
                TenantTemplate.tenant_id == tenant_id,
                TenantTemplate.template_name == template_name,
            )
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Eager-loaded reads (for admin HTML pages)
    # ------------------------------------------------------------------

    async def find_by_id_with_detail(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Tenant | None:
        """Fetch a tenant with members (user+profile+custom_role), IdPs with
        federated identities, and custom roles eager-loaded.

        Intended for admin detail pages that need the full object graph.
        """
        result = await db.execute(
            select(Tenant)
            .options(
                selectinload(Tenant.members)
                .selectinload(TenantMember.user)
                .selectinload(User.profile),
                selectinload(Tenant.members).selectinload(TenantMember.custom_role),
                selectinload(Tenant.identity_providers).selectinload(
                    IdentityProvider.federated_identities
                ),
                selectinload(Tenant.roles),
            )
            .where(Tenant.id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def find_by_slug_with_detail(
        self,
        db: AsyncSession,
        slug: str,
    ) -> Tenant | None:
        """Slug counterpart of :meth:`find_by_id_with_detail`."""
        result = await db.execute(
            select(Tenant)
            .options(
                selectinload(Tenant.members)
                .selectinload(TenantMember.user)
                .selectinload(User.profile),
                selectinload(Tenant.members).selectinload(TenantMember.custom_role),
                selectinload(Tenant.identity_providers).selectinload(
                    IdentityProvider.federated_identities
                ),
                selectinload(Tenant.roles),
            )
            .where(Tenant.slug == slug)
        )
        return result.scalar_one_or_none()

    async def find_by_id_with_branding(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Tenant | None:
        """Fetch a tenant with its ``branding`` relation eager-loaded."""
        result = await db.execute(
            select(Tenant).options(selectinload(Tenant.branding)).where(Tenant.id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def find_by_slug_with_branding(
        self,
        db: AsyncSession,
        slug: str,
    ) -> Tenant | None:
        """Slug counterpart of :meth:`find_by_id_with_branding`."""
        result = await db.execute(
            select(Tenant).options(selectinload(Tenant.branding)).where(Tenant.slug == slug)
        )
        return result.scalar_one_or_none()

    async def find_by_id_with_templates(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Tenant | None:
        """Fetch a tenant with its ``templates`` relation eager-loaded."""
        result = await db.execute(
            select(Tenant).options(selectinload(Tenant.templates)).where(Tenant.id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def find_by_slug_with_templates(
        self,
        db: AsyncSession,
        slug: str,
    ) -> Tenant | None:
        """Slug counterpart of :meth:`find_by_id_with_templates`."""
        result = await db.execute(
            select(Tenant).options(selectinload(Tenant.templates)).where(Tenant.slug == slug)
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Scoped IdP reads
    # ------------------------------------------------------------------

    async def find_idp_scoped(
        self,
        db: AsyncSession,
        idp_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> IdentityProvider | None:
        """Fetch an identity provider by ID scoped to ``tenant_id``."""
        result = await db.execute(
            select(IdentityProvider).where(
                IdentityProvider.id == idp_id,
                IdentityProvider.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Branding reads
    # ------------------------------------------------------------------

    async def find_branding(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> TenantBranding | None:
        """Fetch the ``TenantBranding`` row for ``tenant_id`` (or ``None``)."""
        result = await db.execute(
            select(TenantBranding).where(TenantBranding.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Custom role reads (scoped to tenant)
    # ------------------------------------------------------------------

    async def find_custom_role_by_name(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        name: str,
    ) -> TenantCustomRole | None:
        """Fetch a custom role by (tenant_id, name)."""
        result = await db.execute(
            select(TenantCustomRole).where(
                TenantCustomRole.tenant_id == tenant_id,
                TenantCustomRole.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def find_custom_role_scoped(
        self,
        db: AsyncSession,
        role_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> TenantCustomRole | None:
        """Fetch a custom role by ID scoped to ``tenant_id``."""
        result = await db.execute(
            select(TenantCustomRole).where(
                TenantCustomRole.id == role_id,
                TenantCustomRole.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def count_members_for_role(
        self,
        db: AsyncSession,
        role_id: uuid.UUID,
    ) -> int:
        """Count members assigned to ``role_id``."""
        result = await db.execute(
            select(func.count(TenantMember.id)).where(TenantMember.role_id == role_id)
        )
        return result.scalar() or 0

    # ------------------------------------------------------------------
    # Member reads (by-id, scoped helpers)
    # ------------------------------------------------------------------

    async def existing_membership(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> TenantMember | None:
        """Return the membership row for (tenant_id, user_id) if any."""
        result = await db.execute(
            select(TenantMember).where(
                TenantMember.tenant_id == tenant_id,
                TenantMember.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # User email reads (used by admin member flows)
    # ------------------------------------------------------------------

    async def find_user_email_row(
        self,
        db: AsyncSession,
        email: str,
    ) -> UserEmail | None:
        """Fetch a :class:`UserEmail` row by ``email`` (exact match)."""
        result = await db.execute(select(UserEmail).where(UserEmail.email == email))
        return result.scalar_one_or_none()

    async def find_primary_email_for_user(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> str | None:
        """Return the primary email for ``user_id`` (or None)."""
        result = await db.execute(
            select(UserEmail.email).where(
                UserEmail.user_id == user_id, UserEmail.is_primary.is_(True)
            )
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def add(self, db: AsyncSession, instance: object) -> None:
        """Stage a new row and flush so generated columns (id) are populated."""
        db.add(instance)
        await db.flush()

    async def delete(self, db: AsyncSession, instance: object) -> None:
        """Stage a row deletion (no commit)."""
        await db.delete(instance)

    async def add_member(
        self,
        db: AsyncSession,
        member: TenantMember,
    ) -> TenantMember:
        """Stage a new :class:`TenantMember` row (no flush — caller owns commit).

        Kept separate from :meth:`add` so callers that only need to attach a
        row to an already-flushed tenant don't pay for an extra ``flush()``.
        """
        db.add(member)
        return member

    async def add_branding(
        self,
        db: AsyncSession,
        branding: TenantBranding,
    ) -> TenantBranding:
        """Stage a new :class:`TenantBranding` row (no flush — attached to tenant)."""
        db.add(branding)
        return branding
