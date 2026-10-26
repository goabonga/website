# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Campaign and pixel tracking models."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from analytics.models.base import Base


class Campaign(Base):
    """Marketing campaign for tracking."""

    __tablename__ = "analytics_campaigns"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Campaign information
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tracking_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    # Configuration
    destination_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Statistics (denormalized for performance)
    click_count: Mapped[int] = mapped_column(Integer, default=0)
    unique_click_count: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    pixels: Mapped[list["Pixel"]] = relationship(
        "Pixel",
        back_populates="campaign",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Campaign {self.name}>"


class Pixel(Base):
    """Tracking pixel for email campaigns."""

    __tablename__ = "analytics_pixels"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Campaign reference
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analytics_campaigns.id", ondelete="CASCADE"),
        index=True,
    )

    # Recipient information
    recipient_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recipient_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pixel_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    # Extra data
    extra_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    first_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    open_count: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    campaign: Mapped["Campaign"] = relationship(
        "Campaign",
        back_populates="pixels",
    )
    opens: Mapped[list["PixelOpen"]] = relationship(
        "PixelOpen",
        back_populates="pixel",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Pixel {self.pixel_key}>"


class PixelOpen(Base):
    """Individual pixel open event with detailed information."""

    __tablename__ = "analytics_pixel_opens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Pixel reference
    pixel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analytics_pixels.id", ondelete="CASCADE"),
        index=True,
    )

    # Open information
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Geolocation
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Relationships
    pixel: Mapped["Pixel"] = relationship(
        "Pixel",
        back_populates="opens",
    )

    __table_args__ = (Index("ix_analytics_pixel_opens_opened_at", "opened_at"),)

    def __repr__(self) -> str:
        return f"<PixelOpen {self.pixel_id} at {self.opened_at}>"
