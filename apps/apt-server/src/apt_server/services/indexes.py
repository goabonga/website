# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Compose per-caller ``Packages`` and ``Release`` outputs from the DB."""

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from apt_server.acl.packages import Caller, visible_package_filter
from apt_server.config import settings
from apt_server.db.models import IndexCache, Package
from apt_server.repo import indexes, release


async def invalidate_index_cache(session: AsyncSession) -> None:
    """Drop every cached Packages rendering.

    Called after any mutation that can change a caller's view of the
    repository: upload, delete, visibility change, ACL grant/revoke. The
    cost of regenerating is a single SQL scan plus RFC 822 serialisation,
    so wiping the cache is far cheaper than tracking which entries are
    affected by a given change.
    """
    await session.execute(delete(IndexCache))


def cache_key(
    caller: Caller | None,
    *,
    suite: str,
    component: str,
    architecture: str,
    gzip: bool,
) -> str:
    """Return a deterministic cache key for a specific Packages variant."""
    caller_id = caller.sub if caller else ""
    groups = ",".join(sorted(caller.groups)) if caller else ""
    raw = f"{caller_id}|{groups}|{suite}|{component}|{architecture}|{'gz' if gzip else 'raw'}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def render_packages(
    session: AsyncSession,
    caller: Caller | None,
    *,
    suite: str,
    component: str,
    architecture: str,
    gzip: bool = False,
) -> bytes:
    """Render (and cache) the Packages file seen by ``caller``."""
    key = cache_key(
        caller,
        suite=suite,
        component=component,
        architecture=architecture,
        gzip=gzip,
    )
    cached = await _read_cache(session, key)
    if cached is not None:
        return cached

    stmt = (
        select(Package)
        .where(
            Package.suite == suite,
            Package.component == component,
            Package.architecture.in_([architecture, "all"]),
            visible_package_filter(caller),
        )
        .order_by(Package.name, Package.version, Package.architecture)
    )
    rows = (await session.execute(stmt)).scalars().all()
    body = indexes.render_packages_file(rows)
    if gzip:
        body = indexes.gzip_packages(body)
    await _write_cache(session, key, body)
    return body


async def render_release(
    session: AsyncSession,
    caller: Caller | None,
    *,
    suite: str,
) -> bytes:
    """Render the per-caller Release body with matching Packages checksums."""
    from apt_server.acl.components import is_public_component

    if caller is None:
        candidate_components = [c for c in settings.apt_components_list if is_public_component(c)]
    else:
        candidate_components = list(settings.apt_components_list)
    architectures = list(settings.apt_architectures_list)

    # Build payload and track which components have visible packages
    payload: dict[str, bytes] = {}
    components_with_packages: set[str] = set()
    for component in candidate_components:
        for architecture in architectures:
            plain = await render_packages(
                session,
                caller,
                suite=suite,
                component=component,
                architecture=architecture,
                gzip=False,
            )
            if plain.strip():
                components_with_packages.add(component)
            payload[f"{component}/binary-{architecture}/Packages"] = plain
            gz = await render_packages(
                session,
                caller,
                suite=suite,
                component=component,
                architecture=architecture,
                gzip=True,
            )
            payload[f"{component}/binary-{architecture}/Packages.gz"] = gz

    # Only include public components + private components where the caller has
    # visible packages. This prevents leaking the existence of private components
    # the caller has no access to.
    visible_components = [
        c for c in candidate_components if is_public_component(c) or c in components_with_packages
    ]
    # Filter payload to only visible components
    visible_payload = {
        k: v for k, v in payload.items() if any(k.startswith(f"{c}/") for c in visible_components)
    }

    return release.render_release(
        suite=suite,
        components=visible_components,
        architectures=architectures,
        indexes=visible_payload,
    )


async def _read_cache(session: AsyncSession, key: str) -> bytes | None:
    row = await session.get(IndexCache, key)
    if row is None:
        return None
    ttl = settings.apt_index_cache_ttl
    if ttl <= 0:
        return row.body
    if datetime.now(UTC) - row.generated_at > timedelta(seconds=ttl):
        await session.delete(row)
        await session.commit()
        return None
    return row.body


async def _write_cache(session: AsyncSession, key: str, body: bytes) -> None:
    existing = await session.get(IndexCache, key)
    digest = hashlib.sha256(body).hexdigest()
    if existing is None:
        session.add(
            IndexCache(
                cache_key=key,
                body=body,
                sha256=digest,
                generated_at=datetime.now(UTC),
            )
        )
    else:
        existing.body = body
        existing.sha256 = digest
        existing.generated_at = datetime.now(UTC)
    await session.commit()
