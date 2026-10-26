# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Field validators shared by the request schemas."""

from urllib.parse import urlsplit

from custom_domain.config import settings
from custom_domain.services.upstream import InvalidUpstreamError, parse_upstream

MAX_WEBHOOK_URL_LENGTH = 1000  # size of the ``webhook_url`` column
MIN_WEBHOOK_SECRET_LENGTH = 32


def validate_upstream(value: str | None) -> str | None:
    """Accept a Unix socket path or ``host:port`` and reject anything else.

    Raises:
        ValueError: If the value is not a valid upstream target (Pydantic turns it
            into a ``422`` answer)
    """
    if value is None:
        return value
    try:
        parse_upstream(value)
    except InvalidUpstreamError as error:
        raise ValueError(str(error)) from error
    return value.strip()


def validate_webhook_url(value: str | None) -> str | None:
    """Accept an ``https://`` URL (``http://`` only with WEBHOOK_ALLOW_INSECURE_URLS).

    Raises:
        ValueError: If the value is not an absolute URL without credentials
    """
    if value is None:
        return value
    url = value.strip()
    if len(url) > MAX_WEBHOOK_URL_LENGTH:
        raise ValueError("Webhook URL is too long")
    parts = urlsplit(url)
    allowed = ("https", "http") if settings.webhook_allow_insecure_urls else ("https",)
    if parts.scheme not in allowed:
        raise ValueError(f"Webhook URL must use {' or '.join(allowed)}")
    if not parts.hostname:
        raise ValueError("Webhook URL has no host")
    if parts.username or parts.password:
        raise ValueError("Webhook URL must not contain credentials")
    return url


def validate_webhook_secret(value: str | None) -> str | None:
    """Require a secret long enough to be an HMAC key.

    Raises:
        ValueError: If the secret is shorter than 32 characters
    """
    if value is not None and len(value) < MIN_WEBHOOK_SECRET_LENGTH:
        raise ValueError(f"Webhook secret must be at least {MIN_WEBHOOK_SECRET_LENGTH} characters")
    return value
