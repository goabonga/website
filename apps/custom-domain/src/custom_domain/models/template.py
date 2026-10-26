# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Nginx template model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from custom_domain.models.base import Base

if TYPE_CHECKING:
    from custom_domain.models.domain import CustomDomain


class NginxTemplate(Base):
    """Nginx configuration template."""

    __tablename__ = "nginx_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Owner: the OAuth2 client allowed to use the template (NULL = shared by everyone)
    client_id: Mapped[str | None] = mapped_column(
        String(255),
        index=True,
        nullable=True,
        comment="Owning client; NULL for a shared template",
    )

    # Jinja2 templates
    http_template: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="HTTP-only template for ACME challenge",
    )
    https_template: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Full HTTPS template",
    )

    # Metadata
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Default template if none specified",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Available variables for documentation/validation
    available_variables: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
        comment="List of available Jinja2 variables",
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
    domains: Mapped[list["CustomDomain"]] = relationship(
        back_populates="nginx_template",
    )

    __table_args__ = (
        Index(
            "ix_nginx_templates_is_default",
            "is_default",
            postgresql_where=(is_default.is_(True)),
        ),
    )

    def __repr__(self) -> str:
        return f"<NginxTemplate(id={self.id}, slug='{self.slug}')>"
