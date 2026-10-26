# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Partitioning of the API between SaaS applications.

Scopes say *what* a client may do, never *on whose data*. This module adds
the second question: an OAuth client may only act on the SaaS applications
it is bound to (``saas_client_bindings``).

Rules, applied to every route that targets a SaaS application:

* a client with the admin scope (``PARTITION_ADMIN_SCOPE``) may act on every
  SaaS application and manage the bindings;
* any other client may act on the applications it is bound to, and only
  those;
* a client without any binding is denied (secure by default), unless
  ``PARTITION_ALLOW_UNBOUND=true`` restores the former behavior for clients
  that have no binding at all;
* a token that does not identify its client is denied.

The client is the one that obtained the token presented by the caller, never
the client this service uses for token exchange.
"""

import logging
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from billing.auth import AuthContext, require_scopes
from billing.auth.dependencies import oauth2_scheme
from billing.config import settings
from billing.database import get_db
from billing.models import SaasClientBinding

logger = logging.getLogger(__name__)


class PartitionGuard:
    """Decides which SaaS applications a client may act on."""

    def __init__(self, admin_scope: str, allow_unbound: bool) -> None:
        self.admin_scope = admin_scope
        self.allow_unbound = allow_unbound

    def is_admin(self, auth: AuthContext) -> bool:
        """Tell whether the presented token carries the admin scope."""
        return auth.has_token_scope(self.admin_scope)

    async def bound_saas_ids(self, db: AsyncSession, client_id: str) -> set[str]:
        """Return the identifiers of the SaaS applications a client is bound to."""
        result = await db.execute(
            select(SaasClientBinding.saas_app_id).where(SaasClientBinding.client_id == client_id)
        )
        return {str(saas_id) for saas_id in result.scalars().all()}

    async def authorized_saas_ids(self, auth: AuthContext, db: AsyncSession) -> set[str] | None:
        """Return the SaaS applications the caller may see, or None for all of them."""
        if self.is_admin(auth):
            return None
        if not auth.client_id:
            return set()
        bound = await self.bound_saas_ids(db, auth.client_id)
        if not bound and self.allow_unbound:
            return None
        return bound

    async def authorize(self, auth: AuthContext, saas_id: str, db: AsyncSession) -> None:
        """Allow the caller to act on ``saas_id`` or raise 403."""
        if self.is_admin(auth):
            return
        if not auth.client_id:
            logger.warning("Access to SaaS %s refused: the token carries no client id", saas_id)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The access token does not identify its client",
            )
        allowed = await self.authorized_saas_ids(auth, db)
        if allowed is None or str(saas_id) in allowed:
            return
        logger.warning("Client %s refused on SaaS %s: no binding", auth.client_id, saas_id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This client is not authorized for this SaaS app",
        )


def get_partition_guard() -> PartitionGuard:
    """Build the guard from the settings (overridable in tests)."""
    return PartitionGuard(settings.partition_admin_scope, settings.partition_allow_unbound)


Guard = Annotated[PartitionGuard, Depends(get_partition_guard)]


def require_saas_scopes(*scopes: str) -> Callable:
    """Require scopes *and* access to the SaaS application of the route.

    Use it instead of ``require_scopes`` on routes whose path has a
    ``{saas_id}`` parameter: the token is validated like ``require_scopes``
    does, then the client is checked against the bindings of that SaaS
    application. A client that is not allowed gets ``403`` before the route
    runs, whether or not the application exists.
    """
    authenticate = require_scopes(*scopes)

    async def dependency(
        saas_id: str,
        auth: Annotated[AuthContext, Depends(authenticate)],
        guard: Guard,
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> AuthContext:
        await guard.authorize(auth, saas_id, db)
        return auth

    return dependency


async def require_admin(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
) -> AuthContext:
    """Require the admin scope (``PARTITION_ADMIN_SCOPE``), read when the request is served."""
    return await require_scopes(settings.partition_admin_scope)(request=request, token=token)
