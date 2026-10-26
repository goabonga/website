# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Routes consumed by ``apt`` clients.

Every request walks through layer 1 (component visibility), layer 2
(caller identity, introspected from the ``Authorization`` header) and
layer 3 (per-package ACL). Downloads never stream the ``.deb`` body
through Python: FastAPI replies with ``X-Accel-Redirect`` and nginx
performs the actual transfer via ``sendfile(2)`` from its ``internal``
location.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apt_server.acl import components as component_rules
from apt_server.acl.packages import Caller, can_read
from apt_server.config import settings
from apt_server.database import get_db
from apt_server.db.models import Package
from apt_server.repo import release
from apt_server.services.apt_auth import BASIC_REALM, Caller_
from apt_server.services.indexes import render_packages, render_release

router = APIRouter(tags=["apt"])


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="authentication required",
        headers={"WWW-Authenticate": BASIC_REALM},
    )


def _internal_redirect(relative_path: str) -> Response:
    """Return a 200 with ``X-Accel-Redirect`` pointing at the nginx internal alias."""
    prefix = settings.apt_internal_prefix.rstrip("/")
    target = f"{prefix}/{relative_path.lstrip('/')}"
    return Response(
        status_code=status.HTTP_200_OK,
        headers={
            "X-Accel-Redirect": target,
            "Content-Type": "application/octet-stream",
            "Cache-Control": "no-cache",
        },
    )


def _ensure_suite(suite: str) -> None:
    if suite not in settings.apt_suites_list:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="suite not found")


def _ensure_architecture(arch: str) -> None:
    if arch not in settings.apt_architectures_list and arch != "all":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="architecture not supported",
        )


def _gate_component(component: str, caller: Caller | None) -> None:
    """Apply layer 1 + layer 2: component visibility and caller identity."""
    if not component_rules.is_known_component(component):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="component not found")
    if not component_rules.is_public_component(component) and caller is None:
        raise _unauthorized()


@router.get("/pubkey.gpg", include_in_schema=False)
async def pubkey() -> Response:
    """Export the GPG public key used to sign ``Release``.

    Relies on ``gpg --armor --export <key_id>``. When the key id is empty we
    return a 404 so clients know the repository is unsigned.
    """
    if not settings.apt_gpg_key_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no signing key configured"
        )
    import subprocess

    result = subprocess.run(
        ["/usr/bin/gpg", "--armor", "--export", settings.apt_gpg_key_id],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="signing key not exportable"
        )
    return Response(content=result.stdout, media_type="application/pgp-keys")


@router.get("/dists/{suite}/Release", include_in_schema=False)
async def serve_release(
    suite: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    caller: Caller_,
) -> Response:
    _ensure_suite(suite)
    body = await render_release(db, caller, suite=suite)
    return Response(content=body, media_type="text/plain")


@router.get("/dists/{suite}/InRelease", include_in_schema=False)
async def serve_inrelease(
    suite: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    caller: Caller_,
) -> Response:
    _ensure_suite(suite)
    body = await render_release(db, caller, suite=suite)
    signed = release.sign_clearsigned(body)
    return Response(content=signed, media_type="text/plain")


@router.get("/dists/{suite}/Release.gpg", include_in_schema=False)
async def serve_release_gpg(
    suite: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    caller: Caller_,
) -> Response:
    _ensure_suite(suite)
    body = await render_release(db, caller, suite=suite)
    signature = release.sign_detached(body)
    if not signature:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="release not signed")
    return Response(content=signature, media_type="application/pgp-signature")


@router.get(
    "/dists/{suite}/{component}/binary-{architecture}/Packages",
    include_in_schema=False,
)
async def serve_packages(
    suite: str,
    component: str,
    architecture: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    caller: Caller_,
) -> PlainTextResponse:
    _ensure_suite(suite)
    _gate_component(component, caller)
    _ensure_architecture(architecture)
    body = await render_packages(
        db, caller, suite=suite, component=component, architecture=architecture, gzip=False
    )
    return PlainTextResponse(content=body)


@router.get(
    "/dists/{suite}/{component}/binary-{architecture}/Packages.gz",
    include_in_schema=False,
)
async def serve_packages_gz(
    suite: str,
    component: str,
    architecture: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    caller: Caller_,
) -> Response:
    _ensure_suite(suite)
    _gate_component(component, caller)
    _ensure_architecture(architecture)
    body = await render_packages(
        db, caller, suite=suite, component=component, architecture=architecture, gzip=True
    )
    return Response(content=body, media_type="application/gzip")


@router.get("/pool/{component}/{prefix}/{name}/{filename}", include_in_schema=False)
async def serve_pool(
    component: str,
    prefix: Annotated[str, Path(min_length=1, max_length=8)],
    name: str,
    filename: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    caller: Caller_,
) -> Response:
    """Serve a ``.deb`` via ``X-Accel-Redirect`` after the ACL check.

    The DB row is the source of truth: the pool path is reconstructed from
    ``packages.filename`` and matched against the request path, so a 404 is
    returned for unknown (or filtered) packages without disclosing whether
    the file exists on disk.
    """
    _gate_component(component, caller)
    relative = f"pool/{component}/{prefix}/{name}/{filename}"
    stmt = select(Package).where(Package.filename == relative).options(selectinload(Package.acl))
    package = (await db.execute(stmt)).scalar_one_or_none()
    if package is None or not can_read(caller, package):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    return _internal_redirect(relative)
