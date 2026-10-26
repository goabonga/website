# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""VPN certificate model for audit logging."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from vpn_portal.db.base import Base, TimestampMixin


class VPNCertificate(Base, TimestampMixin):
    """Audit log of issued VPN certificates.

    Tracks every certificate issued by the VPN Portal for audit,
    revocation management, and connection correlation.
    """

    __tablename__ = "vpn_certificates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # User information (from OIDC token)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    username: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Certificate information
    serial_number: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    common_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    not_before: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    not_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    # Device information (optional, from client request)
    device_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Authorization information
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)),
        nullable=False,
        default=list,
    )
    assigned_routes: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)),
        nullable=False,
        default=list,
    )

    # Revocation status
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    revocation_reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    @property
    def is_revoked(self) -> bool:
        """Check if certificate is revoked."""
        return self.revoked_at is not None

    @property
    def is_expired(self) -> bool:
        """Check if certificate is expired."""
        return datetime.now(self.not_after.tzinfo) > self.not_after

    @property
    def is_valid(self) -> bool:
        """Check if certificate is valid (not revoked and not expired)."""
        return not self.is_revoked and not self.is_expired
