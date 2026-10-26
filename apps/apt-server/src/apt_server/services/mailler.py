# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Mailler service client — sends emails via the internal mailler API.

Uses OAuth2 client_credentials flow to authenticate against the auth
service, then sends the email via the mailler's REST endpoint. Connects
via unix socket when ``MAILLER_UNIX_SOCKET`` is configured (same-host).
"""

import time

import httpx

from apt_server.config import settings
from apt_server.logging import get_logger

logger = get_logger(__name__)

_cached_token: str = ""
_token_expires_at: float = 0


async def _get_access_token() -> str:
    """Obtain (or reuse) a client_credentials access token."""
    global _cached_token, _token_expires_at

    if _cached_token and time.time() < _token_expires_at:
        return _cached_token

    auth_url = (settings.mailler_auth_url or settings.oauth2_issuer).rstrip("/")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{auth_url}/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": settings.mailler_client_id,
                "client_secret": settings.mailler_client_secret,
                "scope": "mailler:send",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    _cached_token = data["access_token"]
    _token_expires_at = time.time() + data.get("expires_in", 3600) - 60
    return _cached_token


def _transport() -> httpx.AsyncBaseTransport | None:
    """Return a unix socket transport if configured."""
    if settings.mailler_unix_socket:
        return httpx.AsyncHTTPTransport(uds=settings.mailler_unix_socket)
    return None


async def send_email(
    *,
    to_email: str,
    to_name: str = "",
    subject: str,
    html_content: str,
    text_content: str = "",
) -> None:
    """Send an email via the mailler service."""
    if settings.email_backend.lower() != "mailler":
        logger.debug("email_backend is not 'mailler', skipping send to %s", to_email)
        return

    if not settings.mailler_client_id or not settings.mailler_client_secret:
        logger.warning("mailler credentials not configured, skipping send to %s", to_email)
        return

    try:
        token = await _get_access_token()
    except Exception as exc:
        logger.error("mailler auth failed (check MAILLER_CLIENT_ID/SECRET): %s", exc)
        return

    transport = _transport()
    base_url = settings.mailler_url

    try:
        async with httpx.AsyncClient(
            transport=transport, base_url=base_url, timeout=15.0
        ) as client:
            resp = await client.post(
                "/api/v1/send",
                json={
                    "to_email": to_email,
                    "to_name": to_name,
                    "subject": subject,
                    "html_content": html_content,
                    "text_content": text_content or None,
                    "from_email": settings.email_from,
                    "from_name": settings.email_from_name,
                    "provider": settings.mailler_provider,
                    "metadata": {"source": "apt-server"},
                },
                headers={"Authorization": f"Bearer {token}"},
            )
    except Exception as exc:
        logger.error("mailler send request failed: %s", exc)
        return

    if resp.status_code >= 400:
        logger.error("mailler send failed: status=%s body=%s", resp.status_code, resp.text[:200])
    else:
        logger.info("email sent to %s: %s", to_email, subject)
