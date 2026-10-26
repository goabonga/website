# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Access control shared by the routes that act on behalf of a client."""

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from custom_domain.auth import AuthContext, require_scopes
from custom_domain.database import get_db
from custom_domain.services import domain_service


async def ensure_client_authorized(db: AsyncSession, auth: AuthContext) -> None:
    """Check that the caller's client is registered and still active.

    This runs on every request, not only when a domain is created: deactivating a
    client in the registry takes effect immediately for all of its calls. Holders
    of the administration scope are operators, not registered clients, and are
    not checked.

    Raises:
        HTTPException: 403 when the token carries no client identifier or the
            client is unknown or inactive
    """
    if auth.is_admin:
        return

    client_id = auth.user.client_id
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client ID required",
        )

    if not await domain_service.get_authorized_client(db, client_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client not authorized",
        )


def require_client_scopes(*required_scopes: str) -> Callable:
    """Require scopes, then require the caller's client to be registered and active.

    Usage: ``auth: AuthContext = Depends(require_client_scopes("custom-domain:read"))``
    """
    scope_dependency = require_scopes(*required_scopes)

    async def dependency(
        auth: AuthContext = Depends(scope_dependency),
        db: AsyncSession = Depends(get_db),
    ) -> AuthContext:
        await ensure_client_authorized(db, auth)
        return auth

    return dependency
