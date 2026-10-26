# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Application middlewares."""

from auth.middlewares.cors import OAuth2CORSMiddleware
from auth.middlewares.session import SlidingSessionMiddleware
from auth.middlewares.tenant import (
    TenantContext,
    TenantMiddleware,
    get_tenant_context,
    require_tenant,
    set_tenant_context,
)

__all__ = [
    "OAuth2CORSMiddleware",
    "SlidingSessionMiddleware",
    "TenantContext",
    "TenantMiddleware",
    "get_tenant_context",
    "require_tenant",
    "set_tenant_context",
]
