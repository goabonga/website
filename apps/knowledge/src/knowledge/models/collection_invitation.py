# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Collection invitation model for per-collection invites."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from knowledge.models.base import Base
from knowledge.models.enums import CollaboratorPermission, InvitationStatus

if TYPE_CHECKING:
    from knowledge.models.collection import Collection


class CollectionInvitation(Base):
    """Invitation to collaborate on a specific collection.

    This allows collection owners/admins to invite users by email
    to become collaborators on a collection.
    """

    __tablename__ = "collection_invitations"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    collection_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("collections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    permission: Mapped[CollaboratorPermission] = mapped_column(
        Enum(
            CollaboratorPermission,
            name="collaboratorpermission",
            values_callable=lambda x: [e.value for e in x],
            create_type=False,
        ),
        nullable=False,
        default=CollaboratorPermission.READ,
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
            name="invitationstatus",
            values_callable=lambda x: [e.value for e in x],
            create_type=False,
        ),
        nullable=False,
        default=InvitationStatus.PENDING,
    )
    invited_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
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
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    collection: Mapped[Collection] = relationship(
        "Collection",
        back_populates="collection_invitations",
    )

    def __repr__(self) -> str:
        return f"<CollectionInvitation {self.email} to {self.collection_id} ({self.status.value})>"

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
        if self.status != InvitationStatus.PENDING:
            return False
        return not self.expires_at < datetime.now(UTC)

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
