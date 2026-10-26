# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Pydantic schemas for /api/v1/sessions endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class SessionResponse(BaseModel):
    """Response for a single session."""

    id: uuid.UUID
    user_id: uuid.UUID
    user_email: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    expires_at: datetime
    revoked_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
