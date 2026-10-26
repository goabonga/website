# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Collection collaborator model for per-collection sharing."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from knowledge.models.base import Base
from knowledge.models.enums import CollaboratorPermission

if TYPE_CHECKING:
    from knowledge.models.collection import Collection


class CollectionCollaborator(Base):
    """Collaborator access to a specific collection.

    This allows users to share their personal collections with others,
    giving them read, write, or admin access.
    """

    __tablename__ = "collection_collaborators"
    __table_args__ = (
        UniqueConstraint("collection_id", "user_id", name="uq_collection_collaborator"),
    )

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
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
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
    invited_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
    )
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
    collection: Mapped[Collection] = relationship(
        "Collection",
        back_populates="collaborators",
    )

    def __repr__(self) -> str:
        return f"<CollectionCollaborator {self.user_id} on {self.collection_id} ({self.permission.value})>"

    @property
    def can_read(self) -> bool:
        """Check if collaborator can read."""
        return True  # All permissions include read

    @property
    def can_write(self) -> bool:
        """Check if collaborator can write."""
        return self.permission in (
            CollaboratorPermission.WRITE,
            CollaboratorPermission.ADMIN,
        )

    @property
    def can_admin(self) -> bool:
        """Check if collaborator has admin access."""
        return self.permission == CollaboratorPermission.ADMIN

    @property
    def can_invite(self) -> bool:
        """Check if collaborator can invite others."""
        return self.can_admin
