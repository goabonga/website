# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Organization invitation model for organization member invitations."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from knowledge.models.base import Base
from knowledge.models.enums import InvitationStatus, OrganizationMemberRole

if TYPE_CHECKING:
    from knowledge.models.organization import Organization


class OrganizationInvitation(Base):
    """Invitation to join an organization.

    Note: Table name remains 'invitations' for backward compatibility.
    """

    __tablename__ = "invitations"  # Keep table name for backward compat

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
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
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
    token: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    status: Mapped[InvitationStatus] = mapped_column(
        Enum(
            InvitationStatus,
            name="invitationstatus",  # Match existing enum name in DB
            values_callable=lambda x: [e.value for e in x],
            create_type=False,  # Don't try to create the type, it already exists
        ),
        nullable=False,
        default=InvitationStatus.PENDING,
    )
    invited_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    accepted_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="invitations",
    )

    def __repr__(self) -> str:
        return (
            f"<OrganizationInvitation {self.email} to {self.organization_id} ({self.status.value})>"
        )

    @classmethod
    def generate_token(cls) -> str:
        """Generate a secure random invitation token."""
        return secrets.token_urlsafe(32)

    @classmethod
    def default_expiry(cls) -> datetime:
        """Get default expiry time (7 days from now)."""
        return datetime.now(UTC) + timedelta(days=7)

    @property
    def is_pending(self) -> bool:
        """Check if invitation is still pending."""
        return self.status == InvitationStatus.PENDING

    @property
    def is_expired(self) -> bool:
        """Check if invitation has expired."""
        if self.status == InvitationStatus.EXPIRED:
            return True
        return self.expires_at < datetime.now(UTC)

    @property
    def is_valid(self) -> bool:
        """Check if invitation can be accepted."""
        return self.is_pending and not self.is_expired

    def accept(self, user_id: UUID) -> None:
        """Mark invitation as accepted."""
        self.status = InvitationStatus.ACCEPTED
        self.accepted_at = datetime.now(UTC)
        self.accepted_by = user_id

    def revoke(self) -> None:
        """Revoke the invitation."""
        self.status = InvitationStatus.REVOKED

    def mark_expired(self) -> None:
        """Mark invitation as expired."""
        self.status = InvitationStatus.EXPIRED


# Backward compatibility alias
Invitation = OrganizationInvitation
