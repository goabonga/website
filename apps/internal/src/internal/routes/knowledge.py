# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Knowledge Base CRUD routes for RAG management.

Scopes required:
- knowledge:read - View knowledge entries
- knowledge:write - Create, update knowledge entries
- knowledge:delete - Delete knowledge entries
"""

import json

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
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
from internal.models.knowledge import KnowledgeEntry, KnowledgeEntryStatus, KnowledgeNamespace
from internal.services.embeddings import EmbeddingService

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)
logger = get_logger(__name__)

# Use resource-level scope request to get all permissions at once for proper UI display
# Also request vpn:admin to show VPN link in navigation if user has permission
require_read = require_resource_scopes_or_redirect(
    "knowledge", extra_scopes=["vpn:admin", "billing:read"]
)
require_write = require_scope_or_redirect("knowledge:write")
require_delete = require_scope_or_redirect("knowledge:delete")

DEFAULT_NAMESPACE_SLUG = "general"


def get_embedding_service() -> EmbeddingService | None:
    """Get embedding service if OpenAI is configured."""
    if not settings.openai_api_key:
        return None
    return EmbeddingService()


async def get_or_create_default_namespace(db: AsyncSession) -> KnowledgeNamespace:
    """Get or create the default 'general' namespace."""
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


async def get_all_namespaces(db: AsyncSession) -> list[KnowledgeNamespace]:
    """Get all namespaces ordered by name."""
    result = await db.execute(select(KnowledgeNamespace).order_by(KnowledgeNamespace.name))
    return list(result.scalars().all())


@router.get("", response_class=HTMLResponse)
async def knowledge_list(
    request: Request,
    page: int = Query(1, ge=1),
    search: str | None = Query(None),
    namespace: str | None = Query(None),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_read),
):
    """List all knowledge entries with pagination, search, namespace and status filter."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info(
        "Knowledge list accessed | user_id=%s client_id=%s page=%d search=%s namespace=%s status=%s",
        user.id,
        settings.oauth2_client_id,
        page,
        search,
        namespace,
        status,
    )

    limit = 20
    offset = (page - 1) * limit

    # Get all namespaces for filter dropdown
    namespaces = await get_all_namespaces(db)

    # Build base query
    base_query = select(KnowledgeEntry)

    # Apply namespace filter
    if namespace:
        ns_result = await db.execute(
            select(KnowledgeNamespace).where(KnowledgeNamespace.slug == namespace)
        )
        ns = ns_result.scalar_one_or_none()
        if ns:
            base_query = base_query.where(KnowledgeEntry.namespace_id == ns.id)

    # Apply status filter
    if status:
        base_query = base_query.where(KnowledgeEntry.status == status)

    # Apply search filter
    if search:
        search_pattern = f"%{search}%"
        base_query = base_query.where(
            KnowledgeEntry.question.ilike(search_pattern)
            | KnowledgeEntry.answer.ilike(search_pattern)
        )

    # Count total
    count_query = select(func.count()).select_from(
        base_query.with_only_columns(KnowledgeEntry.id).subquery()
    )
    total = await db.scalar(count_query) or 0
    total_pages = (total + limit - 1) // limit if total > 0 else 1

    # Get paginated results
    query = base_query.order_by(KnowledgeEntry.updated_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    entries = list(result.scalars().all())

    return templates.TemplateResponse(
        request=request,
        name="admin/knowledge/list.html",
        context={
            "request": request,
            "active_section": "knowledge",
            "user": user,
            "entries": entries,
            "namespaces": namespaces,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "search": search,
            "namespace_filter": namespace,
            "status_filter": status,
            "statuses": [s.value for s in KnowledgeEntryStatus],
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
            "openai_configured": bool(settings.openai_api_key),
            "validation_enabled": settings.validation_enabled,
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def knowledge_new(
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Show form to create a new knowledge entry."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info(
        "Knowledge new form accessed | user_id=%s client_id=%s",
        user.id,
        settings.oauth2_client_id,
    )

    # Ensure default namespace exists and get all namespaces
    default_ns = await get_or_create_default_namespace(db)
    namespaces = await get_all_namespaces(db)

    return templates.TemplateResponse(
        request=request,
        name="admin/knowledge/form.html",
        context={
            "request": request,
            "active_section": "knowledge",
            "user": user,
            "entry": None,
            "is_edit": False,
            "namespaces": namespaces,
            "default_namespace_id": default_ns.id,
            "openai_configured": bool(settings.openai_api_key),
        },
    )


# =============================================================================
# AI-Powered Generation Routes (must be before /{entry_id} routes)
# =============================================================================


@router.get("/generate", response_class=HTMLResponse)
async def knowledge_generate_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Show form to generate knowledge entries using AI."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info(
        "Knowledge generate form accessed | user_id=%s client_id=%s",
        user.id,
        settings.oauth2_client_id,
    )

    if not settings.openai_api_key:
        return RedirectResponse(
            url="/knowledge?error=OpenAI+not+configured",
            status_code=303,
        )

    # Ensure default namespace exists and get all namespaces
    default_ns = await get_or_create_default_namespace(db)
    namespaces = await get_all_namespaces(db)

    return templates.TemplateResponse(
        request=request,
        name="admin/knowledge/generate.html",
        context={
            "request": request,
            "active_section": "knowledge",
            "user": user,
            "namespaces": namespaces,
            "default_namespace_id": default_ns.id,
        },
    )


@router.post("/generate")
async def knowledge_generate(
    request: Request,
    source_text: str = Form(...),
    namespace_id: int = Form(...),
    num_entries: int = Form(5),
    context: str = Form(""),
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Dispatch async knowledge generation task.

    Returns JSON with task_id for the frontend to poll status.
    """
    if not isinstance(auth_result, User):
        return auth_result

    if not settings.openai_api_key:
        return JSONResponse(
            {"error": "OpenAI not configured"},
            status_code=400,
        )

    source_text = source_text.strip()
    context_val = context.strip() or None
    num_entries = max(1, min(50, num_entries))

    if len(source_text) < 50:
        return JSONResponse(
            {"error": "Source text too short (min 50 characters)"},
            status_code=400,
        )

    # Verify namespace exists, fallback to default if not
    ns_result = await db.execute(
        select(KnowledgeNamespace).where(KnowledgeNamespace.id == namespace_id)
    )
    namespace = ns_result.scalar_one_or_none()
    if not namespace:
        namespace = await get_or_create_default_namespace(db)
        namespace_id = namespace.id

    try:
        from internal.tasks.knowledge_generation import generate_knowledge_entries

        result = generate_knowledge_entries.delay(
            source_text, num_entries, context_val, namespace_id
        )
    except Exception as e:
        logger.error("Failed to dispatch generation task: %s", e)
        return JSONResponse(
            {"error": "Failed to start generation task"},
            status_code=500,
        )

    logger.info(
        "Generation task dispatched | user_id=%s client_id=%s namespace=%s task_id=%s",
        auth_result.id,
        settings.oauth2_client_id,
        namespace.slug,
        result.id,
    )

    return JSONResponse({"task_id": result.id})


@router.get("/generate/status/{task_id}")
async def knowledge_generate_status(
    request: Request,
    task_id: str,
    auth_result: User | RedirectResponse = Depends(require_read),
):
    """Poll generation task status."""
    if not isinstance(auth_result, User):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    from internal.celery import celery_app

    result = celery_app.AsyncResult(task_id)
    state = result.state

    if state == "PROGRESS":
        return JSONResponse(
            {
                "state": "PROGRESS",
                "progress": result.info,
            }
        )
    elif state == "SUCCESS":
        return JSONResponse(
            {
                "state": "SUCCESS",
                "result": result.result,
            }
        )
    elif state == "FAILURE":
        return JSONResponse(
            {
                "state": "FAILURE",
                "error": str(result.result),
            }
        )
    else:
        # PENDING or STARTED
        return JSONResponse({"state": state})


@router.post("/new")
async def knowledge_create(
    request: Request,
    question: str = Form(...),
    answer: str = Form(...),
    namespace_id: int = Form(...),
    metadata_json: str = Form("{}"),
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Create a new knowledge entry with embedding."""
    if not isinstance(auth_result, User):
        return auth_result

    # Parse metadata JSON
    try:
        metadata = json.loads(metadata_json) if metadata_json else {}
    except json.JSONDecodeError:
        return RedirectResponse(
            url="/knowledge/new?error=Invalid+JSON+in+metadata+field",
            status_code=303,
        )

    question = question.strip()
    answer = answer.strip()

    # Verify namespace exists, fallback to default if not
    ns_result = await db.execute(
        select(KnowledgeNamespace).where(KnowledgeNamespace.id == namespace_id)
    )
    if not ns_result.scalar_one_or_none():
        default_ns = await get_or_create_default_namespace(db)
        namespace_id = default_ns.id

    # Generate embedding if OpenAI is configured
    embedding = None
    embedding_service = get_embedding_service()
    if embedding_service:
        try:
            embedding = await embedding_service.generate(question)
            logger.info("Generated embedding for new knowledge entry")
        except Exception as e:
            logger.error("Failed to generate embedding: %s", e)
            return RedirectResponse(
                url="/knowledge/new?error=Failed+to+generate+embedding:+" + str(e)[:50],
                status_code=303,
            )

    # Create entry
    entry = KnowledgeEntry(
        question=question,
        answer=answer,
        embedding=embedding,
        metadata_=metadata,
        namespace_id=namespace_id,
    )

    # Set PENDING status when validation is enabled
    if settings.validation_enabled:
        entry.status = KnowledgeEntryStatus.PENDING.value

    db.add(entry)
    await db.commit()

    logger.info(
        "Knowledge entry created | user_id=%s client_id=%s entry_id=%s namespace_id=%s",
        auth_result.id,
        settings.oauth2_client_id,
        entry.id,
        namespace_id,
    )

    # Dispatch validation task
    if settings.validation_enabled:
        try:
            from internal.tasks.knowledge_validation import validate_knowledge_entry

            validate_knowledge_entry.delay(entry.id)
        except Exception:
            logger.exception("Failed to dispatch validation task for entry %s", entry.id)

    status_msg = (
        "Knowledge+entry+created+(validation+pending)"
        if settings.validation_enabled
        else "Knowledge+entry+created+successfully"
    )
    return RedirectResponse(
        url=f"/knowledge?success={status_msg}",
        status_code=303,
    )


@router.get("/{entry_id}", response_class=HTMLResponse)
async def knowledge_detail(
    request: Request,
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_read),
):
    """View knowledge entry detail."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info(
        "Knowledge detail accessed | user_id=%s client_id=%s entry_id=%s",
        user.id,
        settings.oauth2_client_id,
        entry_id,
    )

    result = await db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id))
    entry = result.scalar_one_or_none()

    if not entry:
        return RedirectResponse(
            url="/knowledge?error=Knowledge+entry+not+found",
            status_code=303,
        )

    return templates.TemplateResponse(
        request=request,
        name="admin/knowledge/detail.html",
        context={
            "request": request,
            "active_section": "knowledge",
            "user": user,
            "entry": entry,
            "openai_configured": bool(settings.openai_api_key),
            "validation_enabled": settings.validation_enabled,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/{entry_id}/edit", response_class=HTMLResponse)
async def knowledge_edit(
    request: Request,
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Show form to edit a knowledge entry."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info(
        "Knowledge edit form accessed | user_id=%s client_id=%s entry_id=%s",
        user.id,
        settings.oauth2_client_id,
        entry_id,
    )

    result = await db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id))
    entry = result.scalar_one_or_none()

    if not entry:
        return RedirectResponse(
            url="/knowledge?error=Knowledge+entry+not+found",
            status_code=303,
        )

    # Get all namespaces for dropdown
    namespaces = await get_all_namespaces(db)
    default_ns = await get_or_create_default_namespace(db)

    return templates.TemplateResponse(
        request=request,
        name="admin/knowledge/form.html",
        context={
            "request": request,
            "active_section": "knowledge",
            "user": user,
            "entry": entry,
            "is_edit": True,
            "namespaces": namespaces,
            "default_namespace_id": default_ns.id,
            "openai_configured": bool(settings.openai_api_key),
        },
    )


@router.post("/{entry_id}/edit")
async def knowledge_update(
    request: Request,
    entry_id: int,
    question: str = Form(...),
    answer: str = Form(...),
    namespace_id: int = Form(...),
    metadata_json: str = Form("{}"),
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Update a knowledge entry with new embedding if question changed."""
    if not isinstance(auth_result, User):
        return auth_result

    result = await db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id))
    entry = result.scalar_one_or_none()

    if not entry:
        return RedirectResponse(
            url="/knowledge?error=Knowledge+entry+not+found",
            status_code=303,
        )

    # Parse metadata JSON
    try:
        metadata = json.loads(metadata_json) if metadata_json else {}
    except json.JSONDecodeError:
        return RedirectResponse(
            url=f"/knowledge/{entry_id}/edit?error=Invalid+JSON+in+metadata+field",
            status_code=303,
        )

    question = question.strip()
    answer = answer.strip()

    # Verify namespace exists, fallback to default if not
    ns_result = await db.execute(
        select(KnowledgeNamespace).where(KnowledgeNamespace.id == namespace_id)
    )
    if not ns_result.scalar_one_or_none():
        default_ns = await get_or_create_default_namespace(db)
        namespace_id = default_ns.id

    # Regenerate embedding if question changed
    question_changed = entry.question != question
    if question_changed:
        embedding_service = get_embedding_service()
        if embedding_service:
            try:
                entry.embedding = await embedding_service.generate(question)
                logger.info(
                    "Knowledge entry embedding regenerated | user_id=%s client_id=%s entry_id=%s",
                    auth_result.id,
                    settings.oauth2_client_id,
                    entry_id,
                )
            except Exception as e:
                logger.error("Failed to regenerate embedding: %s", e)
                return RedirectResponse(
                    url=f"/knowledge/{entry_id}/edit?error=Failed+to+generate+embedding:+"
                    + str(e)[:50],
                    status_code=303,
                )

    # Update entry
    entry.question = question
    entry.answer = answer
    entry.metadata_ = metadata
    entry.namespace_id = namespace_id

    await db.commit()

    logger.info(
        "Knowledge entry updated | user_id=%s client_id=%s entry_id=%s",
        auth_result.id,
        settings.oauth2_client_id,
        entry_id,
    )

    return RedirectResponse(
        url=f"/knowledge/{entry_id}?success=Knowledge+entry+updated+successfully",
        status_code=303,
    )


@router.post("/{entry_id}/regenerate-embedding")
async def knowledge_regenerate_embedding(
    request: Request,
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Regenerate embedding for an existing entry."""
    if not isinstance(auth_result, User):
        return auth_result

    embedding_service = get_embedding_service()
    if not embedding_service:
        return RedirectResponse(
            url=f"/knowledge/{entry_id}?error=OpenAI+not+configured",
            status_code=303,
        )

    result = await db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id))
    entry = result.scalar_one_or_none()

    if not entry:
        return RedirectResponse(
            url="/knowledge?error=Knowledge+entry+not+found",
            status_code=303,
        )

    try:
        entry.embedding = await embedding_service.generate(entry.question)
        await db.commit()
        logger.info(
            "Knowledge entry embedding regenerated | user_id=%s client_id=%s entry_id=%s",
            auth_result.id,
            settings.oauth2_client_id,
            entry_id,
        )
    except Exception as e:
        logger.error("Failed to regenerate embedding: %s", e)
        return RedirectResponse(
            url=f"/knowledge/{entry_id}?error=Failed+to+regenerate+embedding",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/knowledge/{entry_id}?success=Embedding+regenerated+successfully",
        status_code=303,
    )


# =============================================================================
# Validation Routes
# =============================================================================


@router.get("/{entry_id}/validation", response_class=HTMLResponse)
async def knowledge_validation_detail(
    request: Request,
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_read),
):
    """View validation details for a knowledge entry."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    result = await db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id))
    entry = result.scalar_one_or_none()

    if not entry:
        return RedirectResponse(
            url="/knowledge?error=Knowledge+entry+not+found",
            status_code=303,
        )

    return templates.TemplateResponse(
        request=request,
        name="admin/knowledge/validation_detail.html",
        context={
            "request": request,
            "active_section": "knowledge",
            "user": user,
            "entry": entry,
        },
    )


@router.post("/{entry_id}/revalidate")
async def knowledge_revalidate(
    request: Request,
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Re-trigger validation for an entry."""
    if not isinstance(auth_result, User):
        return auth_result

    result = await db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id))
    entry = result.scalar_one_or_none()

    if not entry:
        return RedirectResponse(
            url="/knowledge?error=Knowledge+entry+not+found",
            status_code=303,
        )

    entry.status = KnowledgeEntryStatus.PENDING.value
    await db.commit()

    try:
        from internal.tasks.knowledge_validation import validate_knowledge_entry

        validate_knowledge_entry.delay(entry.id)
    except Exception:
        logger.exception("Failed to dispatch revalidation task for entry %s", entry_id)

    logger.info(
        "Validation re-triggered | user_id=%s client_id=%s entry_id=%s",
        auth_result.id,
        settings.oauth2_client_id,
        entry_id,
    )

    return RedirectResponse(
        url=f"/knowledge/{entry_id}?success=Validation+re-triggered",
        status_code=303,
    )


@router.post("/{entry_id}/approve")
async def knowledge_approve(
    request: Request,
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Manually approve a NEEDS_REVIEW or REJECTED entry."""
    if not isinstance(auth_result, User):
        return auth_result

    result = await db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id))
    entry = result.scalar_one_or_none()

    if not entry:
        return RedirectResponse(
            url="/knowledge?error=Knowledge+entry+not+found",
            status_code=303,
        )

    entry.status = KnowledgeEntryStatus.ACCEPTED.value
    await db.commit()

    logger.info(
        "Knowledge entry manually approved | user_id=%s client_id=%s entry_id=%s",
        auth_result.id,
        settings.oauth2_client_id,
        entry_id,
    )

    return RedirectResponse(
        url=f"/knowledge/{entry_id}?success=Entry+approved",
        status_code=303,
    )


@router.post("/{entry_id}/reject")
async def knowledge_reject(
    request: Request,
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Manually reject an entry."""
    if not isinstance(auth_result, User):
        return auth_result

    result = await db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id))
    entry = result.scalar_one_or_none()

    if not entry:
        return RedirectResponse(
            url="/knowledge?error=Knowledge+entry+not+found",
            status_code=303,
        )

    entry.status = KnowledgeEntryStatus.REJECTED.value
    await db.commit()

    logger.info(
        "Knowledge entry manually rejected | user_id=%s client_id=%s entry_id=%s",
        auth_result.id,
        settings.oauth2_client_id,
        entry_id,
    )

    return RedirectResponse(
        url=f"/knowledge/{entry_id}?success=Entry+rejected",
        status_code=303,
    )


@router.post("/{entry_id}/delete")
async def knowledge_delete(
    request: Request,
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_delete),
):
    """Delete a knowledge entry."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    result = await db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id))
    entry = result.scalar_one_or_none()

    if not entry:
        return RedirectResponse(
            url="/knowledge?error=Knowledge+entry+not+found",
            status_code=303,
        )

    await db.delete(entry)
    await db.commit()

    logger.info(
        "Knowledge entry deleted | user_id=%s client_id=%s entry_id=%s",
        user.id,
        settings.oauth2_client_id,
        entry_id,
    )

    return RedirectResponse(
        url="/knowledge?success=Knowledge+entry+deleted+successfully",
        status_code=303,
    )


@router.post("/bulk-delete")
async def knowledge_bulk_delete(
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_delete),
):
    """Delete multiple knowledge entries."""
    if not isinstance(auth_result, User):
        return auth_result

    form = await request.form()
    entry_ids_str = str(form.get("entry_ids", ""))
    entry_ids_raw = [id_str.strip() for id_str in entry_ids_str.split(",") if id_str.strip()]

    if not entry_ids_raw:
        return RedirectResponse(
            url="/knowledge?error=No+entries+selected",
            status_code=303,
        )

    try:
        entry_ids = [int(id_str) for id_str in entry_ids_raw if id_str]
    except ValueError:
        return RedirectResponse(
            url="/knowledge?error=Invalid+entry+IDs",
            status_code=303,
        )

    result = await db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id.in_(entry_ids)))
    entries = result.scalars().all()

    if not entries:
        return RedirectResponse(
            url="/knowledge?error=No+entries+found",
            status_code=303,
        )

    deleted_count = len(entries)
    for entry in entries:
        await db.delete(entry)

    await db.commit()

    logger.info(
        "Knowledge entries bulk deleted | user_id=%s client_id=%s deleted_count=%d",
        auth_result.id,
        settings.oauth2_client_id,
        deleted_count,
    )

    return RedirectResponse(
        url=f"/knowledge?success={deleted_count}+entry(ies)+deleted+successfully",
        status_code=303,
    )
