# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Platform API routes (admin operations)."""

from billing.routes.platform import clients, customers, prices, products, saas, subscriptions

__all__ = [
    "saas",
    "clients",
    "products",
    "prices",
    "customers",
    "subscriptions",
]
