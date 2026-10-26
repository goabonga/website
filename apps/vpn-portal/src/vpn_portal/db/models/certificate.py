# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""VPN Certificate and Connection models for audit logging."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

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

    # Relationships
    connections: Mapped[list["VPNConnection"]] = relationship(
        "VPNConnection",
        back_populates="certificate",
        cascade="all, delete-orphan",
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


class VPNConnection(Base, TimestampMixin):
    """Active and historical VPN connections.

    Tracks connection events from OpenVPN client-connect/disconnect scripts.
    """

    __tablename__ = "vpn_connections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Link to certificate
    certificate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vpn_certificates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Connection timestamps
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    disconnected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Network information
    assigned_ip: Mapped[str] = mapped_column(
        String(45),  # IPv4 or IPv6
        nullable=False,
    )
    client_ip: Mapped[str] = mapped_column(
        String(45),
        nullable=False,
    )

    # Traffic statistics (updated on disconnect)
    bytes_received: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
    )
    bytes_sent: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
    )

    # Relationships
    certificate: Mapped["VPNCertificate"] = relationship(
        "VPNCertificate",
        back_populates="connections",
    )

    @property
    def is_active(self) -> bool:
        """Check if connection is still active."""
        return self.disconnected_at is None

    @property
    def duration_seconds(self) -> int | None:
        """Get connection duration in seconds."""
        if self.disconnected_at is None:
            return None
        return int((self.disconnected_at - self.connected_at).total_seconds())
