# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Admin routes for HTML pages - Chat History CRUD.

Scopes required:
- conversations:read - View conversations and dashboard
- conversations:delete - Delete conversations
"""

import uuid

from fastapi import APIRouter, Depends, Query, Request
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
from internal.models.conversation import Conversation, Message
from internal.services.analytics_client import analytics_client
from internal.services.auth_client import auth_client

router = APIRouter(tags=["admin"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)
logger = get_logger(__name__)

# Use resource-level scope request to get all permissions at once for proper UI display
# Dashboard also requests analytics:read to show analytics stats if user has permission
# and vpn:admin to show VPN link in navigation if user has permission
require_dashboard = require_resource_scopes_or_redirect(
    "conversations", extra_scopes=["analytics:read", "vpn:admin", "billing:read"]
)
require_read = require_resource_scopes_or_redirect(
    "conversations", extra_scopes=["vpn:admin", "billing:read"]
)
require_delete = require_scope_or_redirect("conversations:delete")


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_dashboard),
):
    """Admin dashboard with chat statistics."""
    # If not authenticated or access denied, return the response
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info(
        "Dashboard accessed | user_id=%s client_id=%s",
        user.id,
        settings.oauth2_client_id,
    )

    # Get statistics
    total_conversations = await db.scalar(select(func.count(Conversation.id)))
    total_messages = await db.scalar(select(func.count(Message.id)))
    authenticated_conversations = await db.scalar(
        select(func.count(Conversation.id)).where(Conversation.user_id.isnot(None))
    )
    anonymous_conversations = await db.scalar(
        select(func.count(Conversation.id)).where(
            Conversation.user_id.is_(None),
            Conversation.session_id.isnot(None),
        )
    )

    # Get recent conversations with message count
    recent_query = (
        select(
            Conversation,
            func.count(Message.id).label("message_count"),
        )
        .outerjoin(Message, Conversation.id == Message.conversation_id)
        .group_by(Conversation.id)
        .order_by(Conversation.updated_at.desc())
        .limit(5)
    )
    result = await db.execute(recent_query)
    recent_rows = result.all()

    recent_conversations = []
    for conv, msg_count in recent_rows:
        conv.message_count = msg_count
        recent_conversations.append(conv)

    # Fetch analytics stats if user has analytics:read scope
    analytics_stats = None
    logger.info(
        "Dashboard scope check | user_id=%s scopes=%s has_analytics=%s",
        user.id,
        user.scopes,
        user.has_scope("analytics:read"),
    )
    if user.has_scope("analytics:read"):
        try:
            analytics_stats = await analytics_client.get_overview(days=30)
        except Exception as e:
            logger.warning("Failed to fetch analytics stats for dashboard: %s", e)

    return templates.TemplateResponse(
        request=request,
        name="admin/dashboard.html",
        context={
            "request": request,
            "active_section": "dashboard",
            "user": user,
            "stats": {
                "total_conversations": total_conversations or 0,
                "total_messages": total_messages or 0,
                "authenticated_conversations": authenticated_conversations or 0,
                "anonymous_conversations": anonymous_conversations or 0,
            },
            "recent_conversations": recent_conversations,
            "analytics_stats": analytics_stats,
        },
    )


@router.get("/conversations", response_class=HTMLResponse)
async def conversations_list(
    request: Request,
    page: int = Query(1, ge=1),
    search: str | None = Query(None),
    type: str | None = Query(None, alias="type"),
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_read),
):
    """List all conversations with pagination and search."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info(
        "Conversations list accessed | user_id=%s client_id=%s page=%d search=%s type=%s",
        user.id,
        settings.oauth2_client_id,
        page,
        search,
        type,
    )

    limit = 20
    offset = (page - 1) * limit

    # Build base query with message count
    base_query = (
        select(
            Conversation,
            func.count(Message.id).label("message_count"),
        )
        .outerjoin(Message, Conversation.id == Message.conversation_id)
        .group_by(Conversation.id)
    )

    # Apply filters
    filters = []
    if search:
        # Search by user_id or session_id (partial match)
        try:
            # Try to parse as UUID for user_id search
            search_uuid = uuid.UUID(search)
            filters.append(Conversation.user_id == search_uuid)
        except ValueError:
            # Not a valid UUID, search by session_id
            filters.append(Conversation.session_id.ilike(f"%{search}%"))

    if type == "authenticated":
        filters.append(Conversation.user_id.isnot(None))
    elif type == "anonymous":
        filters.append(Conversation.user_id.is_(None))
        filters.append(Conversation.session_id.isnot(None))

    if filters:
        base_query = base_query.where(*filters)

    # Count total
    count_query = select(func.count()).select_from(
        base_query.with_only_columns(Conversation.id).subquery()
    )
    total = await db.scalar(count_query) or 0
    total_pages = (total + limit - 1) // limit

    # Get paginated results
    query = base_query.order_by(Conversation.updated_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    rows = result.all()

    conversations = []
    for conv, msg_count in rows:
        conv.message_count = msg_count
        conversations.append(conv)

    return templates.TemplateResponse(
        request=request,
        name="admin/conversations/list.html",
        context={
            "request": request,
            "active_section": "conversations",
            "user": user,
            "conversations": conversations,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "search": search,
            "type_filter": type,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/conversations/{conversation_id}", response_class=HTMLResponse)
async def conversation_detail(
    request: Request,
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_read),
):
    """View conversation detail with all messages."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info(
        "Conversation detail accessed | user_id=%s client_id=%s conversation_id=%s",
        user.id,
        settings.oauth2_client_id,
        conversation_id,
    )

    # Get conversation
    result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    conversation = result.scalar_one_or_none()

    if not conversation:
        return templates.TemplateResponse(
            request=request,
            name="admin/conversations/list.html",
            context={
                "request": request,
                "active_section": "conversations",
                "user": user,
                "conversations": [],
                "total": 0,
                "page": 1,
                "total_pages": 0,
                "search": None,
                "type_filter": None,
                "error": "Conversation not found.",
            },
        )

    # Get all messages ordered by created_at
    messages_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    messages = list(messages_result.scalars().all())

    # Get conversation owner info from auth API if authenticated user
    owner = None
    if conversation.user_id:
        owner = await auth_client.get_user(conversation.user_id)

    # Count by role
    user_count = sum(1 for m in messages if m.role == "user")
    assistant_count = sum(1 for m in messages if m.role == "assistant")
    system_count = sum(1 for m in messages if m.role == "system")

    # Build back params from referer
    back_params = ""
    referer = request.headers.get("referer", "")
    if "?" in referer:
        back_params = referer.split("?", 1)[1]

    return templates.TemplateResponse(
        request=request,
        name="admin/conversations/detail.html",
        context={
            "request": request,
            "active_section": "conversations",
            "user": user,
            "conversation": conversation,
            "owner": owner,
            "messages": messages,
            "user_message_count": user_count,
            "assistant_message_count": assistant_count,
            "system_message_count": system_count,
            "back_params": back_params,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/conversations/{conversation_id}/delete")
async def delete_conversation(
    request: Request,
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_delete),
):
    """Delete a conversation and all its messages."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    # Get conversation
    result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    conversation = result.scalar_one_or_none()

    if not conversation:
        return RedirectResponse(
            url="/conversations?error=Conversation+not+found",
            status_code=303,
        )

    # Delete conversation (cascade will delete messages)
    await db.delete(conversation)
    await db.commit()

    logger.info(
        "Conversation deleted | user_id=%s client_id=%s conversation_id=%s",
        user.id,
        settings.oauth2_client_id,
        conversation_id,
    )

    return RedirectResponse(
        url="/conversations?success=Conversation+deleted+successfully",
        status_code=303,
    )


@router.post("/conversations/bulk-delete")
async def bulk_delete_conversations(
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_delete),
):
    """Delete multiple conversations and all their messages."""
    if not isinstance(auth_result, User):
        return auth_result

    # Get form data
    form = await request.form()
    conversation_ids_raw = form.getlist("conversation_ids")

    if not conversation_ids_raw:
        return RedirectResponse(
            url="/conversations?error=No+conversations+selected",
            status_code=303,
        )

    # Parse UUIDs: the page sends the selection as one comma-separated value
    try:
        conversation_ids = [
            uuid.UUID(id_str.strip())
            for raw in conversation_ids_raw
            for id_str in str(raw).split(",")
            if id_str.strip()
        ]
    except ValueError:
        return RedirectResponse(
            url="/conversations?error=Invalid+conversation+IDs",
            status_code=303,
        )

    # Get conversations
    result = await db.execute(select(Conversation).where(Conversation.id.in_(conversation_ids)))
    conversations = result.scalars().all()

    if not conversations:
        return RedirectResponse(
            url="/conversations?error=No+conversations+found",
            status_code=303,
        )

    # Delete all conversations (cascade will delete messages)
    deleted_count = len(conversations)
    for conversation in conversations:
        await db.delete(conversation)

    await db.commit()

    user = auth_result
    logger.info(
        "Bulk delete conversations | user_id=%s client_id=%s deleted_count=%d",
        user.id,
        settings.oauth2_client_id,
        deleted_count,
    )

    return RedirectResponse(
        url=f"/conversations?success={deleted_count}+conversation(s)+deleted+successfully",
        status_code=303,
    )
