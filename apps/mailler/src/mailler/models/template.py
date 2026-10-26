# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Email template model for Mailler."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mailler.models.base import Base


class TemplateStatus(StrEnum):
    """Email template status."""

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class EmailTemplate(Base):
    """Email template with MJML source and compiled HTML."""

    __tablename__ = "email_templates"
    __table_args__ = (UniqueConstraint("client_id", "slug", name="uq_email_templates_client_slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Owner: templates are private to the client that created them
    client_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)

    # Identification (unique per client)
    slug: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Content
    subject_template: Mapped[str] = mapped_column(String(500), nullable=False)
    mjml_source: Mapped[str] = mapped_column(Text, nullable=False)
    html_compiled: Mapped[str | None] = mapped_column(Text, nullable=True)
    plain_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Status
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=TemplateStatus.DRAFT.value, index=True
    )

    # Variables extracted from template (e.g., ["first_name", "last_name"])
    variables: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    # Metadata
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<EmailTemplate(id={self.id}, slug={self.slug}, status={self.status})>"
