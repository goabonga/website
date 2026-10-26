# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Authentication module."""

from custom_domain.auth.dependencies import (
    Auth,
    AuthContext,
    CurrentUser,
    get_auth_context,
    get_current_user,
    require_scopes,
)
from custom_domain.auth.introspection import introspection_client
from custom_domain.auth.jwks import jwks_manager
from custom_domain.auth.models import User
from custom_domain.auth.token_exchange import token_exchange_client

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
