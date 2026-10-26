# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""MTA-STS endpoint (RFC 8461)."""

from fastapi import APIRouter, Response

from mta_sts.config import settings

router = APIRouter()


def render_mta_sts_policy() -> str:
    """Render MTA-STS policy from configuration."""
    lines = [
        "version: STSv1",
        f"mode: {settings.mta_sts_mode}",
    ]

    for mx in settings.mx_hosts:
        lines.append(f"mx: {mx}")

    lines.append(f"max_age: {settings.mta_sts_max_age}")

    return "\n".join(lines)


@router.get("/.well-known/mta-sts.txt", include_in_schema=False)
async def mta_sts_policy():
    """Serve MTA-STS policy (RFC 8461)."""
    return Response(content=render_mta_sts_policy(), media_type="text/plain")
