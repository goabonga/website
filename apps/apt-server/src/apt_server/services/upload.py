# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Orchestrate ``.deb`` uploads: parse, validate, persist, store in pool."""

import tempfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apt_server.acl.packages import Caller
from apt_server.db.models import Package, PackageVisibility
from apt_server.repo import pool
from apt_server.repo.debfile import DebMetadata, InvalidDebFileError, parse_deb
from apt_server.services.indexes import invalidate_index_cache


class UploadValidationError(ValueError):
    """Raised when an upload is rejected before any write happens."""


class UploadConflictError(Exception):
    """Raised when a (name, version, arch, suite, component) row already exists."""

    def __init__(self, existing: Package) -> None:
        super().__init__(f"package already exists: {existing.id}")
        self.existing = existing


async def save_upload(
    session: AsyncSession,
    *,
    caller: Caller,
    suite: str,
    component: str,
    raw_body: bytes,
    visibility: PackageVisibility = PackageVisibility.PRIVATE,
) -> Package:
    """Stage, parse, persist and move an uploaded ``.deb`` into the pool."""
    with tempfile.NamedTemporaryFile(suffix=".deb", delete=False) as tmp:
        tmp.write(raw_body)
        staged = Path(tmp.name)

    try:
        try:
            metadata = parse_deb(staged)
        except InvalidDebFileError as exc:
            raise UploadValidationError(str(exc)) from exc
        _validate(metadata, suite=suite, component=component)
        existing = await _find_existing(session, metadata, suite=suite, component=component)
        if existing is not None:
            raise UploadConflictError(existing)

        pool.write_deb(staged, metadata, component)
        relative = pool.pool_relative_path(metadata, component)

        package = Package(
            name=metadata.name,
            version=metadata.version,
            architecture=metadata.architecture,
            suite=suite,
            component=component,
            owner_id=caller.sub,
            visibility=visibility,
            filename=relative,
            size=metadata.size,
            md5=metadata.md5,
            sha1=metadata.sha1,
            sha256=metadata.sha256,
            description=metadata.description or None,
            control=metadata.control,
        )
        session.add(package)
        try:
            await session.flush()
        except IntegrityError:
            # Race: another upload inserted the same identity between our
            # _find_existing check and the flush. Undo the pool write so the
            # pool stays consistent with the DB and surface a conflict.
            await session.rollback()
            pool.delete_deb(relative)
            # The final file we just replaced may be a fresh copy we own.
            # If the existing row points to the same filename, leave it alone.
            raise UploadConflictError(
                await _find_existing(session, metadata, suite=suite, component=component) or package
            )
        await invalidate_index_cache(session)
        await session.commit()
        await session.refresh(package)
        return package
    finally:
        staged.unlink(missing_ok=True)


def _validate(metadata: DebMetadata, *, suite: str, component: str) -> None:
    from apt_server.acl import components as component_rules
    from apt_server.config import settings

    if not component_rules.is_known_component(component):
        raise UploadValidationError(f"unknown component: {component}")
    if suite not in settings.apt_suites_list:
        raise UploadValidationError(f"unknown suite: {suite}")
    if (
        metadata.architecture not in settings.apt_architectures_list
        and metadata.architecture != "all"
    ):
        raise UploadValidationError(f"unsupported architecture: {metadata.architecture}")


async def _find_existing(
    session: AsyncSession,
    metadata: DebMetadata,
    *,
    suite: str,
    component: str,
) -> Package | None:
    stmt = select(Package).where(
        Package.name == metadata.name,
        Package.version == metadata.version,
        Package.architecture == metadata.architecture,
        Package.suite == suite,
        Package.component == component,
    )
    return (await session.execute(stmt)).scalar_one_or_none()
