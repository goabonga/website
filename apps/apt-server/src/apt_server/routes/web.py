# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Server-rendered pages: home, setup, package detail."""

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apt_server.acl.packages import can_read, visible_package_filter
from apt_server.config import settings
from apt_server.database import get_db
from apt_server.db.models import Package
from apt_server.services import user_cache
from apt_server.services.apt_auth import Caller_

router = APIRouter(tags=["web"], include_in_schema=False)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

PAGE_SIZE = 25


def _pagination_query_factory(request: Request):
    """Return a Jinja2 callable that builds a query string for a given page."""

    def pagination_query(page: int) -> str:
        params = dict(request.query_params)
        params["page"] = str(page)
        return "&".join(f"{k}={v}" for k, v in params.items() if v)

    return pagination_query


def _keyring_name(host: str) -> str:
    safe = host.replace(":", "-").replace(".", "-")
    return safe or "apt-server"


def _base_ctx(request: Request, caller, *, active_section: str = "") -> dict:
    return {
        "request": request,
        "app_name": settings.app_name,
        "caller": caller,
        "oauth_enabled": bool(settings.oauth2_issuer),
        "active_section": active_section,
        "pagination_query": _pagination_query_factory(request),
    }


async def _paginated_packages(
    db: AsyncSession,
    base_filter,
    *,
    suite: str | None,
    component: str | None,
    q: str | None,
    page: int,
) -> tuple[list, int, int]:
    """Return (packages, total_count, total_pages) for the given filters."""
    stmt = select(Package).where(base_filter)
    count_stmt = select(func.count()).select_from(Package).where(base_filter)

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
    return list(packages), total, total_pages


@router.get("/", response_class=HTMLResponse)
async def landing(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    caller: Caller_,
    suite: str | None = Query(default=None),
    component: str | None = Query(default=None),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
) -> HTMLResponse:
    """Home page: filtered + paginated package list."""
    packages, total, total_pages = await _paginated_packages(
        db, visible_package_filter(caller), suite=suite, component=component, q=q, page=page
    )

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            **_base_ctx(request, caller, active_section="home"),
            "suites": settings.apt_suites_list,
            "components": settings.apt_components_list,
            "public_components": settings.apt_public_components_list,
            "selected_suite": suite,
            "selected_component": component,
            "query": q,
            "packages": packages,
            "total": total,
            "page": page,
            "total_pages": total_pages,
        },
    )


@router.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request, caller: Caller_) -> HTMLResponse:
    """Dedicated setup documentation page."""
    host = request.url.hostname or "apt.example.com"
    return templates.TemplateResponse(
        request,
        "setup.html",
        {
            **_base_ctx(request, caller, active_section="setup"),
            "host": host,
            "keyring_name": _keyring_name(host),
            "default_suite": settings.apt_suites_list[0] if settings.apt_suites_list else "stable",
            "default_component": (
                settings.apt_public_components_list[0]
                if settings.apt_public_components_list
                else (settings.apt_components_list[0] if settings.apt_components_list else "main")
            ),
            "issuer": settings.oauth2_issuer.rstrip("/") if settings.oauth2_issuer else "",
        },
    )


@router.get("/packages/{package_id}", response_class=HTMLResponse)
async def package_detail(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    caller: Caller_,
    package_id: uuid.UUID,
) -> HTMLResponse:
    """Per-package detail page."""
    stmt = select(Package).where(Package.id == package_id).options(selectinload(Package.acl))
    package = (await db.execute(stmt)).scalar_one_or_none()
    if package is None or not can_read(caller, package):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="package not found")

    owner_display = await user_cache.resolve_display(db, package.owner_id)

    return templates.TemplateResponse(
        request,
        "package_detail.html",
        {
            **_base_ctx(request, caller),
            "package": package,
            "owner_display": owner_display,
        },
    )
