# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Quota limits of a plan.

A limit is a named integer (``max_collections``, ``max_storage_bytes``, ...): the names
and the values belong to the deployment, nothing is built into the code. ``-1`` means
unlimited, a limit that is not defined is ``0``.

The limits of a plan come from the billing service, which is the single place where the
plans are edited (``GET /plans/<app>`` lists the ``limits`` of each plan). When billing
cannot answer (not configured, unreachable, refusing the request, or the plan or its
limits are not defined there) the **fail-safe** limits of the ``QUOTA_FALLBACK_LIMITS``
setting apply, so that a billing outage neither opens the service nor locks everybody out
beyond what the operator decided.
"""

import time

from knowledge.config import get_settings
from knowledge.logging import get_logger
from knowledge.services.billing import BillingAPIError, get_billing_client

logger = get_logger(__name__)

UNLIMITED = -1
WILDCARD = "*"

# Monotonic time until which billing is not asked again after a failure
_billing_unavailable_until = 0.0


def fallback_limits(plan_slug: str) -> dict[str, int]:
    """Return the fail-safe limits of a plan (``QUOTA_FALLBACK_LIMITS``).

    The entry of the plan wins, then the ``*`` entry, then no limit at all.
    """
    configured = get_settings().quota_fallback_limits
    limits = configured.get(plan_slug)
    if limits is None:
        limits = configured.get(WILDCARD, {})
    return dict(limits)


async def billing_limits(plan_slug: str) -> dict[str, int] | None:
    """Return the limits of a plan according to billing, ``None`` when it cannot tell.

    The plan list is cached by the billing client (``BILLING_CACHE_TTL``). After a failure
    billing is not asked again for ``BILLING_FAILURE_BACKOFF`` seconds, so that an outage
    does not add the timeout of a request to every quota check.
    """
    global _billing_unavailable_until

    client = get_billing_client()
    if not client.is_configured or not client.app_slug:
        return None
    if time.monotonic() < _billing_unavailable_until:
        return None

    try:
        plan = await client.get_plan_by_slug(plan_slug)
    except BillingAPIError as error:
        _billing_unavailable_until = time.monotonic() + get_settings().billing_failure_backoff
        logger.warning("Billing unavailable, applying the fail-safe limits: %s", error)
        return None

    if plan is None or plan.limits is None:
        logger.warning("Billing defines no limits for the plan '%s'", plan_slug)
        return None
    return plan.limits


async def get_plan_limits(plan_slug: str) -> dict[str, int]:
    """Return the limits that apply to a plan: billing's, or the fail-safe ones."""
    limits = await billing_limits(plan_slug)
    if limits is None:
        return fallback_limits(plan_slug)
    return limits


def reset_billing_backoff() -> None:
    """Ask billing again at the next quota check (used by the tests)."""
    global _billing_unavailable_until
    _billing_unavailable_until = 0.0
