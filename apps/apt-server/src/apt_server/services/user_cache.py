# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Local user cache — maps OIDC sub UUIDs to human-readable profiles.

Updated on every web login. Used to resolve owner/grantee display names
without calling the auth service on every page load.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apt_server.db.models.user_cache import UserCache
from apt_server.logging import get_logger

logger = get_logger(__name__)


async def upsert(
    db: AsyncSession,
    *,
    sub: str,
    email: str,
    name: str = "",
    avatar_url: str = "",
) -> None:
    """Insert or update a user cache entry."""
    existing = await db.get(UserCache, sub)
    if existing:
        existing.email = email or existing.email
        existing.name = name or existing.name
        existing.avatar_url = avatar_url or existing.avatar_url
        existing.updated_at = datetime.now(UTC)
    else:
        db.add(
            UserCache(
                sub=sub,
                email=email,
                name=name,
                avatar_url=avatar_url,
            )
        )
    await db.commit()


async def resolve_display(db: AsyncSession, identifier: str) -> str:
    """Resolve a sub UUID or email to a display name.

    Returns the email if found, otherwise the identifier as-is.
    """
    # Try by sub first
    entry = await db.get(UserCache, identifier)
    if entry:
        return entry.display

    # Try by email
    stmt = select(UserCache).where(UserCache.email == identifier)
    entry = (await db.execute(stmt)).scalar_one_or_none()
    if entry:
        return entry.display

    return identifier


async def resolve_many(db: AsyncSession, identifiers: list[str]) -> dict[str, str]:
    """Resolve multiple identifiers to display names in one query."""
    if not identifiers:
        return {}

    stmt = select(UserCache).where(
        UserCache.sub.in_(identifiers) | UserCache.email.in_(identifiers)
    )
    rows = (await db.execute(stmt)).scalars().all()

    lookup: dict[str, str] = {}
    for row in rows:
        lookup[row.sub] = row.display
        lookup[row.email] = row.display

    return {ident: lookup.get(ident, ident) for ident in identifiers}
