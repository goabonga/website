# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API routes."""

from billing.routes import health
from billing.routes.platform import saas

__all__ = [
    "health",
    "saas",
]
