# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Authentication module for analytics API."""

from analytics.auth.dependencies import get_current_user, require_scopes
from analytics.auth.jwt import JWTValidator, TokenRevokedError, jwt_validator
from analytics.auth.models import User

__all__ = [
    "JWTValidator",
    "TokenRevokedError",
    "User",
    "get_current_user",
    "jwt_validator",
    "require_scopes",
]
