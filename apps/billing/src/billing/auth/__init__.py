# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Authentication module."""

from billing.auth.dependencies import (
    Auth,
    AuthContext,
    CurrentUser,
    get_auth_context,
    get_current_user,
    require_scopes,
)
from billing.auth.introspection import introspection_client
from billing.auth.jwks import jwks_manager
from billing.auth.models import User
from billing.auth.token_exchange import token_exchange_client

__all__ = [
    "Auth",
    "AuthContext",
    "CurrentUser",
    "User",
    "get_auth_context",
    "get_current_user",
    "introspection_client",
    "jwks_manager",
    "require_scopes",
    "token_exchange_client",
]
