# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Usage tracking model for quotas and billing."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from knowledge.models.base import Base


class UsageRecord(Base):
    """Usage record for tracking API usage per tenant."""

    __tablename__ = "usage_records"
    __table_args__ = (Index("ix_usage_tenant_metric_period", "tenant_id", "metric", "period"),)

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    metric: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    period: Mapped[str] = mapped_column(String(20), nullable=False)  # YYYY-MM format
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<UsageRecord {self.metric}={self.value}>"
