# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Collection model - groups of documents with polymorphic ownership."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from knowledge.models.base import Base
from knowledge.models.enums import OwnerType

if TYPE_CHECKING:
    from knowledge.models.collection_collaborator import CollectionCollaborator
    from knowledge.models.collection_invitation import CollectionInvitation
    from knowledge.models.document import Document
    from knowledge.models.organization import Organization


class Collection(Base):
    """Collection model - a group of documents with polymorphic ownership.

    Collections can be owned by either:
    - A user (personal collection): owner_type='user', owner_id=user_id
    - An organization (shared collection): owner_type='organization', owner_id=org_id

    For backward compatibility, organization collections also have organization_id set.
    """

    __tablename__ = "collections"
    __table_args__ = (
        # New unique constraint for polymorphic ownership
        UniqueConstraint("owner_type", "owner_id", "slug", name="uq_collection_owner_slug"),
        # Index for efficient owner lookups
        Index("ix_collections_owner", "owner_type", "owner_id"),
        # Keep legacy constraint for backward compat (will be dropped in future migration)
        # UniqueConstraint("tenant_id", "slug", name="uq_collection_tenant_slug"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # Polymorphic ownership
    owner_type: Mapped[OwnerType] = mapped_column(
        Enum(
            OwnerType,
            name="ownertype",
            values_callable=lambda x: [e.value for e in x],
            create_type=False,
        ),
        nullable=False,
        default=OwnerType.USER,
    )
    owner_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
    )

    # Legacy organization reference (nullable for personal collections)
    # This is kept for backward compatibility and will be removed in future
    organization_id: Mapped[UUID | None] = mapped_column(
        "tenant_id",  # Keep column name for backward compat
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    embedding_model: Mapped[str] = mapped_column(
        String(100),
        default="text-embedding-3-small",
        nullable=False,
    )
    dimension: Mapped[int] = mapped_column(Integer, default=1536, nullable=False)
    metadata_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    document_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
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
    organization: Mapped["Organization | None"] = relationship(
        "Organization",
        back_populates="collections",
        foreign_keys=[organization_id],
    )
    documents: Mapped[list["Document"]] = relationship(
        "Document",
        back_populates="collection",
        cascade="all, delete-orphan",
    )
    collaborators: Mapped[list["CollectionCollaborator"]] = relationship(
        "CollectionCollaborator",
        back_populates="collection",
        cascade="all, delete-orphan",
    )
    collection_invitations: Mapped[list["CollectionInvitation"]] = relationship(
        "CollectionInvitation",
        back_populates="collection",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Collection {self.slug} ({self.owner_type.value}:{self.owner_id})>"

    @property
    def is_personal(self) -> bool:
        """Check if this is a personal collection (owned by a user)."""
        return self.owner_type == OwnerType.USER

    @property
    def is_organization_owned(self) -> bool:
        """Check if this belongs to an organization."""
        return self.owner_type == OwnerType.ORGANIZATION

    # Backward compatibility aliases
    @property
    def tenant(self) -> "Organization | None":
        """Alias for organization (backward compatibility)."""
        return self.organization

    @property
    def tenant_id(self) -> UUID | None:
        """Alias for organization_id (backward compatibility)."""
        return self.organization_id
