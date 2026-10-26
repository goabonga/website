# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Authorized clients: the registry gate and the sender / provider rules.

Every call of a regular client goes through :func:`ensure_authorized`, and
everything a client sends takes its identity (sender, reply-to, provider) from
its record through :func:`resolve_identity`, so a caller can no longer choose an
arbitrary ``from_email``. Administrators are not bound by a record.
"""

import time
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mailler.config import settings
from mailler.database import AsyncSessionLocal
from mailler.logging import get_logger
from mailler.models.client import AuthorizedClient

logger = get_logger(__name__)

# client_id -> monotonic time until which the client is known to be active
_active_until: dict[str, float] = {}


@dataclass(frozen=True)
class ResolvedIdentity:
    """Sender, reply-to and provider an email is sent with."""

    from_email: str
    from_name: str | None
    reply_to: str | None
    provider: str


def clear_cache() -> None:
    """Forget which clients are known to be active."""
    _active_until.clear()


async def get_client(db: AsyncSession, client_id: str | None) -> AuthorizedClient | None:
    """Return the record of a client, or None."""
    if not client_id:
        return None
    result = await db.execute(
        select(AuthorizedClient).where(AuthorizedClient.client_id == client_id)
    )
    return result.scalar_one_or_none()


async def ensure_authorized(client_id: str) -> None:
    """Refuse a client that is not registered or not active.

    An active client is remembered for ``CLIENT_CACHE_TTL`` seconds, so a
    deactivation takes at most that long to be noticed by every process.

    Raises:
        HTTPException: 403 when the client has no record or its record is inactive.
    """
    now = time.monotonic()
    if _active_until.get(client_id, 0) > now:
        return

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AuthorizedClient.is_active).where(AuthorizedClient.client_id == client_id)
        )
        active = result.scalar_one_or_none()

    if active is None:
        logger.info("Unregistered client refused", extra={"client_id": client_id})
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Client is not registered"
        )
    if not active:
        logger.info("Inactive client refused", extra={"client_id": client_id})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Client is deactivated")

    if settings.client_cache_ttl > 0:
        _active_until[client_id] = now + settings.client_cache_ttl


def _identities(client: AuthorizedClient) -> list[dict]:
    """The sender identities of a client, the default one first."""
    identities = []
    if client.from_email:
        identities.append({"email": client.from_email, "name": client.from_name})
    identities.extend(client.allowed_senders or [])
    return identities


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def check_overrides(
    client: AuthorizedClient | None,
    *,
    is_admin: bool,
    from_email: str | None = None,
    from_name: str | None = None,
    reply_to: str | None = None,
    provider: str | None = None,
) -> None:
    """Check the sender, reply-to and provider a caller asks for against its record.

    Nothing is checked for an administrator.

    Raises:
        HTTPException: 403 when a requested value is not allowed for the client.
    """
    if is_admin:
        return
    if client is None:
        raise _forbidden("Client is not registered")

    if from_email is not None:
        identity = next(
            (i for i in _identities(client) if i["email"].lower() == from_email.lower()), None
        )
        if identity is None:
            raise _forbidden("Sender address is not allowed for this client")
        if from_name is not None and from_name != identity.get("name"):
            raise _forbidden("Sender name is not allowed for this client")
    elif from_name is not None and from_name != client.from_name:
        raise _forbidden("Sender name is not allowed for this client")

    if reply_to is not None and client.reply_to and reply_to.lower() != client.reply_to.lower():
        raise _forbidden("Reply-to address is not allowed for this client")

    if provider is not None:
        allowed = set(client.allowed_providers or [])
        if client.default_provider:
            allowed.add(client.default_provider)
        if provider not in allowed:
            raise _forbidden("Provider is not allowed for this client")


def resolve_identity(
    client: AuthorizedClient | None,
    *,
    is_admin: bool,
    from_email: str | None = None,
    from_name: str | None = None,
    reply_to: str | None = None,
    provider: str | None = None,
) -> ResolvedIdentity:
    """Work out the sender, reply-to and provider of an email.

    A regular client gets what its record allows: the values it asks for are
    checked, the missing ones come from the record. An administrator is not
    bound by a record; its missing values come from the record of its own
    client, then from the optional platform settings.

    Raises:
        HTTPException: 403 when a requested value is not allowed, 422 when no
            sender or no provider can be determined.
    """
    check_overrides(
        client,
        is_admin=is_admin,
        from_email=from_email,
        from_name=from_name,
        reply_to=reply_to,
        provider=provider,
    )

    if not from_email:
        if client is not None and client.from_email:
            from_email, default_name = client.from_email, client.from_name
        elif is_admin and settings.default_from:
            from_email, default_name = settings.default_from, settings.default_from_name
        else:
            raise HTTPException(
                status_code=422,
                detail="No sender address: the client has none configured",
            )
        from_name = from_name or default_name
    else:
        identity = (
            next(
                (i for i in _identities(client) if i["email"].lower() == from_email.lower()),
                None,
            )
            if client is not None
            else None
        )
        if from_name is None and identity is not None:
            from_name = identity.get("name")

    reply_to = reply_to or (client.reply_to if client is not None else None)

    if not provider:
        if client is not None and client.default_provider:
            provider = client.default_provider
        elif is_admin and settings.default_provider:
            provider = settings.default_provider
        else:
            raise HTTPException(
                status_code=422,
                detail="No provider: the client has no default provider configured",
            )

    return ResolvedIdentity(
        from_email=from_email,
        from_name=from_name or None,
        reply_to=reply_to,
        provider=provider,
    )
