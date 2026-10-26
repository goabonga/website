# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Authentication module with JWT validation and scope-based authorization."""

from internal.auth.dependencies import get_current_user, require_scope
from internal.auth.jwt import JWTValidator
from internal.auth.models import User

__all__ = ["JWTValidator", "User", "get_current_user", "require_scope"]
