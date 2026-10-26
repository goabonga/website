# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Maintenance tasks."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from custom_domain.celery import celery_app
from custom_domain.config import settings
from custom_domain.database import get_sync_db
from custom_domain.logging import get_logger
from custom_domain.models import CustomDomain, DomainStatus
from custom_domain.services.certbot import certbot_service
from custom_domain.services.dns import dns_service
from custom_domain.tasks.provisioning import deprovision_domain, provision_domain_ssl, run_async

logger = get_logger(__name__)


def soft_delete_domain(db, domain: CustomDomain, reason: str) -> None:
    """Soft delete a domain and deprovision its resources."""
    logger.info(
        "Soft deleting domain %s: %s",
        domain.domain,
        reason,
    )

    domain.deleted_at = datetime.now(UTC)
    domain.error_message = reason
    db.commit()

    # Trigger deprovisioning (remove nginx config). The certificate is kept: only an
    # explicit deletion by the client revokes it, a DNS hiccup must not destroy it.
    deprovision_domain.delay(str(domain.id), False)


@celery_app.task
def check_certificate_expiry() -> None:
    """Check for certificates expiring soon and trigger renewal."""
    logger.info("Checking certificate expiry")

    renewal_threshold = timedelta(days=settings.certificate_renewal_days)
    threshold_date = datetime.now(UTC) + renewal_threshold

    with get_sync_db() as db:
        domains = (
            db.execute(
                select(CustomDomain).where(
                    CustomDomain.status == DomainStatus.ACTIVE,
                    CustomDomain.deleted_at.is_(None),
                    CustomDomain.ssl_expires_at.isnot(None),
                    CustomDomain.ssl_expires_at < threshold_date,
                )
            )
            .scalars()
            .all()
        )

        for domain in domains:
            logger.info(
                "Certificate expiring soon for %s (expires %s)",
                domain.domain,
                domain.ssl_expires_at,
            )

            # Check actual certificate status
            cert_info = run_async(certbot_service.check_certificate(domain.domain))

            if cert_info and cert_info.days_until_expiry <= settings.certificate_renewal_days:
                # Trigger renewal via reprovisioning
                provision_domain_ssl.delay(str(domain.id))
                logger.info("Triggered renewal for %s", domain.domain)

        logger.info("Checked %d domains for certificate expiry", len(domains))


@celery_app.task
def check_domain_health() -> None:
    """Check if active domains still have valid DNS configuration."""
    logger.info("Checking domain health")

    with get_sync_db() as db:
        domains = (
            db.execute(
                select(CustomDomain).where(
                    CustomDomain.status == DomainStatus.ACTIVE,
                    CustomDomain.deleted_at.is_(None),
                )
            )
            .scalars()
            .all()
        )

        healthy_count = 0
        unhealthy_count = 0

        for domain in domains:
            # Check DNS is still valid
            result = run_async(dns_service.check_cname(domain.domain, domain.cname_target))

            domain.last_check_at = datetime.now(UTC)

            if result.success:
                healthy_count += 1
                domain.error_message = None
            else:
                unhealthy_count += 1
                logger.warning(
                    "Domain %s health check failed: %s",
                    domain.domain,
                    result.error_message,
                )
                domain.error_message = f"Health check failed: {result.error_message}"
                domain.status = DomainStatus.FAILED

                # Soft delete unhealthy domain
                soft_delete_domain(
                    db,
                    domain,
                    f"DNS no longer valid: {result.error_message}",
                )

            db.commit()

        logger.info(
            "Health check completed: %d healthy, %d unhealthy",
            healthy_count,
            unhealthy_count,
        )


@celery_app.task
def cleanup_stale_domains() -> None:
    """Soft delete domains that failed to activate within the timeout period."""
    logger.info("Cleaning up stale domains")

    timeout_threshold = datetime.now(UTC) - timedelta(
        hours=settings.domain_activation_timeout_hours
    )

    with get_sync_db() as db:
        # Find domains that are not ACTIVE and were created before threshold
        domains = (
            db.execute(
                select(CustomDomain).where(
                    CustomDomain.status.in_(
                        [
                            DomainStatus.PENDING,
                            DomainStatus.DNS_VERIFYING,
                            DomainStatus.DNS_VERIFIED,
                            DomainStatus.SSL_PROVISIONING,
                            DomainStatus.FAILED,
                        ]
                    ),
                    CustomDomain.deleted_at.is_(None),
                    CustomDomain.created_at < timeout_threshold,
                )
            )
            .scalars()
            .all()
        )

        for domain in domains:
            soft_delete_domain(
                db,
                domain,
                f"Failed to activate within {settings.domain_activation_timeout_hours} hours",
            )

        logger.info("Soft deleted %d stale domains", len(domains))


@celery_app.task
def purge_deleted_domains() -> None:
    """Permanently delete soft-deleted domains after retention period."""
    logger.info("Purging deleted domains")

    purge_threshold = datetime.now(UTC) - timedelta(days=settings.soft_delete_purge_days)

    with get_sync_db() as db:
        domains = (
            db.execute(
                select(CustomDomain).where(
                    CustomDomain.deleted_at.isnot(None),
                    CustomDomain.deleted_at < purge_threshold,
                )
            )
            .scalars()
            .all()
        )

        for domain in domains:
            logger.info(
                "Permanently deleting domain %s (deleted at %s)",
                domain.domain,
                domain.deleted_at,
            )
            db.delete(domain)

        db.commit()
        logger.info("Permanently deleted %d domains", len(domains))
