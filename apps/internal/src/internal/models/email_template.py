# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Email template model for newsletter/email campaigns."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from internal.database import Base


class EmailTemplateStatus(StrEnum):
    """Status of an email template."""

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class EmailTemplate(Base):
    """Email template with MJML source and compiled HTML.

    Supports both visual (GrapesJS) and code (MJML) editing modes.
    Templates can include variables like {{first_name}}, {{email}}, etc.
    """

    __tablename__ = "email_templates"

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
    subject_template: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        default="",
    )
    mjml_source: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )
    html_compiled: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    plain_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=EmailTemplateStatus.DRAFT.value,
        index=True,
    )
    variables: Mapped[list[str] | None] = mapped_column(
        ARRAY(String),
        nullable=True,
        default=list,
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

    def __repr__(self) -> str:
        return f"<EmailTemplate(id={self.id}, slug='{self.slug}', status='{self.status}')>"
