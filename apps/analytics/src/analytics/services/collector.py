# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Analytics event collector service."""

import secrets
import uuid
from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.config import settings
from analytics.logging import get_logger
from analytics.models import Event, Session
from analytics.services.geoip import geoip_service
from analytics.services.useragent import useragent_service

logger = get_logger(__name__)


def generate_tracking_key(length: int = 16) -> str:
    """Generate a secure random tracking key."""
    return secrets.token_urlsafe(length)


def get_client_ip(request: Request) -> str:
    """Extract client IP from request, handling proxies."""
    # Check X-Forwarded-For header (set by reverse proxy)
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        # Take the first IP in the chain (original client)
        ip = forwarded_for.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "unknown"

    # Optionally anonymize IP for GDPR compliance
    if settings.anonymize_ip and ip and ip != "unknown":
        if ":" in ip:
            # IPv6: mask last 80 bits (keep /48)
            parts = ip.split(":")
            if len(parts) >= 3:
                ip = ":".join(parts[:3]) + "::"
        else:
            # IPv4: mask last octet
            parts = ip.split(".")
            if len(parts) == 4:
                ip = ".".join(parts[:3]) + ".0"

    return ip


class CollectorService:
    """Service for collecting analytics data."""

    async def get_or_create_session(
        self,
        db: AsyncSession,
        request: Request,
        session_id: str | None = None,
        user_id: uuid.UUID | None = None,
    ) -> tuple[Session, bool]:
        """Get or create an analytics session.

        Args:
            db: Database session.
            request: FastAPI request.
            session_id: Existing session ID from cookie.
            user_id: Authenticated user ID.

        Returns:
            Tuple of (session, is_new).
        """
        # Try to find existing session
        if session_id:
            result = await db.execute(select(Session).where(Session.session_id == session_id))
            session = result.scalar_one_or_none()
            if session:
                # Update last seen
                session.last_seen = datetime.now(UTC)
                # Link user if newly authenticated
                if user_id and not session.user_id:
                    session.user_id = user_id
                await db.commit()
                return session, False

        # Create new session
        new_session_id = session_id or generate_tracking_key(24)
        client_ip = get_client_ip(request)
        user_agent = request.headers.get("user-agent")
        referrer = request.headers.get("referer")

        # Parse user agent
        device_info = useragent_service.parse(user_agent)

        # Get geolocation
        geo = geoip_service.lookup(client_ip)

        # Extract UTM parameters
        utm_source = request.query_params.get("utm_source")
        utm_medium = request.query_params.get("utm_medium")
        utm_campaign = request.query_params.get("utm_campaign")
        utm_term = request.query_params.get("utm_term")
        utm_content = request.query_params.get("utm_content")

        session = Session(
            session_id=new_session_id,
            user_id=user_id,
            ip_address=client_ip if client_ip != "unknown" else None,
            country=geo.country,
            city=geo.city,
            user_agent=user_agent,
            device_type=device_info.device_type,
            browser=device_info.browser,
            browser_version=device_info.browser_version,
            os=device_info.os,
            os_version=device_info.os_version,
            referrer=referrer,
            utm_source=utm_source,
            utm_medium=utm_medium,
            utm_campaign=utm_campaign,
            utm_term=utm_term,
            utm_content=utm_content,
            landing_page=str(request.url),
        )

        db.add(session)
        await db.commit()
        await db.refresh(session)

        logger.info(f"New session created: {new_session_id} from {client_ip} ({geo.country})")
        return session, True

    async def track_event(
        self,
        db: AsyncSession,
        session: Session,
        event_type: str,
        event_data: dict | None = None,
        page_url: str | None = None,
        page_title: str | None = None,
    ) -> Event:
        """Track an analytics event.

        Args:
            db: Database session.
            session: Analytics session.
            event_type: Type of event (page_view, click, etc.).
            event_data: Additional event data.
            page_url: Current page URL.
            page_title: Current page title.

        Returns:
            Created event.
        """
        event = Event(
            session_id=session.id,
            event_type=event_type,
            event_data=event_data,
            page_url=page_url,
            page_title=page_title,
        )

        db.add(event)

        # Update session last seen
        session.last_seen = datetime.now(UTC)

        await db.commit()
        await db.refresh(event)

        logger.debug(f"Event tracked: {event_type} for session {session.session_id}")
        return event


# Singleton instance
collector_service = CollectorService()
