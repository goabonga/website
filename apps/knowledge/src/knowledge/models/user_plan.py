# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""User plan model for personal account quotas."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from knowledge.models.base import Base
from knowledge.models.enums import PlanType


class UserPlan(Base):
    """User's personal plan for quota enforcement.

    This tracks the plan for individual users (not organizations).
    Users on Free/Starter/Pro plans have their collections owned directly.
    """

    __tablename__ = "user_plans"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
    )
    plan: Mapped[PlanType] = mapped_column(
        Enum(
            PlanType,
            name="plantype",
            values_callable=lambda x: [e.value for e in x],
            create_type=False,
        ),
        default=PlanType.FREE,
        nullable=False,
    )
    settings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
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
        return f"<UserPlan {self.user_id} ({self.plan.value})>"
