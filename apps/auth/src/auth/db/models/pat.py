# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Personal Access Token database model."""

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auth.db.base import Base, TimestampMixin


class PATExpirationPreset(StrEnum):
    """Predefined expiration options for PATs."""

    DAYS_7 = "7_days"
    DAYS_30 = "30_days"
    DAYS_60 = "60_days"
    DAYS_90 = "90_days"
    DAYS_365 = "365_days"
    NO_EXPIRATION = "no_expiration"
    CUSTOM = "custom"


class PersonalAccessToken(Base, TimestampMixin):
    """Personal Access Token for user API access.

    Similar to GitHub's fine-grained PATs, these tokens allow users
    to authenticate programmatically with specific scopes.

    Security features:
    - Token is only shown once at creation
    - Token stored as SHA-256 hash (never plaintext)
    - Token prefix for identification (gab_pat_)
    - Last used tracking
    - Optional resource targeting (tenant/client)
    """

    __tablename__ = "personal_access_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Token identification
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Token security - only hash is stored
    # Format: SHA-256 hash of the full token (gab_pat_<random>)
    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )

    # Token prefix hint (last 4 chars) for identification in UI
    # e.g., "****abcd"
    token_suffix: Mapped[str] = mapped_column(
        String(4),
        nullable=False,
    )

    # Scopes - array of scope names from the Scope table
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(String(100)),
        nullable=False,
        default=list,
    )

    # Expiration
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,  # NULL means no expiration
    )

    # Optional resource targeting
    # Limit token to specific tenant
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # Limit token to specific OAuth2 client
    target_client_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("oauth2_clients.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Activity tracking
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_used_ip: Mapped[str | None] = mapped_column(
        String(45),  # IPv6 max length
        nullable=True,
    )
    use_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # Revocation
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    revocation_reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship(foreign_keys=[user_id])
    tenant: Mapped["Tenant | None"] = relationship()
    target_client: Mapped["OAuth2Client | None"] = relationship()
    revoker: Mapped["User | None"] = relationship(foreign_keys=[revoked_by])

    def __repr__(self) -> str:
        return (
            f"<PersonalAccessToken name={self.name} "
            f"user_id={self.user_id} "
            f"revoked={self.revoked_at is not None}>"
        )

    @property
    def is_expired(self) -> bool:
        """Check if the token has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(UTC) > self.expires_at

    @property
    def is_valid(self) -> bool:
        """Check if the token is valid (not expired and not revoked)."""
        return not self.is_expired and self.revoked_at is None


if TYPE_CHECKING:
    from auth.db.models.oauth2 import OAuth2Client
    from auth.db.models.tenant import Tenant
    from auth.db.models.user import User
