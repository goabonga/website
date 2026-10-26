# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API routes."""

from team.routes import health
from team.routes.team import teams

__all__ = [
    "health",
    "teams",
]
