# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Authorized client model for Mailler."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mailler.models.base import Base


class AuthorizedClient(Base):
    """An application (OAuth2 client) allowed to send through Mailler.

    The record fixes the identity the client sends with: its sender
    addresses, its reply-to address and the providers it may use. A client
    without a record, or whose record is not active, is refused.
    """

    __tablename__ = "authorized_clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # OAuth2 client the record applies to (the ``client_id`` / ``azp`` of its tokens)
    client_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Default sender identity and reply-to address
    from_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    from_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reply_to: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Other sender identities the client may choose, as [{"email": ..., "name": ...}]
    allowed_senders: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    # Providers the client may use, and the one used when it names none
    allowed_providers: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    default_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<AuthorizedClient(client_id={self.client_id}, active={self.is_active})>"
