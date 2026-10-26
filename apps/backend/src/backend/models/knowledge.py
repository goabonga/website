# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Knowledge base model for RAG with pgvector."""

from datetime import datetime
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class KnowledgeEntryStatus(StrEnum):
    """Validation status of a knowledge entry."""

    PENDING = "pending"
    VALIDATING = "validating"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


class KnowledgeNamespace(Base):
    """Namespace/category for knowledge base entries.

    Namespaces allow organizing knowledge into categories with optional
    scope-based access control.
    """

    __tablename__ = "knowledge_namespaces"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    slug: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    required_scopes: Mapped[list[str] | None] = mapped_column(
        ARRAY(String),
        nullable=True,
        default=None,
    )
    is_public: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        default=dict,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationship to entries
    entries: Mapped[list["KnowledgeEntry"]] = relationship(
        "KnowledgeEntry",
        back_populates="namespace",
        lazy="selectin",
    )

    def is_accessible(self, user_scopes: set[str] | None) -> bool:
        """Check if namespace is accessible given user scopes.

        Args:
            user_scopes: User's scopes (None for anonymous users)

        Returns:
            True if namespace is accessible
        """
        # Public namespaces with no required scopes are always accessible
        if self.is_public and not self.required_scopes:
            return True
        # Non-public namespaces require authentication
        if not self.is_public and user_scopes is None:
            return False
        # If required_scopes is set, user must have ALL of them
        if self.required_scopes:
            if user_scopes is None:
                return False
            return set(self.required_scopes).issubset(user_scopes)
        return self.is_public


class KnowledgeEntry(Base):
    """Knowledge base entry for RAG semantic search."""

    __tablename__ = "knowledge_base"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    namespace_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("knowledge_namespaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    question: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    answer: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1536),
        nullable=True,
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        default=dict,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=KnowledgeEntryStatus.ACCEPTED.value,
        server_default=KnowledgeEntryStatus.ACCEPTED.value,
        index=True,
    )
    validation_details: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationship to namespace
    namespace: Mapped[KnowledgeNamespace | None] = relationship(
        "KnowledgeNamespace",
        back_populates="entries",
        lazy="joined",
    )

    __table_args__ = (Index("ix_knowledge_base_namespace_embedding", "namespace_id"),)
