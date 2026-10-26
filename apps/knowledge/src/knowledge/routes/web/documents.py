# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Documents web routes."""

import hashlib
import logging
import math
import re
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.auth.dependencies import get_web_auth_context
from knowledge.auth.models import WebAuthContext
from knowledge.config import TEMPLATES_DIR
from knowledge.database import get_db
from knowledge.models import Collection, Document, Tenant, TenantMember
from knowledge.schemas.document import DocumentCreate
from knowledge.services.documents import DocumentService
from knowledge.services.embeddings import get_embedding_service
from knowledge.services.quotas import QuotaExceededError, QuotaService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["web-documents"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)

CHUNK_MODE_MARKDOWN_SECTIONS = "markdown_sections"
CHUNK_MODE_SPLIT_5 = "split_5"
CHUNK_MODE_SPLIT_10 = "split_10"


def _split_markdown_sections(content: str) -> list[str]:
    """Split markdown text by heading sections."""
    normalized = content.strip()
    if not normalized:
        return []

    heading_re = re.compile(r"^#{1,6}\s+.+$", re.MULTILINE)
    matches = list(heading_re.finditer(normalized))
    if not matches:
        return [normalized]

    chunks: list[str] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(normalized)
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
    return chunks or [normalized]


def _split_even_chunks(content: str, parts: int) -> list[str]:
    """Split content into N balanced chunks by words."""
    normalized = content.strip()
    if not normalized:
        return []
    if parts <= 1:
        return [normalized]

    words = normalized.split()
    if not words:
        return [normalized]

    chunk_size = max(1, math.ceil(len(words) / parts))
    chunks: list[str] = []
    for i in range(0, len(words), chunk_size):
        chunk = " ".join(words[i : i + chunk_size]).strip()
        if chunk:
            chunks.append(chunk)
    return chunks or [normalized]


def _chunk_content(content: str, chunk_mode: str | None) -> list[str]:
    """Chunk content according to selected mode."""
    if not chunk_mode:
        return [content.strip()] if content.strip() else []
    if chunk_mode == CHUNK_MODE_MARKDOWN_SECTIONS:
        return _split_markdown_sections(content)
    if chunk_mode == CHUNK_MODE_SPLIT_5:
        return _split_even_chunks(content, 5)
    if chunk_mode == CHUNK_MODE_SPLIT_10:
        return _split_even_chunks(content, 10)
    return [content.strip()] if content.strip() else []


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


@router.get("/{document_id}", response_class=HTMLResponse)
async def view_document(
    request: Request,
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """View a document's details."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    if not auth_result.tenant:
        return RedirectResponse(url="/collections", status_code=302)

    tenant = auth_result.tenant

    # Get document with collection check
    result = await db.execute(
        select(Document)
        .join(Collection, Document.collection_id == Collection.id)
        .where(
            Document.id == document_id,
            Collection.organization_id == tenant.id,
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        return RedirectResponse(url="/collections", status_code=302)

    # Get collection for breadcrumb
    result = await db.execute(select(Collection).where(Collection.id == document.collection_id))
    collection = result.scalar_one_or_none()

    return templates.TemplateResponse(
        request,
        "documents/detail.html",
        {
            **(await _get_common_context(request, db, auth_result)),
            "document": document,
            "collection": collection,
            "display_content_size": _display_content_size(document),
        },
    )


@router.get("/{collection_id}/new", response_class=HTMLResponse)
async def new_document_form(
    request: Request,
    collection_id: UUID,
    error: str = Query("", description="Error message from failed creation"),
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Show form to create a new document."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    if not auth_result.tenant:
        return RedirectResponse(url="/collections", status_code=302)

    tenant = auth_result.tenant

    # Verify collection belongs to tenant
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
        "documents/form.html",
        {
            **(await _get_common_context(request, db, auth_result)),
            "collection": collection,
            "document": None,
            "is_edit": False,
            "error": error if error else None,
        },
    )


@router.post("/{collection_id}/new", response_class=HTMLResponse)
async def create_document(
    request: Request,
    collection_id: UUID,
    content: str = Form(""),
    source_type: str = Form(""),
    source_ref: str = Form(""),
    file: UploadFile | None = File(default=None),
    enable_chunking: bool = Form(False),
    chunk_mode: str = Form(""),
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Create a new document with embedding generation via OpenAI."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    if not auth_result.tenant:
        return RedirectResponse(url="/collections", status_code=302)

    tenant = auth_result.tenant

    # Verify collection belongs to tenant
    result = await db.execute(
        select(Collection).where(
            Collection.id == collection_id,
            Collection.organization_id == tenant.id,
        )
    )
    collection = result.scalar_one_or_none()

    if not collection:
        return RedirectResponse(url="/collections", status_code=302)

    # Check quotas
    quota_service = QuotaService(db)
    try:
        await quota_service.enforce_document_quota(tenant, collection.id)
        await quota_service.enforce_storage_quota(tenant)
    except QuotaExceededError as e:
        return templates.TemplateResponse(
            request,
            "documents/form.html",
            {
                **(await _get_common_context(request, db, auth_result)),
                "collection": collection,
                "document": None,
                "is_edit": False,
                "error": str(e),
                "form_content": content,
                "form_source_type": source_type,
                "form_source_ref": source_ref,
            },
        )

    # Save collection_id before try block (in case of rollback detaching the object)
    collection_id = collection.id

    raw_content = content
    if file and file.filename:
        file_bytes = await file.read()
        try:
            raw_content = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raw_content = file_bytes.decode("utf-8", errors="replace")

        if not source_type:
            source_type = "file"
        if not source_ref:
            source_ref = file.filename

    if not raw_content.strip():
        return templates.TemplateResponse(
            request,
            "documents/form.html",
            {
                **(await _get_common_context(request, db, auth_result)),
                "collection": collection,
                "document": None,
                "is_edit": False,
                "error": "Content is required (text or uploaded file).",
                "form_content": content,
                "form_source_type": source_type,
                "form_source_ref": source_ref,
                "form_enable_chunking": enable_chunking,
                "form_chunk_mode": chunk_mode,
            },
            status_code=400,
        )

    chunks = _chunk_content(raw_content, chunk_mode if enable_chunking else None)
    if not chunks:
        chunks = [raw_content]

    # Create document using DocumentService (generates real embeddings via OpenAI)
    try:
        doc_service = DocumentService(db)
        for chunk in chunks:
            await quota_service.enforce_document_quota(tenant, collection.id)
            await quota_service.enforce_storage_quota(tenant)

            doc_data = DocumentCreate(
                content=chunk,
                source_type=source_type or None,
                source_ref=source_ref or None,
                metadata={
                    "chunked": enable_chunking,
                    "chunk_mode": chunk_mode if enable_chunking else None,
                    "chunk_count": len(chunks) if enable_chunking else 1,
                },
            )
            await doc_service.create(collection_id, doc_data)
        await db.commit()
    except Exception as e:
        logger.exception("Failed to create document with embedding")
        await db.rollback()
        # Redirect with error message to avoid session issues after rollback
        from urllib.parse import quote

        error_msg = quote(str(e)[:200])  # Limit error message length
        return RedirectResponse(
            url=f"/documents/{collection_id}/new?error={error_msg}",
            status_code=302,
        )

    return RedirectResponse(
        url=f"/collections/{collection_id}",
        status_code=302,
    )


@router.get("/{document_id}/edit", response_class=HTMLResponse)
async def edit_document_form(
    request: Request,
    document_id: UUID,
    error: str = Query("", description="Error message from failed update"),
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Show form to edit a document."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    if not auth_result.tenant:
        return RedirectResponse(url="/collections", status_code=302)

    tenant = auth_result.tenant

    # Get document with collection check
    result = await db.execute(
        select(Document)
        .join(Collection, Document.collection_id == Collection.id)
        .where(
            Document.id == document_id,
            Collection.organization_id == tenant.id,
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        return RedirectResponse(url="/collections", status_code=302)

    # Get collection
    result = await db.execute(select(Collection).where(Collection.id == document.collection_id))
    collection = result.scalar_one_or_none()

    return templates.TemplateResponse(
        request,
        "documents/form.html",
        {
            **(await _get_common_context(request, db, auth_result)),
            "collection": collection,
            "document": document,
            "is_edit": True,
            "error": error if error else None,
        },
    )


@router.post("/{document_id}/edit", response_class=HTMLResponse)
async def update_document(
    request: Request,
    document_id: UUID,
    content: str = Form(...),
    source_type: str = Form(""),
    source_ref: str = Form(""),
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Update a document and regenerate embedding if content changed."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    if not auth_result.tenant:
        return RedirectResponse(url="/collections", status_code=302)

    tenant = auth_result.tenant

    # Get document with collection check
    result = await db.execute(
        select(Document)
        .join(Collection, Document.collection_id == Collection.id)
        .where(
            Document.id == document_id,
            Collection.organization_id == tenant.id,
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        return RedirectResponse(url="/collections", status_code=302)

    # Get collection
    result = await db.execute(select(Collection).where(Collection.id == document.collection_id))
    collection = result.scalar_one_or_none()

    # Check storage quota for size difference
    new_size = len(content.encode("utf-8"))
    size_diff = new_size - document.content_size

    if size_diff > 0:
        quota_service = QuotaService(db)
        try:
            await quota_service.enforce_storage_quota(tenant)
        except QuotaExceededError as e:
            return templates.TemplateResponse(
                request,
                "documents/form.html",
                {
                    **(await _get_common_context(request, db, auth_result)),
                    "collection": collection,
                    "document": document,
                    "is_edit": True,
                    "error": str(e),
                },
            )

    # Check if content changed
    content_changed = document.content != content

    # Update document
    document.content = content
    document.content_hash = hashlib.sha256(content.encode()).hexdigest()
    document.content_size = new_size
    document.source_type = source_type or None
    document.source_ref = source_ref or None

    # Regenerate embedding if content changed
    if content_changed:
        try:
            embedding_service = get_embedding_service()
            document.embedding = await embedding_service.embed_text(content)
            document.embedding_size = len(document.embedding) * 4
        except Exception as e:
            logger.exception("Failed to regenerate embedding")
            await db.rollback()
            # Redirect with error message to avoid session issues after rollback
            from urllib.parse import quote

            error_msg = quote(str(e)[:200])
            return RedirectResponse(
                url=f"/documents/{document_id}/edit?error={error_msg}",
                status_code=302,
            )

    await db.commit()

    return RedirectResponse(
        url=f"/documents/{document.id}",
        status_code=302,
    )


@router.post("/{document_id}/delete", response_class=HTMLResponse)
async def delete_document(
    request: Request,
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Delete a document."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    if not auth_result.tenant:
        return RedirectResponse(url="/collections", status_code=302)

    tenant = auth_result.tenant

    # Get document with collection check
    result = await db.execute(
        select(Document)
        .join(Collection, Document.collection_id == Collection.id)
        .where(
            Document.id == document_id,
            Collection.organization_id == tenant.id,
        )
    )
    document = result.scalar_one_or_none()

    collection_id = document.collection_id if document else None

    if document:
        await db.delete(document)
        await db.commit()

    if collection_id:
        return RedirectResponse(url=f"/collections/{collection_id}", status_code=302)
    return RedirectResponse(url="/collections", status_code=302)
