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
from analytics.models import Campaign, Event, Pixel, PixelOpen, Session
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

    async def track_pixel_open(
        self,
        db: AsyncSession,
        pixel_key: str,
        request: Request,
    ) -> Pixel | None:
        """Track a pixel open event.

        Args:
            db: Database session.
            pixel_key: Unique pixel identifier.
            request: FastAPI request.

        Returns:
            Pixel if found, None otherwise.
        """
        result = await db.execute(select(Pixel).where(Pixel.pixel_key == pixel_key))
        pixel = result.scalar_one_or_none()

        if not pixel:
            logger.warning(f"Pixel not found: {pixel_key}")
            return None

        client_ip = get_client_ip(request)
        user_agent = request.headers.get("user-agent")
        geo = geoip_service.lookup(client_ip)

        # Create open record
        pixel_open = PixelOpen(
            pixel_id=pixel.id,
            ip_address=client_ip if client_ip != "unknown" else None,
            user_agent=user_agent,
            country=geo.country,
            city=geo.city,
        )
        db.add(pixel_open)

        # Update pixel stats
        now = datetime.now(UTC)
        if not pixel.first_opened_at:
            pixel.first_opened_at = now
        pixel.last_opened_at = now
        pixel.open_count += 1

        await db.commit()

        logger.info(f"Pixel opened: {pixel_key} (count: {pixel.open_count})")
        return pixel

    async def create_campaign(
        self,
        db: AsyncSession,
        name: str,
        description: str | None = None,
        destination_url: str | None = None,
        extra_data: dict | None = None,
    ) -> Campaign:
        """Create a new campaign.

        Args:
            db: Database session.
            name: Campaign name.
            description: Campaign description.
            destination_url: URL to redirect to.
            extra_data: Additional data.

        Returns:
            Created campaign.
        """
        campaign = Campaign(
            name=name,
            description=description,
            tracking_key=generate_tracking_key(),
            destination_url=destination_url,
            extra_data=extra_data,
        )

        db.add(campaign)
        await db.commit()
        await db.refresh(campaign)

        logger.info(f"Campaign created: {name} ({campaign.tracking_key})")
        return campaign

    async def create_pixel(
        self,
        db: AsyncSession,
        campaign_id: uuid.UUID,
        recipient_email: str | None = None,
        recipient_id: str | None = None,
        extra_data: dict | None = None,
    ) -> Pixel:
        """Create a tracking pixel for a campaign.

        Args:
            db: Database session.
            campaign_id: Parent campaign ID.
            recipient_email: Recipient email address.
            recipient_id: Custom recipient identifier.
            extra_data: Additional data.

        Returns:
            Created pixel.
        """
        pixel = Pixel(
            campaign_id=campaign_id,
            pixel_key=generate_tracking_key(),
            recipient_email=recipient_email,
            recipient_id=recipient_id,
            extra_data=extra_data,
        )

        db.add(pixel)
        await db.commit()
        await db.refresh(pixel)

        logger.info(f"Pixel created: {pixel.pixel_key} for campaign {campaign_id}")
        return pixel


# Singleton instance
collector_service = CollectorService()
