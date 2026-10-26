# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""System prompt models with version history."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class SystemPrompt(Base):
    """System prompt configuration with scope-based access.

    Prompts can be assigned to specific user scopes, allowing different
    personas or behaviors for different user types.
    """

    __tablename__ = "system_prompts"

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
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
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

    # Relationship to versions
    versions: Mapped[list["SystemPromptVersion"]] = relationship(
        "SystemPromptVersion",
        back_populates="prompt",
        lazy="selectin",
        order_by="desc(SystemPromptVersion.version)",
    )

    def is_accessible(self, user_scopes: set[str] | None) -> bool:
        """Check if prompt is accessible given user scopes.

        Args:
            user_scopes: User's scopes (None for anonymous users)

        Returns:
            True if prompt is accessible
        """
        # Default prompt is always accessible as fallback
        if self.is_default:
            return True
        # Prompts without required_scopes are accessible to everyone
        if not self.required_scopes:
            return True
        # If required_scopes is set, user must have ALL of them
        if user_scopes is None:
            return False
        return set(self.required_scopes).issubset(user_scopes)

    def get_current_version(self) -> "SystemPromptVersion | None":
        """Get the current active version of this prompt."""
        for version in self.versions:
            if version.is_current:
                return version
        return None

    def get_specificity(self) -> int:
        """Get the specificity score (number of required scopes).

        Higher specificity = more specific prompt.
        Used to select the most specific matching prompt.
        """
        return len(self.required_scopes) if self.required_scopes else 0


class SystemPromptVersion(Base):
    """Version of a system prompt for history tracking."""

    __tablename__ = "system_prompt_versions"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    prompt_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("system_prompts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        default=dict,
        nullable=False,
    )
    is_current: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Relationship back to prompt
    prompt: Mapped[SystemPrompt] = relationship(
        "SystemPrompt",
        back_populates="versions",
        lazy="joined",
    )

    __table_args__ = (Index("ix_system_prompt_versions_prompt_current", "prompt_id", "is_current"),)
