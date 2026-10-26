# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Packages and ACL management endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apt_server.acl import components as component_rules
from apt_server.acl import scopes as scope_rules
from apt_server.acl.packages import can_read, can_write, visible_package_filter
from apt_server.auth.dependencies import Auth
from apt_server.database import get_db
from apt_server.db.models import ACLRole, Package, PackageACL, PackageVisibility
from apt_server.services.caller import caller_from_auth
from apt_server.services.indexes import invalidate_index_cache
from apt_server.services.upload import (
    UploadConflictError,
    UploadValidationError,
    save_upload,
)

router = APIRouter(prefix="/packages", tags=["packages"])


class PackageRead(BaseModel):
    """Package metadata returned to API clients."""

    id: uuid.UUID
    name: str
    version: str
    architecture: str
    suite: str
    component: str
    owner_id: str
    visibility: PackageVisibility
    filename: str
    size: int
    sha256: str
    description: str | None

    @classmethod
    def from_row(cls, package: Package) -> "PackageRead":
        return cls(
            id=package.id,
            name=package.name,
            version=package.version,
            architecture=package.architecture,
            suite=package.suite,
            component=package.component,
            owner_id=package.owner_id,
            visibility=package.visibility,
            filename=package.filename,
            size=package.size,
            sha256=package.sha256,
            description=package.description,
        )


class PackageUpdate(BaseModel):
    """Mutable fields on a package."""

    visibility: PackageVisibility | None = None
    description: str | None = None


class ACLGrantRead(BaseModel):
    """An ACL row returned to API clients."""

    id: uuid.UUID
    package_id: uuid.UUID
    grantee_user_id: str | None
    grantee_group: str | None
    role: ACLRole
    granted_by: str

    @classmethod
    def from_row(cls, row: PackageACL) -> "ACLGrantRead":
        return cls(
            id=row.id,
            package_id=row.package_id,
            grantee_user_id=row.grantee_user_id,
            grantee_group=row.grantee_group,
            role=row.role,
            granted_by=row.granted_by,
        )


class ACLGrantCreate(BaseModel):
    """Payload to grant an ACL entry."""

    grantee_user_id: str | None = Field(default=None, max_length=255)
    grantee_group: str | None = Field(default=None, max_length=255)
    role: ACLRole = ACLRole.READ


@router.post(
    "",
    response_model=PackageRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_package(
    auth: Auth,
    db: Annotated[AsyncSession, Depends(get_db)],
    deb: UploadFile,
    suite: Annotated[str, Form()],
    component: Annotated[str, Form()],
    visibility: Annotated[PackageVisibility, Form()] = PackageVisibility.PRIVATE,
) -> PackageRead:
    """Upload a ``.deb`` into a suite/component.

    Requires ``apt:write`` or ``apt:write:<component>``. The caller becomes
    the package owner; metadata is parsed from the archive before any write
    lands on disk.
    """
    caller = caller_from_auth(auth)
    scopes = set(caller.scopes)
    if not scope_rules.may_write(scopes, component):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required scope: apt:write or apt:write:{component}",
        )

    body = await deb.read()
    try:
        package = await save_upload(
            db,
            caller=caller,
            suite=suite,
            component=component,
            raw_body=body,
            visibility=visibility,
        )
    except UploadValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except UploadConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"package already exists: {exc.existing.id}",
        )
    return PackageRead.from_row(package)


@router.get("", response_model=list[PackageRead])
async def list_packages(
    auth: Auth,
    db: Annotated[AsyncSession, Depends(get_db)],
    suite: str | None = None,
    component: str | None = None,
    name: str | None = None,
) -> list[PackageRead]:
    """List packages visible to the caller."""
    caller = caller_from_auth(auth)
    stmt = select(Package).where(visible_package_filter(caller))
    if suite:
        stmt = stmt.where(Package.suite == suite)
    if component:
        stmt = stmt.where(Package.component == component)
    if name:
        stmt = stmt.where(Package.name == name)
    stmt = stmt.order_by(Package.name, Package.version)
    rows = (await db.execute(stmt)).scalars().all()
    return [PackageRead.from_row(r) for r in rows]


@router.get("/{package_id}", response_model=PackageRead)
async def get_package(
    auth: Auth,
    db: Annotated[AsyncSession, Depends(get_db)],
    package_id: uuid.UUID,
) -> PackageRead:
    """Return metadata for a single package."""
    package = await _load_package(db, package_id)
    if not can_read(caller_from_auth(auth), package):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="package not found")
    return PackageRead.from_row(package)


@router.patch("/{package_id}", response_model=PackageRead)
async def update_package(
    auth: Auth,
    db: Annotated[AsyncSession, Depends(get_db)],
    package_id: uuid.UUID,
    payload: PackageUpdate,
) -> PackageRead:
    """Update mutable fields (visibility, description)."""
    package = await _load_package(db, package_id)
    caller = caller_from_auth(auth)
    if not can_write(caller, package):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not allowed")

    if payload.visibility is not None:
        package.visibility = payload.visibility
    if payload.description is not None:
        package.description = payload.description
    await invalidate_index_cache(db)
    await db.commit()
    await db.refresh(package)
    return PackageRead.from_row(package)


@router.delete("/{package_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_package(
    auth: Auth,
    db: Annotated[AsyncSession, Depends(get_db)],
    package_id: uuid.UUID,
) -> None:
    """Delete a package and every ACL entry attached to it."""
    from apt_server.repo import pool

    package = await _load_package(db, package_id)
    caller = caller_from_auth(auth)
    if not can_write(caller, package):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not allowed")
    filename = package.filename
    await db.delete(package)
    await invalidate_index_cache(db)
    await db.commit()
    pool.delete_deb(filename)


@router.get("/{package_id}/acl", response_model=list[ACLGrantRead])
async def list_acl(
    auth: Auth,
    db: Annotated[AsyncSession, Depends(get_db)],
    package_id: uuid.UUID,
) -> list[ACLGrantRead]:
    """List ACL entries; only the owner and admins can see the full list."""
    package = await _load_package(db, package_id)
    caller = caller_from_auth(auth)
    if package.owner_id != caller.sub and not caller.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not allowed")
    return [ACLGrantRead.from_row(row) for row in package.acl]


@router.post(
    "/{package_id}/acl",
    response_model=ACLGrantRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_acl(
    auth: Auth,
    db: Annotated[AsyncSession, Depends(get_db)],
    package_id: uuid.UUID,
    payload: ACLGrantCreate,
) -> ACLGrantRead:
    """Grant a user or group a role on a package."""
    package = await _load_package(db, package_id)
    caller = caller_from_auth(auth)
    if package.owner_id != caller.sub and not caller.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not allowed")
    if bool(payload.grantee_user_id) == bool(payload.grantee_group):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="exactly one of grantee_user_id or grantee_group must be set",
        )
    entry = PackageACL(
        package_id=package.id,
        grantee_user_id=payload.grantee_user_id,
        grantee_group=payload.grantee_group,
        role=payload.role,
        granted_by=caller.display_name or caller.sub,
    )
    db.add(entry)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="duplicate ACL entry",
        )
    await invalidate_index_cache(db)
    await db.commit()
    await db.refresh(entry)
    return ACLGrantRead.from_row(entry)


@router.delete(
    "/{package_id}/acl/{acl_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_acl(
    auth: Auth,
    db: Annotated[AsyncSession, Depends(get_db)],
    package_id: uuid.UUID,
    acl_id: uuid.UUID,
) -> None:
    """Revoke an ACL entry."""
    package = await _load_package(db, package_id)
    caller = caller_from_auth(auth)
    if package.owner_id != caller.sub and not caller.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not allowed")
    row = next((entry for entry in package.acl if entry.id == acl_id), None)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="acl entry not found")
    await db.delete(row)
    await invalidate_index_cache(db)
    await db.commit()


async def _load_package(db: AsyncSession, package_id: uuid.UUID) -> Package:
    stmt = select(Package).where(Package.id == package_id).options(selectinload(Package.acl))
    package = (await db.execute(stmt)).scalar_one_or_none()
    if package is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="package not found")
    if package.component and not component_rules.is_known_component(package.component):
        # Defensive: a component was removed from config but rows still exist.
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"component {package.component} is no longer served",
        )
    return package
