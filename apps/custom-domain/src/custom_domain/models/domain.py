# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Custom domain model."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from custom_domain.models.base import Base
from custom_domain.models.enums import DomainStatus
from custom_domain.models.template import NginxTemplate


class CustomDomain(Base):
    """Custom domain configuration."""

    __tablename__ = "custom_domains"

    # Identity
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    domain: Mapped[str] = mapped_column(
        String(255),
        index=True,
        nullable=False,
    )

    # Soft delete - when set, domain is considered deleted
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    # Owner (OAuth2 client)
    client_id: Mapped[str] = mapped_column(
        String(255),
        index=True,
        nullable=False,
    )
    # Owner identifier (org_id, tenant_id, etc.)
    owner_id: Mapped[str] = mapped_column(
        String(255),
        index=True,
        nullable=False,
    )
    # Owner type for routing
    owner_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    # Upstream target (socket or URL)
    upstream_target: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    # State
    status: Mapped[DomainStatus] = mapped_column(
        Enum(
            DomainStatus,
            name="domainstatus",
            create_type=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=DomainStatus.PENDING,
        index=True,
    )

    # DNS configuration
    cname_target: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    dns_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    # SSL configuration
    ssl_provisioned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    ssl_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    # Errors
    error_message: Mapped[str | None] = mapped_column(Text)
    last_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    # Custom nginx template
    nginx_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("nginx_templates.id"),
        nullable=True,
    )

    # Metadata
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        default=dict,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    nginx_template: Mapped[NginxTemplate | None] = relationship(
        back_populates="domains",
    )

    __table_args__ = (
        Index("ix_custom_domains_client_owner", "client_id", "owner_id"),
        # Partial unique index - only enforces uniqueness on non-deleted domains
        Index(
            "ix_custom_domains_domain_unique",
            "domain",
            unique=True,
            postgresql_where=(deleted_at.is_(None)),
        ),
    )

    def __repr__(self) -> str:
        return f"<CustomDomain(id={self.id}, domain='{self.domain}', status={self.status})>"
