# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Platform API routes (admin operations)."""

from billing.routes.platform import products, saas

__all__ = [
    "saas",
    "products",
]
