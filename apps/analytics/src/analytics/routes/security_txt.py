# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Security.txt endpoint implementation (RFC 9116).

This module provides the /.well-known/security.txt endpoint for vulnerability
disclosure according to RFC 9116.
"""

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from analytics.config import settings

router = APIRouter()


def generate_security_txt() -> str:
    """Generate security.txt content from settings."""
    lines = []

    # Required fields
    if settings.security_contact:
        lines.append(f"Contact: {settings.security_contact}")
    if settings.security_expires:
        lines.append(f"Expires: {settings.security_expires}")

    # Optional fields
    if settings.security_encryption:
        lines.append(f"Encryption: {settings.security_encryption}")
    if settings.security_acknowledgments:
        lines.append(f"Acknowledgments: {settings.security_acknowledgments}")
    if settings.security_preferred_languages:
        lines.append(f"Preferred-Languages: {settings.security_preferred_languages}")
    if settings.security_canonical:
        lines.append(f"Canonical: {settings.security_canonical}")
    if settings.security_policy:
        lines.append(f"Policy: {settings.security_policy}")
    if settings.security_hiring:
        lines.append(f"Hiring: {settings.security_hiring}")
    if settings.security_csaf:
        lines.append(f"CSAF: {settings.security_csaf}")

    return "\n".join(lines)


@router.get("/.well-known/security.txt", include_in_schema=False)
async def security_txt() -> PlainTextResponse:
    """Return security.txt content (RFC 9116)."""
    content = generate_security_txt()
    return PlainTextResponse(content=content, media_type="text/plain")
