# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Authenticated dashboard: upload, manage and share packages."""

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apt_server.acl.packages import Caller, can_write
from apt_server.config import settings
from apt_server.database import get_db
from apt_server.db.models import ACLRole, Package, PackageACL, PackageVisibility
from apt_server.services.apt_auth import Caller_
from apt_server.services.indexes import invalidate_index_cache
from apt_server.services.upload import UploadConflictError, UploadValidationError, save_upload

PAGE_SIZE = 25

router = APIRouter(prefix="/dashboard", tags=["dashboard"], include_in_schema=False)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _require_caller(caller: Caller | None) -> Caller:
    if caller is None:
        raise HTTPException(status_code=status.HTTP_302_FOUND, headers={"Location": "/login"})
    return caller


def _pagination_query_factory(request: Request):
    def pagination_query(page: int) -> str:
        params = dict(request.query_params)
        params["page"] = str(page)
        return "&".join(f"{k}={v}" for k, v in params.items() if v)

    return pagination_query


def _ctx(
    request: Request, caller: Caller, *, active_section: str = "dashboard", **extra: object
) -> dict:
    return {
        "request": request,
        "app_name": settings.app_name,
        "caller": caller,
        "oauth_enabled": True,
        "suites": settings.apt_suites_list,
        "components": settings.apt_components_list,
        "active_section": active_section,
        "pagination_query": _pagination_query_factory(request),
        **extra,
    }


@router.get("", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    caller: Caller_,
    suite: str | None = Query(default=None),
    component: str | None = Query(default=None),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
) -> HTMLResponse:
    """List the caller's own packages with filters and pagination."""
    user = _require_caller(caller)
    base = Package.owner_id == user.sub
    stmt = select(Package).where(base).options(selectinload(Package.acl))
    count_stmt = select(func.count()).select_from(Package).where(base)

    if suite:
        stmt = stmt.where(Package.suite == suite)
        count_stmt = count_stmt.where(Package.suite == suite)
    if component:
        stmt = stmt.where(Package.component == component)
        count_stmt = count_stmt.where(Package.component == component)
    if q:
        stmt = stmt.where(Package.name.ilike(f"%{q}%"))
        count_stmt = count_stmt.where(Package.name.ilike(f"%{q}%"))

    total = (await db.execute(count_stmt)).scalar() or 0
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(1, min(page, total_pages))

    stmt = (
        stmt.order_by(Package.name, Package.version).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
    )
    packages = (await db.execute(stmt)).scalars().all()

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        _ctx(
            request,
            user,
            packages=packages,
            total=total,
            page=page,
            total_pages=total_pages,
            selected_suite=suite,
            selected_component=component,
            query=q,
        ),
    )


@router.get("/upload", response_class=HTMLResponse)
async def upload_form(request: Request, caller: Caller_) -> HTMLResponse:
    """Render the upload form."""
    user = _require_caller(caller)
    return templates.TemplateResponse(
        request,
        "upload.html",
        _ctx(request, user, active_section="upload", chunk_size=settings.upload_chunk_size),
    )


@router.post("/upload")
async def upload_action(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    caller: Caller_,
    deb: UploadFile,
    suite: Annotated[str, Form()],
    component: Annotated[str, Form()],
    visibility: Annotated[str, Form()] = "private",
) -> RedirectResponse:
    """Handle the upload form submission."""
    user = _require_caller(caller)
    body = await deb.read()
    vis = (
        PackageVisibility(visibility)
        if visibility in ("public", "private", "shared")
        else PackageVisibility.PRIVATE
    )
    try:
        await save_upload(
            db, caller=user, suite=suite, component=component, raw_body=body, visibility=vis
        )
    except UploadValidationError as exc:
        return templates.TemplateResponse(
            request,
            "upload.html",
            _ctx(request, user, error=str(exc)),
            status_code=400,
        )
    except UploadConflictError:
        return templates.TemplateResponse(
            request,
            "upload.html",
            _ctx(
                request,
                user,
                error="A package with the same name, version and architecture already exists in this suite/component.",
            ),
            status_code=409,
        )
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{package_id}/delete")
async def delete_action(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    caller: Caller_,
    package_id: uuid.UUID,
) -> RedirectResponse:
    """Delete a package (POST from the dashboard)."""
    from apt_server.repo import pool

    user = _require_caller(caller)
    package = await _load_owned(db, package_id, user)
    filename = package.filename
    await db.delete(package)
    await invalidate_index_cache(db)
    await db.commit()
    pool.delete_deb(filename)
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{package_id}/visibility")
async def visibility_action(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    caller: Caller_,
    package_id: uuid.UUID,
    visibility: Annotated[str, Form()],
) -> RedirectResponse:
    """Change visibility of a package."""
    user = _require_caller(caller)
    package = await _load_owned(db, package_id, user)
    if visibility in ("public", "private", "shared"):
        package.visibility = PackageVisibility(visibility)
        await invalidate_index_cache(db)
        await db.commit()
    return RedirectResponse(
        url=f"/dashboard/{package_id}/share", status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/{package_id}/share", response_class=HTMLResponse)
async def share_form(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    caller: Caller_,
    package_id: uuid.UUID,
) -> HTMLResponse:
    """Render the share/ACL management page for a package."""
    user = _require_caller(caller)
    package = await _load_owned(db, package_id, user)
    return templates.TemplateResponse(request, "share.html", _ctx(request, user, package=package))


@router.post("/{package_id}/share")
async def share_action(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    caller: Caller_,
    package_id: uuid.UUID,
    grantee: Annotated[str, Form()],
    grantee_type: Annotated[str, Form()] = "user",
    role: Annotated[str, Form()] = "read",
) -> RedirectResponse:
    """Grant access to a user or group."""
    user = _require_caller(caller)
    package = await _load_owned(db, package_id, user)
    acl_role = ACLRole(role) if role in ("read", "write") else ACLRole.READ
    grantee_value = grantee.strip()
    entry = PackageACL(
        package_id=package.id,
        grantee_user_id=grantee_value if grantee_type == "user" else None,
        grantee_group=grantee_value if grantee_type == "group" else None,
        role=acl_role,
        granted_by=user.display_name or user.sub,
    )
    db.add(entry)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return templates.TemplateResponse(
            request,
            "share.html",
            _ctx(request, user, package=package, error="This grant already exists."),
            status_code=409,
        )
    await invalidate_index_cache(db)
    await db.commit()

    return RedirectResponse(
        url=f"/dashboard/{package_id}/share", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/{package_id}/revoke/{acl_id}")
async def revoke_action(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    caller: Caller_,
    package_id: uuid.UUID,
    acl_id: uuid.UUID,
) -> RedirectResponse:
    """Revoke an ACL entry."""
    user = _require_caller(caller)
    package = await _load_owned(db, package_id, user)
    row = next((e for e in package.acl if e.id == acl_id), None)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="acl entry not found")
    await db.delete(row)
    await invalidate_index_cache(db)
    await db.commit()
    return RedirectResponse(
        url=f"/dashboard/{package_id}/share", status_code=status.HTTP_303_SEE_OTHER
    )


async def _load_owned(db: AsyncSession, package_id: uuid.UUID, caller: Caller) -> Package:
    stmt = select(Package).where(Package.id == package_id).options(selectinload(Package.acl))
    package = (await db.execute(stmt)).scalar_one_or_none()
    if package is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="package not found")
    if not can_write(caller, package):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not allowed")
    return package
