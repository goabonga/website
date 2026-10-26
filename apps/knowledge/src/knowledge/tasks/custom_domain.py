# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Reconciliation of the custom domains with the custom-domain service.

The service tells the application about status changes with signed webhooks. A webhook
can still be lost (the application down for longer than the retries of the service), and
domains that were configured by the application before it used the service have never
been registered there. This periodic task closes both gaps:

* a workspace with a domain but no service id gets the domain registered;
* a workspace whose domain is still being set up is asked for its status.

Nothing here touches DNS, certificates or the web server: that is the service's job.
"""

import asyncio
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from knowledge.celery import celery_app
from knowledge.config import get_settings
from knowledge.models import Organization
from knowledge.models.enums import CustomDomainStatus
from knowledge.services.custom_domain import (
    CustomDomainClient,
    CustomDomainError,
    apply_status,
)

logger = logging.getLogger(__name__)

# The statuses in which the domain is still being set up, so that the status can change
IN_PROGRESS = (
    CustomDomainStatus.PENDING,
    CustomDomainStatus.DNS_VERIFYING,
    CustomDomainStatus.DNS_VERIFIED,
    CustomDomainStatus.SSL_PROVISIONING,
)


async def reconcile(db: AsyncSession, client: CustomDomainClient) -> dict[str, int]:
    """Register the domains the service does not know and refresh those being set up.

    Each workspace is handled in its own transaction: one failure does not block the others.

    Returns:
        Counters: ``registered``, ``updated``, ``failed`` (an error recorded on the
        workspace) and ``errors`` (the service could not be asked).
    """
    counters = {"registered": 0, "updated": 0, "failed": 0, "errors": 0}

    result = await db.execute(
        select(Organization).where(
            Organization.custom_domain.is_not(None),
            (Organization.custom_domain_service_id.is_(None))
            | (Organization.custom_domain_status.in_(IN_PROGRESS)),
        )
    )
    organizations = result.scalars().all()

    for organization in organizations:
        # Read before any rollback: a rolled back object has to be reloaded to be read
        name = organization.custom_domain
        org_id = str(organization.id)
        try:
            if not organization.custom_domain_service_id:
                registered = await client.register(name, org_id)
                organization.custom_domain_service_id = registered.id
                organization.custom_domain_cname_target = registered.cname_target or None
                apply_status(organization, registered.status)
                counters["registered"] += 1
            else:
                details = await client.get(organization.custom_domain_service_id)
                if details is None:
                    # The service lost the domain: the customer can register it again
                    organization.custom_domain_service_id = None
                    organization.custom_domain_status = CustomDomainStatus.FAILED
                    organization.custom_domain_error = (
                        "The custom domain service does not know this domain, register it again"
                    )
                    counters["failed"] += 1
                else:
                    apply_status(organization, details.status, error=details.error_message)
                    counters["updated"] += 1
            await db.commit()
        except CustomDomainError as error:
            await db.rollback()
            logger.warning("Custom domain %s not reconciled: %s", name, error.detail)
            if error.status_code == 409:
                # Registered by someone else: nothing the application can do but tell the customer
                organization.custom_domain_status = CustomDomainStatus.FAILED
                organization.custom_domain_error = error.detail[:500]
                await db.commit()
                counters["failed"] += 1
            else:
                counters["errors"] += 1
        except Exception:
            await db.rollback()
            logger.exception("Failed to reconcile custom domain %s", org_id)
            counters["errors"] += 1

    return counters


def run_async(coro: Any) -> Any:
    """Run a coroutine to completion in a private event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="knowledge.tasks.custom_domain.reconcile_custom_domains")
def reconcile_custom_domains() -> dict:
    """Reconcile the custom domains with the custom-domain service (periodic task).

    Does nothing when the service is not configured.
    """
    client = CustomDomainClient()
    if not client.is_configured:
        logger.debug("Custom domain service not configured, nothing to reconcile")
        return {"skipped": True}

    settings = get_settings()

    async def _process() -> dict[str, int]:
        engine = create_async_engine(settings.database_url)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with session_factory() as db:
                return await reconcile(db, client)
        finally:
            await engine.dispose()

    counters = run_async(_process())
    logger.info("Custom domains reconciled | %s", counters)
    return counters
