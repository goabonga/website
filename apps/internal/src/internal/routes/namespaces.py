# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Knowledge Namespace CRUD routes.

Scopes required:
- namespaces:read - View namespaces
- namespaces:write - Create, update namespaces
- namespaces:delete - Delete namespaces
"""

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from internal import TEMPLATES_DIR
from internal.auth.dependencies import (
    require_resource_scopes_or_redirect,
    require_scope_or_redirect,
)
from internal.auth.models import User
from internal.config import settings
from internal.database import get_db
from internal.logging import get_logger
from internal.models.knowledge import KnowledgeNamespace

router = APIRouter(prefix="/namespaces", tags=["namespaces"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)
logger = get_logger(__name__)

# Use resource-level scope request to get all permissions at once for proper UI display
# Also request vpn:admin to show VPN link in navigation if user has permission
require_read = require_resource_scopes_or_redirect(
    "namespaces", extra_scopes=["vpn:admin", "billing:read"]
)
require_write = require_scope_or_redirect("namespaces:write")
require_delete = require_scope_or_redirect("namespaces:delete")

DEFAULT_NAMESPACE_SLUG = "general"


async def ensure_default_namespace(db: AsyncSession) -> KnowledgeNamespace:
    """Ensure the default 'general' namespace exists."""
    result = await db.execute(
        select(KnowledgeNamespace).where(KnowledgeNamespace.slug == DEFAULT_NAMESPACE_SLUG)
    )
    namespace = result.scalar_one_or_none()

    if not namespace:
        namespace = KnowledgeNamespace(
            slug=DEFAULT_NAMESPACE_SLUG,
            name="General",
            description="Default namespace for general knowledge entries",
            is_public=True,
        )
        db.add(namespace)
        await db.commit()
        await db.refresh(namespace)
        logger.info("Created default namespace: %s", DEFAULT_NAMESPACE_SLUG)

    return namespace


@router.get("", response_class=HTMLResponse)
async def namespace_list(
    request: Request,
    page: int = Query(1, ge=1),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_read),
):
    """List all namespaces with pagination and search."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info(
        "Namespace list accessed | user_id=%s client_id=%s page=%d search=%s",
        user.id,
        settings.oauth2_client_id,
        page,
        search,
    )

    # Ensure default namespace exists
    await ensure_default_namespace(db)

    limit = 20
    offset = (page - 1) * limit

    # Build base query
    base_query = select(KnowledgeNamespace)

    # Apply search filter
    if search:
        search_pattern = f"%{search}%"
        base_query = base_query.where(
            KnowledgeNamespace.name.ilike(search_pattern)
            | KnowledgeNamespace.slug.ilike(search_pattern)
            | KnowledgeNamespace.description.ilike(search_pattern)
        )

    # Count total
    count_query = select(func.count()).select_from(
        base_query.with_only_columns(KnowledgeNamespace.id).subquery()
    )
    total = await db.scalar(count_query) or 0
    total_pages = (total + limit - 1) // limit if total > 0 else 1

    # Get paginated results
    query = base_query.order_by(KnowledgeNamespace.name).offset(offset).limit(limit)
    result = await db.execute(query)
    namespaces = list(result.scalars().all())

    return templates.TemplateResponse(
        request=request,
        name="admin/namespaces/list.html",
        context={
            "request": request,
            "active_section": "namespaces",
            "user": user,
            "namespaces": namespaces,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "search": search,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def namespace_new(
    request: Request,
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Show form to create a new namespace."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info(
        "Namespace new form accessed | user_id=%s client_id=%s",
        user.id,
        settings.oauth2_client_id,
    )

    return templates.TemplateResponse(
        request=request,
        name="admin/namespaces/form.html",
        context={
            "request": request,
            "active_section": "namespaces",
            "user": user,
            "namespace": None,
            "is_edit": False,
        },
    )


@router.post("/new")
async def namespace_create(
    request: Request,
    slug: str = Form(...),
    name: str = Form(...),
    description: str = Form(""),
    required_scopes: str = Form(""),
    is_public: bool = Form(True),
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Create a new namespace."""
    if not isinstance(auth_result, User):
        return auth_result

    slug = slug.strip().lower()
    name = name.strip()
    desc_val = description.strip() or None

    # Parse scopes (comma-separated)
    scopes_list = None
    if required_scopes.strip():
        scopes_list = [s.strip() for s in required_scopes.split(",") if s.strip()]

    # Check if slug already exists
    result = await db.execute(select(KnowledgeNamespace).where(KnowledgeNamespace.slug == slug))
    if result.scalar_one_or_none():
        return RedirectResponse(
            url=f"/namespaces/new?error=Namespace+with+slug+'{slug}'+already+exists",
            status_code=303,
        )

    # Create namespace
    namespace = KnowledgeNamespace(
        slug=slug,
        name=name,
        description=desc_val,
        required_scopes=scopes_list,
        is_public=is_public,
    )
    db.add(namespace)
    await db.commit()

    logger.info(
        "Namespace created | user_id=%s client_id=%s namespace_id=%s slug=%s",
        auth_result.id,
        settings.oauth2_client_id,
        namespace.id,
        namespace.slug,
    )

    return RedirectResponse(
        url="/namespaces?success=Namespace+created+successfully",
        status_code=303,
    )


@router.get("/{namespace_id}", response_class=HTMLResponse)
async def namespace_detail(
    request: Request,
    namespace_id: int,
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_read),
):
    """View namespace detail."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info(
        "Namespace detail accessed | user_id=%s client_id=%s namespace_id=%s",
        user.id,
        settings.oauth2_client_id,
        namespace_id,
    )

    result = await db.execute(
        select(KnowledgeNamespace).where(KnowledgeNamespace.id == namespace_id)
    )
    namespace = result.scalar_one_or_none()

    if not namespace:
        return RedirectResponse(
            url="/namespaces?error=Namespace+not+found",
            status_code=303,
        )

    # Count entries in this namespace
    from internal.models.knowledge import KnowledgeEntry

    count_result = await db.execute(
        select(func.count())
        .select_from(KnowledgeEntry)
        .where(KnowledgeEntry.namespace_id == namespace_id)
    )
    entry_count = count_result.scalar() or 0

    return templates.TemplateResponse(
        request=request,
        name="admin/namespaces/detail.html",
        context={
            "request": request,
            "active_section": "namespaces",
            "user": user,
            "namespace": namespace,
            "entry_count": entry_count,
        },
    )


@router.get("/{namespace_id}/edit", response_class=HTMLResponse)
async def namespace_edit(
    request: Request,
    namespace_id: int,
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Show form to edit a namespace."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info(
        "Namespace edit form accessed | user_id=%s client_id=%s namespace_id=%s",
        user.id,
        settings.oauth2_client_id,
        namespace_id,
    )

    result = await db.execute(
        select(KnowledgeNamespace).where(KnowledgeNamespace.id == namespace_id)
    )
    namespace = result.scalar_one_or_none()

    if not namespace:
        return RedirectResponse(
            url="/namespaces?error=Namespace+not+found",
            status_code=303,
        )

    return templates.TemplateResponse(
        request=request,
        name="admin/namespaces/form.html",
        context={
            "request": request,
            "active_section": "namespaces",
            "user": user,
            "namespace": namespace,
            "is_edit": True,
        },
    )


@router.post("/{namespace_id}/edit")
async def namespace_update(
    request: Request,
    namespace_id: int,
    slug: str = Form(...),
    name: str = Form(...),
    description: str = Form(""),
    required_scopes: str = Form(""),
    is_public: bool = Form(True),
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Update a namespace."""
    if not isinstance(auth_result, User):
        return auth_result

    result = await db.execute(
        select(KnowledgeNamespace).where(KnowledgeNamespace.id == namespace_id)
    )
    namespace = result.scalar_one_or_none()

    if not namespace:
        return RedirectResponse(
            url="/namespaces?error=Namespace+not+found",
            status_code=303,
        )

    slug = slug.strip().lower()
    name = name.strip()
    desc_val = description.strip() or None

    # Parse scopes (comma-separated)
    scopes_list = None
    if required_scopes.strip():
        scopes_list = [s.strip() for s in required_scopes.split(",") if s.strip()]

    # Check if new slug conflicts with another namespace
    if slug != namespace.slug:
        existing = await db.execute(
            select(KnowledgeNamespace).where(KnowledgeNamespace.slug == slug)
        )
        if existing.scalar_one_or_none():
            return RedirectResponse(
                url=f"/namespaces/{namespace_id}/edit?error=Namespace+with+slug+'{slug}'+already+exists",
                status_code=303,
            )

    # Update namespace
    namespace.slug = slug
    namespace.name = name
    namespace.description = desc_val
    namespace.required_scopes = scopes_list
    namespace.is_public = is_public

    await db.commit()

    logger.info(
        "Namespace updated | user_id=%s client_id=%s namespace_id=%s slug=%s",
        auth_result.id,
        settings.oauth2_client_id,
        namespace.id,
        namespace.slug,
    )

    return RedirectResponse(
        url=f"/namespaces/{namespace_id}?success=Namespace+updated+successfully",
        status_code=303,
    )


@router.post("/bulk-delete")
async def namespace_bulk_delete(
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_delete),
):
    """Delete multiple namespaces."""
    if not isinstance(auth_result, User):
        return auth_result

    form = await request.form()
    namespace_ids_raw = form.getlist("namespace_ids")

    if not namespace_ids_raw:
        return RedirectResponse(
            url="/namespaces?error=No+namespaces+selected",
            status_code=303,
        )

    # The page sends the selection as one comma-separated value
    try:
        namespace_ids = [
            int(id_str)
            for raw in namespace_ids_raw
            for id_str in str(raw).replace(" ", "").split(",")
            if id_str
        ]
    except ValueError:
        return RedirectResponse(
            url="/namespaces?error=Invalid+namespace+IDs",
            status_code=303,
        )

    result = await db.execute(
        select(KnowledgeNamespace).where(KnowledgeNamespace.id.in_(namespace_ids))
    )
    namespaces = result.scalars().all()

    if not namespaces:
        return RedirectResponse(
            url="/namespaces?error=No+namespaces+found",
            status_code=303,
        )

    deleted_count = 0
    skipped_default = 0
    for namespace in namespaces:
        if namespace.slug == DEFAULT_NAMESPACE_SLUG:
            skipped_default += 1
            continue
        await db.delete(namespace)
        deleted_count += 1

    await db.commit()

    logger.info(
        "Namespaces bulk deleted | user_id=%s client_id=%s deleted_count=%d skipped_default=%d",
        auth_result.id,
        settings.oauth2_client_id,
        deleted_count,
        skipped_default,
    )

    if skipped_default > 0:
        return RedirectResponse(
            url=f"/namespaces?success={deleted_count}+namespace(s)+deleted,+{skipped_default}+skipped+(default)",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/namespaces?success={deleted_count}+namespace(s)+deleted+successfully",
        status_code=303,
    )


@router.post("/{namespace_id}/delete")
async def namespace_delete(
    request: Request,
    namespace_id: int,
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_delete),
):
    """Delete a namespace."""
    if not isinstance(auth_result, User):
        return auth_result

    result = await db.execute(
        select(KnowledgeNamespace).where(KnowledgeNamespace.id == namespace_id)
    )
    namespace = result.scalar_one_or_none()

    if not namespace:
        return RedirectResponse(
            url="/namespaces?error=Namespace+not+found",
            status_code=303,
        )

    # Prevent deleting the default namespace
    if namespace.slug == DEFAULT_NAMESPACE_SLUG:
        return RedirectResponse(
            url="/namespaces?error=Cannot+delete+the+default+namespace",
            status_code=303,
        )

    await db.delete(namespace)
    await db.commit()

    logger.info(
        "Namespace deleted | user_id=%s client_id=%s namespace_id=%s slug=%s",
        auth_result.id,
        settings.oauth2_client_id,
        namespace_id,
        namespace.slug,
    )

    return RedirectResponse(
        url="/namespaces?success=Namespace+deleted+successfully",
        status_code=303,
    )
