# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Pydantic schemas for /api/v1/pats endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class PATResponse(BaseModel):
    """Response for a single Personal Access Token."""

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    token_suffix: str
    scopes: list[str]
    description: str | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None
    use_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class PATDetailResponse(BaseModel):
    """Detailed PAT response including ownership and last-used context."""

    id: uuid.UUID
    user_id: uuid.UUID
    user_email: str | None = None
    tenant_id: uuid.UUID | None = None
    target_client_id: uuid.UUID | None = None
    name: str
    token_suffix: str
    scopes: list[str]
    description: str | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None
    last_used_ip: str | None = None
    use_count: int
    created_at: datetime

    model_config = {"from_attributes": True}
