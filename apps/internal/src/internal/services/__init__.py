# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Application services."""

from internal.services.analytics_client import AnalyticsClient, analytics_client
from internal.services.auth_client import AuthClient, UserInfo
from internal.services.mailler_client import mailler_client

__all__ = [
    "AnalyticsClient",
    "AuthClient",
    "UserInfo",
    "analytics_client",
    "mailler_client",
]
