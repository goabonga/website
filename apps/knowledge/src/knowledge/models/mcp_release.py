# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""MCP Release models for tracking Knowledge-MCP executable releases."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from knowledge.models.base import Base
from knowledge.models.enums import Platform, ReleaseStatus


class McpRelease(Base):
    """Represents a release of the Knowledge-MCP executable."""

    __tablename__ = "mcp_releases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
    )
    github_release_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        unique=True,
    )
    release_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    status: Mapped[ReleaseStatus] = mapped_column(
        Enum(
            ReleaseStatus,
            name="releasestatus",
            create_constraint=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=ReleaseStatus.PUBLISHED,
        index=True,
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    assets: Mapped[list[McpReleaseAsset]] = relationship(
        "McpReleaseAsset",
        back_populates="release",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (Index("ix_mcp_releases_status_published_at", "status", "published_at"),)

    def __repr__(self) -> str:
        return f"<McpRelease(version={self.version}, status={self.status})>"


class McpReleaseAsset(Base):
    """Represents a downloadable asset (binary) for a specific platform."""

    __tablename__ = "mcp_release_assets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    release_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mcp_releases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform: Mapped[Platform] = mapped_column(
        Enum(
            Platform,
            name="platform",
            create_constraint=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    download_url: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )
    file_size: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    sha256_checksum: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    download_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    release: Mapped[McpRelease] = relationship(
        "McpRelease",
        back_populates="assets",
    )

    __table_args__ = (
        Index("ix_mcp_release_assets_release_platform", "release_id", "platform", unique=True),
    )

    def __repr__(self) -> str:
        return f"<McpReleaseAsset(platform={self.platform}, filename={self.filename})>"
