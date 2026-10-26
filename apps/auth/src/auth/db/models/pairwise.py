# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Pairwise subject identifier database model."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auth.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from auth.db.models.tenant import Tenant
    from auth.db.models.user import User


class PairwiseSubject(Base, TimestampMixin):
    """Pairwise subject identifier for per-tenant user anonymization.

    Each (user, tenant) pair gets a unique, opaque sub_value that is used
    as the ``sub`` claim in tokens issued for that tenant. This prevents
    cross-tenant user tracking by ensuring different tenants see different
    subject identifiers for the same user.
    """

    __tablename__ = "pairwise_subjects"
    __table_args__ = (UniqueConstraint("user_id", "tenant_id", name="uq_pairwise_user_tenant"),)

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sub_value: Mapped[uuid.UUID] = mapped_column(
        nullable=False,
        default=uuid.uuid4,
        unique=True,
        index=True,
    )

    # Relationships
    user: Mapped["User"] = relationship()
    tenant: Mapped["Tenant"] = relationship()

    def __repr__(self) -> str:
        return f"<PairwiseSubject user_id={self.user_id} tenant_id={self.tenant_id}>"
