# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API dependencies for authentication and authorization."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from vpn_portal.auth import AuthContext, require_scopes
from vpn_portal.db.session import get_db

# Type aliases for dependencies
GetDB = Annotated[AsyncSession, Depends(get_db)]

# VPN scope dependencies using token exchange
RequireVPNConnect = Annotated[AuthContext, Depends(require_scopes("vpn:connect"))]
RequireVPNAdmin = Annotated[AuthContext, Depends(require_scopes("vpn:admin"))]
RequireVPNServer = Annotated[AuthContext, Depends(require_scopes("vpn:server"))]
