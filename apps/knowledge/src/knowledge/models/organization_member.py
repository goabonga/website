# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Organization membership model for multi-tenant access control."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from knowledge.models.base import Base
from knowledge.models.enums import OrganizationMemberRole

if TYPE_CHECKING:
    from knowledge.models.organization import Organization


class OrganizationMember(Base):
    """Membership linking users to organizations with roles.

    Note: Table name remains 'tenant_members' for backward compatibility.
    """

    __tablename__ = "tenant_members"  # Keep table name for backward compat

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    # Column named tenant_id for backward compat, represents organization_id
    organization_id: Mapped[UUID] = mapped_column(
        "tenant_id",  # Keep column name for backward compat
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    # Cached user display info (updated on login/join)
    display_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    role: Mapped[OrganizationMemberRole] = mapped_column(
        Enum(
            OrganizationMemberRole,
            name="tenantmemberrole",  # Keep enum name for backward compat
            values_callable=lambda x: [e.value for e in x],
            create_type=False,  # Don't try to create the type, it already exists
        ),
        nullable=False,
        default=OrganizationMemberRole.MEMBER,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Unique constraint: one membership per user per organization
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_tenant_member"),)

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="members",
    )

    def __repr__(self) -> str:
        return f"<OrganizationMember {self.user_id} in {self.organization_id} as {self.role.value}>"

    @property
    def is_owner(self) -> bool:
        """Check if this member is the organization owner."""
        return self.role == OrganizationMemberRole.OWNER

    @property
    def is_admin(self) -> bool:
        """Check if this member has admin privileges (owner or admin)."""
        return self.role in (OrganizationMemberRole.OWNER, OrganizationMemberRole.ADMIN)

    @property
    def can_manage_members(self) -> bool:
        """Check if this member can invite/remove other members."""
        return self.is_admin

    @property
    def can_manage_organization(self) -> bool:
        """Check if this member can update organization settings."""
        return self.is_admin

    @property
    def can_delete_organization(self) -> bool:
        """Check if this member can delete the organization."""
        return self.is_owner

    @property
    def can_create_collections(self) -> bool:
        """Check if this member can create collections in the organization.

        Admins and owners can always create collections.
        Regular members can create if organization settings allow it.
        """
        if self.is_admin:
            return True
        # Need to check organization settings - handled at service level
        return True  # Default to True, actual check in service


# Backward compatibility alias
TenantMember = OrganizationMember
TenantMemberRole = OrganizationMemberRole
