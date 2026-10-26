# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Authentication module."""

from reachy_mini_api.auth.dependencies import (
    Auth,
    AuthContext,
    CurrentUser,
    get_auth_context,
    get_current_user,
    require_scopes,
)
from reachy_mini_api.auth.jwks import jwks_manager
from reachy_mini_api.auth.models import User

__all__ = [
    "Auth",
    "AuthContext",
    "CurrentUser",
    "User",
    "get_auth_context",
    "get_current_user",
    "jwks_manager",
    "require_scopes",
]
