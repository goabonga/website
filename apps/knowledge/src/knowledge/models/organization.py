# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Organization model - represents a team/company workspace (Enterprise plan)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from knowledge.models.base import Base
from knowledge.models.enums import CustomDomainStatus, PlanType

if TYPE_CHECKING:
    from knowledge.models.collection import Collection
    from knowledge.models.organization_invitation import OrganizationInvitation
    from knowledge.models.organization_member import OrganizationMember


class Organization(Base):
    """Organization model - a shared workspace for teams.

    Organizations are only available for Enterprise plan users.
    They allow multiple users to collaborate on shared collections.

    Note: This was previously called 'Tenant'. The table name remains
    'tenants' for backward compatibility during migration.
    """

    __tablename__ = "tenants"  # Keep table name for backward compat

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    plan: Mapped[PlanType] = mapped_column(
        Enum(
            PlanType,
            name="plantype",
            values_callable=lambda x: [e.value for e in x],
            create_type=False,
        ),
        default=PlanType.ENTERPRISE,  # Organizations are Enterprise only
        nullable=False,
    )
    settings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Custom domain fields (Enterprise plan only)
    custom_domain: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )
    custom_domain_status: Mapped[CustomDomainStatus | None] = mapped_column(
        Enum(
            CustomDomainStatus,
            name="customdomainstatus",
            values_callable=lambda x: [e.value for e in x],
            create_type=False,
        ),
        nullable=True,
        index=True,
    )
    custom_domain_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    custom_domain_ssl_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    custom_domain_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    custom_domain_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Id of the domain in the custom-domain service, and the CNAME it asks the customer for
    custom_domain_service_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True, index=True
    )
    custom_domain_cname_target: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    collections: Mapped[list[Collection]] = relationship(
        "Collection",
        back_populates="organization",
        cascade="all, delete-orphan",
        foreign_keys="Collection.organization_id",
    )
    members: Mapped[list[OrganizationMember]] = relationship(
        "OrganizationMember",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    invitations: Mapped[list[OrganizationInvitation]] = relationship(
        "OrganizationInvitation",
        back_populates="organization",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Organization {self.slug}>"

    @property
    def allow_member_create_collections(self) -> bool:
        """Check if members can create collections in this organization."""
        return self.settings.get("allow_member_create_collections", True)

    @allow_member_create_collections.setter
    def allow_member_create_collections(self, value: bool) -> None:
        """Set whether members can create collections."""
        self.settings = {**self.settings, "allow_member_create_collections": value}

    @property
    def is_enterprise(self) -> bool:
        """Check if organization has enterprise plan."""
        return self.plan == PlanType.ENTERPRISE

    @property
    def can_use_custom_domain(self) -> bool:
        """Check if organization can use custom domain feature."""
        return self.is_enterprise

    @property
    def custom_domain_is_active(self) -> bool:
        """Check if custom domain is fully provisioned and active."""
        return (
            self.custom_domain is not None
            and self.custom_domain_status == CustomDomainStatus.ACTIVE
        )


# Backward compatibility alias
Tenant = Organization
