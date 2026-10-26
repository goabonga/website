# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Authentication module."""

from vpn_portal.auth.dependencies import (
    Auth,
    AuthContext,
    CurrentUser,
    get_auth_context,
    get_current_user,
    require_scopes,
)
from vpn_portal.auth.introspection import introspection_client
from vpn_portal.auth.jwks import jwks_manager
from vpn_portal.auth.models import User
from vpn_portal.auth.token_exchange import token_exchange_client

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
