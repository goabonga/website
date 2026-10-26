# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Admin scopes management HTML pages."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db, get_templates, get_user_admin_permissions, require_scope
from auth.db.models.rbac import ADMIN_SCOPES, Role, Scope
from auth.db.models.user import User
from auth.services.scope import scope_service as _scope_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scopes")

# Scope dependencies - scopes management uses the scopes:* permissions
require_scopes_read = require_scope("scopes:read", redirect_to_login=True)
require_scopes_write = require_scope("scopes:write", redirect_to_login=True)
require_scopes_delete = require_scope("scopes:delete", redirect_to_login=True)


def scope_to_dict(scope: Scope, role_count: int = 0) -> dict:
    """Convert Scope model to dictionary format."""
    return {
        "id": str(scope.id),
        "name": scope.name,
        "description": scope.description,
        "resource": scope.resource,
        "action": scope.action,
        "category": scope.category,
        "is_system": scope.is_system,
        "is_active": scope.is_active,
        "role_count": role_count,
        "created_at": scope.created_at.isoformat() if scope.created_at else None,
        "updated_at": scope.updated_at.isoformat() if scope.updated_at else None,
    }


@router.get("", response_class=HTMLResponse)
async def scopes_list_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_scopes_read)],
    page: Annotated[int, Query(ge=1)] = 1,
    search: Annotated[str | None, Query(max_length=255)] = None,
    category: Annotated[str | None, Query(max_length=50)] = None,
    is_active: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    """Scopes list page."""
    logger.debug("Admin page: listing scopes")
    templates = get_templates()

    page_size = 20

    # Resolve is_active tri-state from the query-string representation.
    is_active_filter: bool | None = None
    if is_active == "true":
        is_active_filter = True
    elif is_active == "false":
        is_active_filter = False

    scopes, total = await _scope_service.list(
        db,
        page=page,
        page_size=page_size,
        search=search,
        category=category,
        is_active=is_active_filter,
        order_by_created_desc=False,
    )

    scopes_list = []
    for scope in scopes:
        role_count = await _scope_service.count_roles_for_scope(db, scope.id)
        scopes_list.append(scope_to_dict(scope, role_count))

    total_pages = (total + page_size - 1) // page_size

    categories = await _scope_service.list_distinct_categories(db)

    success = request.query_params.get("success")
    error = request.query_params.get("error")

    user, roles = auth
    permissions = get_user_admin_permissions(roles)

    return templates.TemplateResponse(
        request=request,
        name="admin/scopes/list.html",
        context={
            "active_section": "scopes",
            "scopes": scopes_list,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "search": search or "",
            "category": category or "",
            "is_active": is_active or "",
            "categories": categories,
            "success": success,
            "error": error,
            "permissions": permissions,
        },
    )


@router.get("/create", response_class=HTMLResponse)
async def scope_create_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_scopes_write)],
) -> HTMLResponse:
    """Scope creation form page."""
    logger.debug("Admin page: create scope form")
    templates = get_templates()

    error = request.query_params.get("error")

    categories = await _scope_service.list_distinct_categories(db)

    user, roles = auth
    permissions = get_user_admin_permissions(roles)

    return templates.TemplateResponse(
        request=request,
        name="admin/scopes/create.html",
        context={
            "active_section": "scopes",
            "categories": categories,
            "error": error,
            "permissions": permissions,
        },
    )


@router.post("/create", response_class=RedirectResponse)
async def scope_create_submit(
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_scopes_write)],
    name: Annotated[str, Form()],
    resource: Annotated[str, Form()],
    action: Annotated[str, Form()],
    category: Annotated[str, Form()] = "custom",
    description: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    """Handle scope creation form submission."""
    logger.debug("Admin page: creating scope name=%s", name)

    if await _scope_service.name_exists(db, name):
        return RedirectResponse(
            url="/admin/scopes/create?error=Scope+name+already+exists",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        scope = Scope(
            name=name,
            description=description or None,
            resource=resource,
            action=action,
            category=category,
            is_system=False,
            is_active=True,
        )
        await _scope_service.stage(db, scope)
        await db.commit()
        await db.refresh(scope)

        logger.info("Admin page: created scope id=%s name=%s", scope.id, scope.name)
        return RedirectResponse(
            url=f"/admin/scopes/{scope.id}?success=Scope+created+successfully",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        logger.error("Admin page: failed to create scope: %s", e)
        return RedirectResponse(
            url=f"/admin/scopes/create?error={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


@router.get("/{scope_id}", response_class=HTMLResponse)
async def scope_detail_page(
    request: Request,
    scope_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_scopes_read)],
) -> HTMLResponse:
    """Scope detail page."""
    logger.debug("Admin page: viewing scope id=%s", scope_id)
    templates = get_templates()

    try:
        scope_uuid = uuid.UUID(scope_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid scope ID format",
        )

    scope = await _scope_service.get_by_id(db, scope_uuid)

    if not scope:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scope not found",
        )

    roles = await _scope_service.list_roles_for_scope(db, scope_uuid)

    roles_list = [
        {
            "id": str(role.id),
            "name": role.name,
            "description": role.description,
            "is_system": role.is_system,
        }
        for role in roles
    ]

    scope_dict = scope_to_dict(scope, len(roles_list))
    scope_dict["roles"] = roles_list

    success = request.query_params.get("success")
    error = request.query_params.get("error")

    user, auth_roles = auth
    permissions = get_user_admin_permissions(auth_roles)

    return templates.TemplateResponse(
        request=request,
        name="admin/scopes/detail.html",
        context={
            "active_section": "scopes",
            "scope": scope_dict,
            "success": success,
            "error": error,
            "permissions": permissions,
        },
    )


@router.post("/{scope_id}/toggle", response_class=RedirectResponse)
async def scope_toggle_submit(
    scope_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_scopes_write)],
) -> RedirectResponse:
    """Handle scope enable/disable toggle."""
    logger.debug("Admin page: toggling scope id=%s", scope_id)

    try:
        scope_uuid = uuid.UUID(scope_id)
    except ValueError:
        return RedirectResponse(
            url="/admin/scopes?error=Invalid+scope+ID+format",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    scope = await _scope_service.get_by_id(db, scope_uuid)

    if not scope:
        return RedirectResponse(
            url="/admin/scopes?error=Scope+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if scope.is_system:
        return RedirectResponse(
            url=f"/admin/scopes/{scope_id}?error=Cannot+toggle+system+scopes",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    scope.is_active = not scope.is_active
    await db.commit()

    action = "enabled" if scope.is_active else "disabled"
    logger.info("Admin page: %s scope id=%s", action, scope_id)
    return RedirectResponse(
        url=f"/admin/scopes/{scope_id}?success=Scope+{action}+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{scope_id}/delete", response_class=RedirectResponse)
async def scope_delete_submit(
    scope_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_scopes_delete)],
) -> RedirectResponse:
    """Handle scope deletion."""
    logger.debug("Admin page: deleting scope id=%s", scope_id)

    try:
        scope_uuid = uuid.UUID(scope_id)
    except ValueError:
        return RedirectResponse(
            url="/admin/scopes?error=Invalid+scope+ID+format",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    scope = await _scope_service.get_by_id(db, scope_uuid)

    if not scope:
        return RedirectResponse(
            url="/admin/scopes?error=Scope+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if scope.is_system:
        return RedirectResponse(
            url=f"/admin/scopes/{scope_id}?error=Cannot+delete+system+scopes",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    await _scope_service.delete(db, scope)
    await db.commit()

    logger.info("Admin page: deleted scope id=%s", scope_id)
    return RedirectResponse(
        url="/admin/scopes?success=Scope+deleted+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/seed", response_class=RedirectResponse)
async def seed_default_scopes_submit(
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_scopes_write)],
) -> RedirectResponse:
    """Seed default system scopes."""
    logger.debug("Admin page: seeding default scopes")

    created = []
    for name, description in ADMIN_SCOPES.items():
        if await _scope_service.name_exists(db, name):
            logger.debug("Scope %s already exists, skipping", name)
            continue

        # Parse resource:action from name
        parts = name.split(":")
        resource = parts[0]
        action = parts[1] if len(parts) > 1 else "*"

        scope = Scope(
            name=name,
            description=description,
            resource=resource,
            action=action,
            category="admin",
            is_system=True,
            is_active=True,
        )
        await _scope_service.stage(db, scope)
        created.append(name)

    await db.commit()

    logger.info("Admin page: seeded %d default scopes", len(created))

    if created:
        return RedirectResponse(
            url=f"/admin/scopes?success=Created+{len(created)}+scope(s)",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url="/admin/scopes?success=All+default+scopes+already+exist",
        status_code=status.HTTP_303_SEE_OTHER,
    )
