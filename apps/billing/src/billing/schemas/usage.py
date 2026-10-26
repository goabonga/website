# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Usage event schemas."""

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from billing.config import settings
from billing.models.usage_event import UsageEventStatus


class UsageReport(BaseModel):
    """Schema for reporting a usage event."""

    subscription_id: str
    quantity: int = Field(..., ge=1)
    timestamp: datetime | None = None  # Defaults to now
    idempotency_key: str | None = Field(None, max_length=255)
    action: str | None = Field(None, max_length=100)
    metadata: dict | None = None


class UsageBatchReport(BaseModel):
    """Schema for batch reporting usage events."""

    events: list[UsageReport] = Field(..., min_length=1, max_length=settings.usage_batch_max_events)


class UsageEventResponse(BaseModel):
    """Schema for usage event response."""

    id: str
    subscription_id: str
    quantity: int
    timestamp: datetime
    idempotency_key: str | None
    status: UsageEventStatus
    stripe_usage_record_id: str | None
    reported_at: datetime | None
    error_message: str | None
    action: str | None
    metadata: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def resolve_metadata(cls, data):
        """Map extra_data -> metadata for ORM objects.

        SQLAlchemy models inherit Base.metadata (MetaData registry),
        which clashes with the schema field. Use extra_data column instead.
        """
        from billing.models.base import Base

        if isinstance(data, Base):
            return {
                field: getattr(data, "extra_data" if field == "metadata" else field, None)
                for field in cls.model_fields
            }
        return data
