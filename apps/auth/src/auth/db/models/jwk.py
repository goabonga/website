# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""JWK (JSON Web Key) database model."""

import uuid
from datetime import datetime

from sqlalchemy import LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from auth.db.base import Base, TimestampMixin


class JWK(Base, TimestampMixin):
    """JSON Web Key stored in database.

    Stores RSA key pairs for JWT signing/verification.
    Private keys are encrypted with AES-256-GCM before storage.
    """

    __tablename__ = "jwks"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    kid: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )
    kty: Mapped[str] = mapped_column(
        String(8),
        default="RSA",
        nullable=False,
    )
    alg: Mapped[str] = mapped_column(
        String(16),
        default="RS256",
        nullable=False,
    )
    use: Mapped[str] = mapped_column(
        String(8),
        default="sig",
        nullable=False,
    )

    # Private key encrypted with AES-256-GCM
    private_key_encrypted: Mapped[bytes] = mapped_column(
        LargeBinary,
        nullable=False,
    )
    # Public key in PEM format (not encrypted)
    public_key_pem: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<JWK kid={self.kid} active={self.is_active}>"
