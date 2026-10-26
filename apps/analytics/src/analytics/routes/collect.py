# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Event collection endpoint."""

import contextlib
import uuid
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.config import settings
from analytics.database import get_db
from analytics.logging import get_logger, set_request_context
from analytics.services.collector import collector_service, get_client_ip

logger = get_logger(__name__)

router = APIRouter(tags=["collect"])


class EventPayload(BaseModel):
    """Single event payload."""

    event_type: str = Field(..., max_length=50)
    event_data: dict | None = None
    page_url: str | None = None
    page_title: str | None = Field(None, max_length=255)


class CollectRequest(BaseModel):
    """Batch event collection request."""

    events: list[EventPayload] = Field(..., min_length=1, max_length=100)
    user_id: uuid.UUID | None = None


class CollectResponse(BaseModel):
    """Collection response."""

    success: bool = True
    session_id: str
    events_count: int


@router.post("/collect", response_model=CollectResponse)
async def collect_events(
    request: Request,
    response: Response,
    payload: CollectRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    ua_sid: Annotated[str | None, Cookie()] = None,
) -> CollectResponse:
    """Collect analytics events.

    This endpoint receives batches of events from the frontend SDK.
    It creates or retrieves the session and stores all events.
    """
    client_ip = get_client_ip(request)
    set_request_context(session_id=ua_sid, client_ip=client_ip)

    # Get or create session
    session, is_new = await collector_service.get_or_create_session(
        db=db,
        request=request,
        session_id=ua_sid,
        user_id=payload.user_id,
    )

    # Set session cookie if new
    if is_new:
        response.set_cookie(
            key=settings.session_cookie_name,
            value=session.session_id,
            max_age=settings.session_cookie_max_age,
            secure=settings.session_cookie_secure,
            httponly=True,
            samesite=settings.session_cookie_samesite,
            domain=settings.session_cookie_domain or None,
        )

    # Track all events
    for event_payload in payload.events:
        await collector_service.track_event(
            db=db,
            session=session,
            event_type=event_payload.event_type,
            event_data=event_payload.event_data,
            page_url=event_payload.page_url,
            page_title=event_payload.page_title,
        )

    logger.info(f"Collected {len(payload.events)} events for session {session.session_id}")

    return CollectResponse(
        success=True,
        session_id=session.session_id,
        events_count=len(payload.events),
    )


@router.get("/collect")
async def collect_beacon(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    t: str,  # event type
    d: str | None = None,  # event data (JSON encoded)
    u: str | None = None,  # page URL
    ua_sid: Annotated[str | None, Cookie()] = None,
) -> Response:
    """Lightweight GET endpoint for beacon/pixel tracking.

    Useful for tracking without JavaScript (e.g., email opens, noscript fallback).
    Returns a 1x1 transparent GIF.
    """
    import base64
    import json

    client_ip = get_client_ip(request)
    set_request_context(session_id=ua_sid, client_ip=client_ip)

    # Get or create session
    session, is_new = await collector_service.get_or_create_session(
        db=db,
        request=request,
        session_id=ua_sid,
    )

    # Parse event data if provided
    event_data = None
    if d:
        with contextlib.suppress(json.JSONDecodeError):
            event_data = json.loads(d)

    # Track event
    await collector_service.track_event(
        db=db,
        session=session,
        event_type=t,
        event_data=event_data,
        page_url=u,
    )

    # 1x1 transparent GIF
    gif_bytes = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")

    resp = Response(
        content=gif_bytes,
        media_type="image/gif",
        headers={
            "Cache-Control": settings.pixel_cache_control,
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )

    # Set session cookie if new
    if is_new:
        resp.set_cookie(
            key=settings.session_cookie_name,
            value=session.session_id,
            max_age=settings.session_cookie_max_age,
            secure=settings.session_cookie_secure,
            httponly=True,
            samesite=settings.session_cookie_samesite,
            domain=settings.session_cookie_domain or None,
        )

    return resp
