# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Security.txt endpoint implementation (RFC 9116).

This module provides the /.well-known/security.txt endpoint for vulnerability
disclosure according to RFC 9116.
"""

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from .config import Settings
from .logging import get_logger

logger = get_logger(__name__)

# (field name, settings attribute) in the order they are written. Contact and
# Expires are the fields required by the RFC, the others are optional.
FIELDS = (
    ("Contact", "security_contact"),
    ("Expires", "security_expires"),
    ("Encryption", "security_encryption"),
    ("Acknowledgments", "security_acknowledgments"),
    ("Preferred-Languages", "security_preferred_languages"),
    ("Canonical", "security_canonical"),
    ("Policy", "security_policy"),
    ("Hiring", "security_hiring"),
    ("CSAF", "security_csaf"),
)


def generate_security_txt(cfg: Settings) -> str:
    """Generate security.txt content from settings; empty fields are omitted."""
    return "\n".join(f"{name}: {getattr(cfg, attr)}" for name, attr in FIELDS if getattr(cfg, attr))


def create_router(cfg: Settings) -> APIRouter:
    """Build the router serving security.txt for the given settings."""
    router = APIRouter()

    @router.get("/.well-known/security.txt", include_in_schema=False)
    async def security_txt() -> PlainTextResponse:
        """Return security.txt content (RFC 9116)."""
        logger.info("security.txt requested")
        return PlainTextResponse(content=generate_security_txt(cfg), media_type="text/plain")

    return router
