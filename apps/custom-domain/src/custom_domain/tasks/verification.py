# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""DNS verification tasks."""

from datetime import UTC, datetime

from sqlalchemy import select

from custom_domain.celery import celery_app
from custom_domain.config import settings
from custom_domain.database import get_sync_db
from custom_domain.logging import get_logger
from custom_domain.models import CustomDomain, DomainStatus
from custom_domain.services.dns import dns_service
from custom_domain.services.events import publish_event

logger = get_logger(__name__)


@celery_app.task(
    bind=True,
    max_retries=settings.dns_verification_max_retries,
    default_retry_delay=settings.dns_verification_retry_delay_seconds,
)
def verify_domain_dns(self, domain_id: str) -> None:
    """Verify DNS configuration for a domain.

    Retries with exponential backoff, starting from
    ``DNS_VERIFICATION_RETRY_DELAY_SECONDS`` and doubling each time.
    """
    logger.info("Verifying DNS for domain %s", domain_id)

    with get_sync_db() as db:
        domain = db.execute(
            select(CustomDomain).where(
                CustomDomain.id == domain_id,
                CustomDomain.deleted_at.is_(None),
            )
        ).scalar_one_or_none()

        if not domain:
            logger.warning("Domain %s not found or deleted", domain_id)
            return

        # Publish start event
        publish_event(
            domain_id,
            "step_started",
            {
                "step": "dns_check",
                "message": f"Checking DNS CNAME record for {domain.domain}...",
            },
        )

        # Update status
        domain.status = DomainStatus.DNS_VERIFYING
        domain.last_check_at = datetime.now(UTC)
        db.commit()

        publish_event(
            domain_id,
            "status_change",
            {
                "status": DomainStatus.DNS_VERIFYING.value,
                "previous_status": DomainStatus.PENDING.value,
            },
        )

        # Run DNS check synchronously (it's a sync task)
        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                dns_service.check_cname(domain.domain, domain.cname_target)
            )
        finally:
            loop.close()

        if result.success:
            domain.status = DomainStatus.DNS_VERIFIED
            domain.dns_verified_at = datetime.now(UTC)
            domain.error_message = None
            db.commit()

            logger.info("DNS verified for %s", domain.domain)

            publish_event(
                domain_id,
                "step_completed",
                {
                    "step": "dns_check",
                    "message": f"DNS CNAME verified: {domain.domain} -> {domain.cname_target}",
                },
            )

            publish_event(
                domain_id,
                "status_change",
                {
                    "status": DomainStatus.DNS_VERIFIED.value,
                    "previous_status": DomainStatus.DNS_VERIFYING.value,
                },
            )

            # Trigger SSL provisioning
            from custom_domain.tasks.provisioning import provision_domain_ssl

            provision_domain_ssl.delay(domain_id)

        else:
            domain.error_message = result.error_message
            domain.retry_count += 1
            db.commit()

            logger.warning(
                "DNS verification failed for %s: %s (retry %d/%d)",
                domain.domain,
                result.error_message,
                self.request.retries,
                self.max_retries,
            )

            publish_event(
                domain_id,
                "step_failed",
                {
                    "step": "dns_check",
                    "error": result.error_message,
                    "retry_count": self.request.retries,
                },
            )

            if self.request.retries < self.max_retries:
                # Exponential backoff
                delay = settings.dns_verification_retry_delay_seconds * (2**self.request.retries)
                raise self.retry(countdown=delay)
            else:
                domain.status = DomainStatus.FAILED
                db.commit()

                publish_event(
                    domain_id,
                    "error",
                    {
                        "code": "DNS_VERIFICATION_FAILED",
                        "message": result.error_message,
                        "details": {
                            "expected": domain.cname_target,
                            "actual": result.actual_value,
                        },
                    },
                )


@celery_app.task
def check_pending_domains() -> None:
    """Check all pending domains for DNS verification."""
    logger.info("Checking pending domains")

    with get_sync_db() as db:
        domains = (
            db.execute(
                select(CustomDomain).where(
                    CustomDomain.status.in_(
                        [
                            DomainStatus.PENDING,
                            DomainStatus.DNS_VERIFYING,
                        ]
                    ),
                    CustomDomain.deleted_at.is_(None),
                )
            )
            .scalars()
            .all()
        )

        for domain in domains:
            # Skip if recently checked (within last check interval)
            if domain.last_check_at:
                elapsed = datetime.now(UTC) - domain.last_check_at.replace(tzinfo=UTC)
                if elapsed.total_seconds() < settings.dns_check_interval_minutes * 60:
                    continue

            verify_domain_dns.delay(str(domain.id))

        logger.info("Triggered verification for %d domains", len(domains))
