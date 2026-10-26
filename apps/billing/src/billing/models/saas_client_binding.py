# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Binding between an OAuth client and a SaaS application."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from billing.models.base import Base

if TYPE_CHECKING:
    from billing.models.saas_app import SaasApp


class SaasClientBinding(Base):
    """Allows one OAuth client to act on one SaaS application.

    A client (the ``client_id`` of its access tokens) can only read or change
    the data of the SaaS applications it is bound to. A client can be bound
    to several applications, and an application can have several clients.
    """

    __tablename__ = "saas_client_bindings"
    __table_args__ = (
        UniqueConstraint("saas_app_id", "client_id", name="uq_binding_saas_client"),
        Index("ix_saas_client_bindings_client", "client_id"),
    )

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    saas_app_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), ForeignKey("saas_apps.id", ondelete="CASCADE")
    )
    client_id: Mapped[str] = mapped_column(String(255), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    saas_app: Mapped[SaasApp] = relationship()
