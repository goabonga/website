# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Authorized client model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from custom_domain.models.base import Base

if TYPE_CHECKING:
    from custom_domain.models.template import NginxTemplate


class AuthorizedClient(Base):
    """OAuth2 client authorized to create custom domains."""

    __tablename__ = "authorized_clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Default configuration (optional - can be provided per-domain)
    default_upstream_target: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Default upstream socket or URL",
    )
    default_cname_target: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Default CNAME target",
    )

    # Default nginx template for this client
    default_nginx_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("nginx_templates.id"),
        nullable=True,
    )

    # Limits
    max_domains: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Domain limit (null = unlimited)",
    )

    # State
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

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
    default_nginx_template: Mapped["NginxTemplate | None"] = relationship(
        "NginxTemplate",
    )

    def __repr__(self) -> str:
        return f"<AuthorizedClient(id={self.id}, client_id='{self.client_id}')>"
