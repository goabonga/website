# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Authentication module."""

from apt_server.auth.dependencies import (
    Auth,
    AuthContext,
    CurrentUser,
    get_auth_context,
    get_current_user,
    require_scopes,
)
from apt_server.auth.introspection import introspection_client
from apt_server.auth.jwks import jwks_manager
from apt_server.auth.models import User
from apt_server.auth.token_exchange import token_exchange_client
from apt_server.auth.userinfo import userinfo_client

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
    "userinfo_client",
]
