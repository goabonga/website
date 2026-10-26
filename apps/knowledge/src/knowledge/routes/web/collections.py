# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Collections web routes."""

import re
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.auth.dependencies import get_web_auth_context
from knowledge.auth.models import WebAuthContext
from knowledge.config import TEMPLATES_DIR
from knowledge.database import get_db
from knowledge.models import Collection, Document, Tenant, TenantMember
from knowledge.models.enums import OwnerType
from knowledge.services.quotas import QuotaExceededError, QuotaService

router = APIRouter(tags=["web-collections"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def slugify(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    # Convert to lowercase and replace spaces with hyphens
    slug = text.lower().strip()
    # Replace any non-alphanumeric characters (except hyphens) with hyphens
    slug = re.sub(r"[^a-z0-9-]", "-", slug)
    # Replace multiple consecutive hyphens with a single hyphen
    slug = re.sub(r"-+", "-", slug)
    # Remove leading/trailing hyphens
    slug = slug.strip("-")
    # Limit length
    return slug[:100] if slug else "collection"


def _display_content_size(document: Document) -> int:
    """Return a reliable content size for UI (fallback for legacy rows)."""
    if document.content_size and document.content_size > 0:
        return document.content_size
    return len((document.content or "").encode("utf-8"))


async def _get_common_context(
    request: Request,
    db: AsyncSession,
    auth_result: WebAuthContext,
) -> dict:
    """Get common template context."""
    user = auth_result.user
    tenant = auth_result.tenant

    # Get user's tenants for switcher
    result = await db.execute(
        select(Tenant)
        .join(TenantMember, Tenant.id == TenantMember.organization_id)
        .where(TenantMember.user_id == user.id, Tenant.is_active == True)  # noqa: E712
    )
    tenants = result.scalars().all()

    return {
        "user": user,
        "tenant": tenant,
        "tenant_member": auth_result.tenant_member,
        "tenants": tenants,
        "active_section": "collections",
    }


@router.get("", response_class=HTMLResponse)
async def list_collections(
    request: Request,
    page: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """List all collections for the current tenant."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    if not auth_result.tenant:
        return templates.TemplateResponse(
            request,
            "collections/list.html",
            {
                **(await _get_common_context(request, db, auth_result)),
                "collections": [],
                "total": 0,
                "page": 1,
                "total_pages": 1,
                "error": "No tenant selected",
            },
        )

    tenant = auth_result.tenant
    per_page = 20
    offset = (page - 1) * per_page

    # Get total count
    result = await db.execute(
        select(func.count(Collection.id)).where(Collection.organization_id == tenant.id)
    )
    total = result.scalar() or 0
    total_pages = (total + per_page - 1) // per_page

    # Get collections with document counts
    result = await db.execute(
        select(Collection)
        .where(Collection.organization_id == tenant.id)
        .order_by(Collection.updated_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    collections = result.scalars().all()

    # Get document counts for each collection
    collection_stats: dict[Any, int] = {}
    for collection in collections:
        result = await db.execute(
            select(func.count(Document.id)).where(Document.collection_id == collection.id)  # type: ignore[attr-defined]
        )
        collection_stats[collection.id] = int(result.scalar() or 0)  # type: ignore[attr-defined, arg-type]

    return templates.TemplateResponse(
        request,
        "collections/list.html",
        {
            **(await _get_common_context(request, db, auth_result)),
            "collections": collections,
            "collection_stats": collection_stats,
            "total": total,
            "page": page,
            "total_pages": total_pages,
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def new_collection_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Show form to create a new collection."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    return templates.TemplateResponse(
        request,
        "collections/form.html",
        {
            **(await _get_common_context(request, db, auth_result)),
            "collection": None,
            "is_edit": False,
        },
    )


@router.post("/new", response_class=HTMLResponse)
async def create_collection(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Create a new collection."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    if not auth_result.tenant:
        return templates.TemplateResponse(
            request,
            "collections/form.html",
            {
                **(await _get_common_context(request, db, auth_result)),
                "collection": None,
                "is_edit": False,
                "error": "No tenant selected",
            },
        )

    tenant = auth_result.tenant

    # Check quota
    quota_service = QuotaService(db)
    try:
        await quota_service.enforce_collection_quota(tenant)
    except QuotaExceededError as e:
        return templates.TemplateResponse(
            request,
            "collections/form.html",
            {
                **(await _get_common_context(request, db, auth_result)),
                "collection": None,
                "is_edit": False,
                "error": str(e),
                "form_name": name,
                "form_description": description,
            },
        )

    # A slug identifies a collection of the workspace
    slug = slugify(name)
    result = await db.execute(
        select(Collection).where(
            Collection.owner_type == OwnerType.ORGANIZATION,
            Collection.owner_id == tenant.id,
            Collection.slug == slug,
        )
    )
    if result.scalar_one_or_none() is not None:
        return templates.TemplateResponse(
            request,
            "collections/form.html",
            {
                **(await _get_common_context(request, db, auth_result)),
                "collection": None,
                "is_edit": False,
                "error": f"A collection named '{name}' already exists in this workspace.",
                "form_name": name,
                "form_description": description,
            },
            status_code=400,
        )

    # Create collection
    collection = Collection(
        owner_type=OwnerType.ORGANIZATION,
        owner_id=tenant.id,
        organization_id=tenant.id,  # For backward compatibility
        name=name,
        slug=slug,
        description=description or None,
    )
    db.add(collection)
    await db.commit()

    return RedirectResponse(
        url=f"/collections/{collection.id}",
        status_code=302,
    )


@router.get("/{collection_id}", response_class=HTMLResponse)
async def view_collection(
    request: Request,
    collection_id: UUID,
    page: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """View a collection and its documents."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    if not auth_result.tenant:
        return RedirectResponse(url="/collections", status_code=302)

    tenant = auth_result.tenant

    # Get collection
    result = await db.execute(
        select(Collection).where(
            Collection.id == collection_id,
            Collection.organization_id == tenant.id,
        )
    )
    collection = result.scalar_one_or_none()

    if not collection:
        return RedirectResponse(url="/collections", status_code=302)

    # Get documents with pagination
    per_page = 20
    offset = (page - 1) * per_page

    result = await db.execute(
        select(func.count(Document.id)).where(Document.collection_id == collection.id)
    )
    total: int = int(result.scalar() or 0)  # type: ignore[arg-type]
    total_pages = (total + per_page - 1) // per_page

    doc_result = await db.execute(
        select(Document)
        .where(Document.collection_id == collection.id)
        .order_by(Document.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    documents = doc_result.scalars().all()
    display_document_sizes = {
        document.id: _display_content_size(document) for document in documents
    }

    return templates.TemplateResponse(
        request,
        "collections/detail.html",
        {
            **(await _get_common_context(request, db, auth_result)),
            "collection": collection,
            "documents": documents,
            "display_document_sizes": display_document_sizes,
            "total": total,
            "page": page,
            "total_pages": total_pages,
        },
    )


@router.get("/{collection_id}/edit", response_class=HTMLResponse)
async def edit_collection_form(
    request: Request,
    collection_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Show form to edit a collection."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    if not auth_result.tenant:
        return RedirectResponse(url="/collections", status_code=302)

    tenant = auth_result.tenant

    # Get collection
    result = await db.execute(
        select(Collection).where(
            Collection.id == collection_id,
            Collection.organization_id == tenant.id,
        )
    )
    collection = result.scalar_one_or_none()

    if not collection:
        return RedirectResponse(url="/collections", status_code=302)

    return templates.TemplateResponse(
        request,
        "collections/form.html",
        {
            **(await _get_common_context(request, db, auth_result)),
            "collection": collection,
            "is_edit": True,
        },
    )


@router.post("/{collection_id}/edit", response_class=HTMLResponse)
async def update_collection(
    request: Request,
    collection_id: UUID,
    name: str = Form(...),
    description: str = Form(""),
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Update a collection."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    if not auth_result.tenant:
        return RedirectResponse(url="/collections", status_code=302)

    tenant = auth_result.tenant

    # Get collection
    result = await db.execute(
        select(Collection).where(
            Collection.id == collection_id,
            Collection.organization_id == tenant.id,
        )
    )
    collection = result.scalar_one_or_none()

    if not collection:
        return RedirectResponse(url="/collections", status_code=302)

    # Update collection
    collection.name = name
    collection.description = description or None
    await db.commit()

    return RedirectResponse(
        url=f"/collections/{collection.id}",
        status_code=302,
    )


@router.post("/{collection_id}/delete", response_class=HTMLResponse)
async def delete_collection(
    request: Request,
    collection_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Delete a collection."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    if not auth_result.tenant:
        return RedirectResponse(url="/collections", status_code=302)

    tenant = auth_result.tenant

    # Get collection
    result = await db.execute(
        select(Collection).where(
            Collection.id == collection_id,
            Collection.organization_id == tenant.id,
        )
    )
    collection = result.scalar_one_or_none()

    if collection:
        await db.delete(collection)
        await db.commit()

    return RedirectResponse(url="/collections", status_code=302)


@router.post("/{collection_id}/documents/delete", response_class=HTMLResponse)
async def delete_selected_documents(
    request: Request,
    collection_id: UUID,
    document_ids: list[UUID] = Form(default=[]),
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Delete selected documents from a collection."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    if not auth_result.tenant:
        return RedirectResponse(url="/collections", status_code=302)

    tenant = auth_result.tenant

    # Ensure collection belongs to current tenant
    result = await db.execute(
        select(Collection).where(
            Collection.id == collection_id,
            Collection.organization_id == tenant.id,
        )
    )
    collection = result.scalar_one_or_none()
    if not collection:
        return RedirectResponse(url="/collections", status_code=302)

    if document_ids:
        result = await db.execute(
            select(Document).where(
                Document.collection_id == collection.id,
                Document.id.in_(document_ids),
            )
        )
        documents = result.scalars().all()
        for document in documents:
            await db.delete(document)
        await db.commit()

    return RedirectResponse(url=f"/collections/{collection.id}", status_code=302)
