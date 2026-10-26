# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Health check response schemas."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
