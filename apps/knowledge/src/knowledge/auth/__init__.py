# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""OAuth2/OIDC authentication module."""

from knowledge.auth.dependencies import Auth, get_current_user, get_optional_user, require_scopes
from knowledge.auth.models import User

__all__ = [
    "Auth",
    "User",
    "get_current_user",
    "get_optional_user",
    "require_scopes",
]
