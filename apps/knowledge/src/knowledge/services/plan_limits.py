# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Quota limits of a plan.

A limit is a named integer (``max_collections``, ``max_storage_bytes``, ...): the names
and the values belong to the deployment, nothing is built into the code. ``-1`` means
unlimited, a limit that is not defined is ``0``.
"""

from knowledge.config import get_settings

UNLIMITED = -1
WILDCARD = "*"


def fallback_limits(plan_slug: str) -> dict[str, int]:
    """Return the configured limits of a plan (``QUOTA_FALLBACK_LIMITS``).

    The entry of the plan wins, then the ``*`` entry, then no limit at all.
    """
    configured = get_settings().quota_fallback_limits
    limits = configured.get(plan_slug)
    if limits is None:
        limits = configured.get(WILDCARD, {})
    return dict(limits)


async def get_plan_limits(plan_slug: str) -> dict[str, int]:
    """Return the limits that apply to a plan."""
    return fallback_limits(plan_slug)
