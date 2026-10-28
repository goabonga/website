# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Custom domain of an organisation: change, remove, verify and report its state.

The organisation settings pages and the REST API change the custom domain the same way,
so the rules live here: a new domain starts in the ``PENDING`` state and queues the DNS
verification, removing it clears the state and queues the removal of its configuration, and
a change is announced to the webhooks of the organisation (``tenant.updated``). The Celery
tasks are queued after the commit.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from auth.db.models.tenant import CustomDomainStatus, Tenant, WebhookEvent
from auth.services.webhook import safe_dispatch

logger = logging.getLogger(__name__)

DOMAIN_PATTERN = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.[A-Za-z0-9-]{1,63})*\.[A-Za-z]{2,}$")

# Sends a tenant event: ``dispatch(db, tenant_id=..., event=WebhookEvent, data={...})``; the
# default is the best-effort ``safe_dispatch`` (a webhook that cannot be queued never breaks
# the change).
DispatchTenantEvent = Callable[..., Awaitable[None]]


class VerificationOutcome(StrEnum):
    """What asking for a verification of the domain did."""

    NO_DOMAIN = "no_domain"  # nothing to verify
    ALREADY_ACTIVE = "already_active"  # nothing to do
    IN_PROGRESS = "in_progress"  # a verification or the SSL provisioning is running
    STARTED = "started"  # the state is ``PENDING`` and the verification is queued


@dataclass(frozen=True)
class DomainChange:
    """The result of setting or removing the custom domain."""

    changed: bool
    old_domain: str | None
    new_domain: str | None


def is_valid_domain(domain: str) -> bool:
    """Whether ``domain`` is a well formed host name (labels, then an alphabetic top level)."""
    return len(domain) <= 253 and bool(DOMAIN_PATTERN.match(domain))


class CustomDomainService:
    """Custom domain flows of an organisation (the caller owns the HTTP side)."""

    @staticmethod
    def status(tenant: Tenant) -> dict[str, Any]:
        """The domain and the state of its verification, for polling."""
        return {
            "custom_domain": tenant.custom_domain,
            "status": tenant.custom_domain_status.value if tenant.custom_domain_status else None,
            "error": tenant.custom_domain_error,
            "verified_at": tenant.custom_domain_verified_at.isoformat()
            if tenant.custom_domain_verified_at
            else None,
            "ssl_at": tenant.custom_domain_ssl_at.isoformat()
            if tenant.custom_domain_ssl_at
            else None,
            "checked_at": tenant.custom_domain_checked_at.isoformat()
            if tenant.custom_domain_checked_at
            else None,
        }

    async def set_domain(
        self,
        db: AsyncSession,
        tenant: Tenant,
        custom_domain: str | None,
        *,
        actor_id: uuid.UUID,
        dispatch: DispatchTenantEvent | None = None,
    ) -> DomainChange:
        """Set, change or remove (``None``) the custom domain, then commit.

        Nothing is written when the domain is the current one. Otherwise the verification
        state is reset (``PENDING`` for a domain, cleared for a removal), ``tenant.updated``
        is dispatched, the transaction is committed and the Celery task is queued: the DNS
        verification of the new domain, or the removal of the configuration of the old one.
        """
        old_domain = tenant.custom_domain
        if custom_domain == old_domain:
            return DomainChange(False, old_domain, custom_domain)

        tenant.custom_domain = custom_domain
        # a new domain waits for its DNS verification, a removed one has no state
        tenant.custom_domain_status = CustomDomainStatus.PENDING if custom_domain else None
        tenant.custom_domain_verified_at = None
        tenant.custom_domain_ssl_at = None
        tenant.custom_domain_error = None
        tenant.custom_domain_checked_at = None

        await (dispatch or safe_dispatch)(
            db,
            tenant_id=tenant.id,
            event=WebhookEvent.TENANT_UPDATED,
            data={
                "tenant_id": str(tenant.id),
                "display_name": tenant.display_name,
                "custom_domain": custom_domain,
                "actor_id": str(actor_id),
            },
        )

        await db.commit()

        # Trigger tasks after commit
        if custom_domain:
            from auth.tasks.custom_domain import verify_custom_domain_dns

            verify_custom_domain_dns.delay(str(tenant.id), custom_domain, tenant.slug)
            logger.info(
                "User %s configured custom domain %s for org %s", actor_id, custom_domain, tenant.id
            )
        elif old_domain:
            from auth.tasks.custom_domain import remove_custom_domain_config

            remove_custom_domain_config.delay(old_domain, tenant.slug)
            logger.info(
                "User %s removed custom domain %s from org %s", actor_id, old_domain, tenant.id
            )
        return DomainChange(True, old_domain, custom_domain)

    async def start_verification(
        self, db: AsyncSession, tenant: Tenant, *, actor_id: uuid.UUID
    ) -> VerificationOutcome:
        """Ask for the DNS verification of the configured domain.

        Resets the state to ``PENDING``, commits and queues ``verify_custom_domain_dns``,
        unless there is no domain, it is already active or a verification is running.
        """
        if not tenant.custom_domain:
            return VerificationOutcome.NO_DOMAIN

        if tenant.custom_domain_status == CustomDomainStatus.ACTIVE:
            return VerificationOutcome.ALREADY_ACTIVE

        if tenant.custom_domain_status in [
            CustomDomainStatus.SSL_PROVISIONING,
            CustomDomainStatus.DNS_VERIFYING,
        ]:
            return VerificationOutcome.IN_PROGRESS

        # Reset status to pending and trigger verification
        tenant.custom_domain_status = CustomDomainStatus.PENDING
        tenant.custom_domain_error = None
        await db.commit()

        from auth.tasks.custom_domain import verify_custom_domain_dns

        verify_custom_domain_dns.delay(str(tenant.id), tenant.custom_domain, tenant.slug)

        logger.info(
            "User %s triggered manual domain verification for %s", actor_id, tenant.custom_domain
        )
        return VerificationOutcome.STARTED


custom_domain_service = CustomDomainService()
