# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tool catalog route — list all registered tools."""

from typing import Annotated

from fastapi import APIRouter, Depends

import team.services.tools  # noqa: F401 — trigger registration
from team.auth import AuthContext, require_scopes
from team.services.tool_service import ToolService

router = APIRouter(prefix="/platform/tools", tags=["Platform - Tools"])


@router.get("")
async def list_tools(
    _auth: Annotated[AuthContext, Depends(require_scopes("team:platform:read"))],
) -> list[dict]:
    """List all registered tools with their definitions."""
    return [
        {
            "name": definition["name"],
            "description": definition.get("description", ""),
            "parameters": definition.get("parameters", {}),
        }
        for _handler, definition in ToolService._registry.values()
    ]
