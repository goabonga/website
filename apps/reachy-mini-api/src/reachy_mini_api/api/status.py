# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Status API for system monitoring."""

import platform
from datetime import datetime

from fastapi import APIRouter, Depends

from reachy_mini_api.auth import AuthContext, require_scopes
from reachy_mini_api.logging import get_logger, log_action

logger = get_logger(__name__)
router = APIRouter()


@router.get("/server")
async def get_server_status(
    auth: AuthContext = Depends(require_scopes("reachy:status:read")),
):
    """Get server status information."""
    log_action(logger, "get_server_status", user_id=auth.user_id)

    return {
        "timestamp": datetime.now().isoformat(),
        "hostname": platform.node(),
        "platform": platform.system(),
        "python_version": platform.python_version(),
        "status": "online",
    }


@router.get("/services")
async def get_services_status(
    auth: AuthContext = Depends(require_scopes("reachy:status:read")),
):
    """Get status of monitored services."""
    log_action(logger, "get_services_status", user_id=auth.user_id)

    # TODO: Implement actual service monitoring
    return {
        "services": [
            {"name": "fastapi-api", "status": "running", "port": 8000},
            {"name": "asterisk-bot", "status": "running", "port": 4573},
            {"name": "web-app", "status": "running", "port": 8003},
        ],
    }
