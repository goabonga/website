# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API dependencies for authentication and authorization."""

from typing import Annotated

from fastapi import Depends

from vpn_portal.auth import AuthContext, require_scopes

# VPN scope dependencies using token exchange
RequireVPNConnect = Annotated[AuthContext, Depends(require_scopes("vpn:connect"))]
