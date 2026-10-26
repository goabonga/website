# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""FederationRepository — SQL access for identity-provider federation rows."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth.db.models.tenant import (
    FederatedIdentity,
    IdentityProvider,
    Tenant,
    TenantMember,
)
from auth.db.models.user import User, UserEmail


class FederationRepository:
    """Data access for federation tables.

    Encapsulates every SQL query touching ``identity_providers`` and
    ``federated_identities``. Methods return SQLAlchemy model instances
    and never commit — the caller owns the transaction boundary.
    """

    # ------------------------------------------------------------------
    # IdentityProvider reads
    # ------------------------------------------------------------------

    async def list_idps_for_tenant_slug(
        self,
        db: AsyncSession,
        tenant_slug: str,
    ) -> list[IdentityProvider]:
        """List active identity providers for an active tenant, ordered for display."""
        result = await db.execute(
            select(IdentityProvider)
            .join(Tenant)
            .where(
                Tenant.slug == tenant_slug,
                Tenant.is_active.is_(True),
                IdentityProvider.is_active.is_(True),
            )
            .order_by(IdentityProvider.display_order, IdentityProvider.name)
        )
        return list(result.scalars().all())

    async def find_idp_by_id(
        self,
        db: AsyncSession,
        idp_id: str | uuid.UUID,
    ) -> IdentityProvider | None:
        """Fetch a single identity provider by ID."""
        result = await db.execute(select(IdentityProvider).where(IdentityProvider.id == idp_id))
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # FederatedIdentity reads
    # ------------------------------------------------------------------

    async def list_identities_for_user(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> list[FederatedIdentity]:
        """Return a user's federated identities with IdP and tenant eager-loaded."""
        result = await db.execute(
            select(FederatedIdentity)
            .options(
                selectinload(FederatedIdentity.identity_provider).selectinload(
                    IdentityProvider.tenant
                )
            )
            .where(FederatedIdentity.user_id == user_id)
        )
        return list(result.scalars().all())

    async def list_identities_for_user_in_tenant(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> list[FederatedIdentity]:
        """List a user's federated identities whose IdP belongs to ``tenant_id``."""
        result = await db.execute(
            select(FederatedIdentity)
            .join(IdentityProvider)
            .where(
                FederatedIdentity.user_id == user_id,
                IdentityProvider.tenant_id == tenant_id,
            )
        )
        return list(result.scalars().all())

    async def find_federated_identity(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        idp_id: uuid.UUID,
    ) -> FederatedIdentity | None:
        """Fetch a single federated identity by ``(user_id, idp_id)`` pair."""
        result = await db.execute(
            select(FederatedIdentity).where(
                FederatedIdentity.identity_provider_id == idp_id,
                FederatedIdentity.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def find_identity_by_subject(
        self,
        db: AsyncSession,
        idp_id: uuid.UUID,
        external_subject: str,
    ) -> FederatedIdentity | None:
        """Look up a federated identity by ``(identity_provider_id, external_subject)``."""
        result = await db.execute(
            select(FederatedIdentity).where(
                FederatedIdentity.identity_provider_id == idp_id,
                FederatedIdentity.external_subject == external_subject,
            )
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Cross-table helpers used by find_or_create_user
    # ------------------------------------------------------------------

    async def find_user_by_id(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> User | None:
        """Fetch a user by ID (no eager-loading)."""
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def find_user_by_email(
        self,
        db: AsyncSession,
        email: str,
    ) -> User | None:
        """Fetch a user by one of its email addresses (case-insensitive)."""
        result = await db.execute(
            select(User).join(UserEmail).where(UserEmail.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def find_tenant_by_slug(
        self,
        db: AsyncSession,
        tenant_slug: str,
    ) -> Tenant | None:
        """Fetch a tenant by slug."""
        result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
        return result.scalar_one_or_none()

    async def find_tenant_membership(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> TenantMember | None:
        """Fetch a ``(tenant_id, user_id)`` membership row if it exists."""
        result = await db.execute(
            select(TenantMember).where(
                TenantMember.tenant_id == tenant_id,
                TenantMember.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def add(self, db: AsyncSession, federated_identity: FederatedIdentity) -> None:
        """Stage a new :class:`FederatedIdentity` row."""
        db.add(federated_identity)

    async def delete(self, db: AsyncSession, federated_identity: FederatedIdentity) -> None:
        """Stage a :class:`FederatedIdentity` deletion (no commit)."""
        await db.delete(federated_identity)
