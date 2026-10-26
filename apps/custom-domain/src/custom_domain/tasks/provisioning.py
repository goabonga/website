# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""SSL provisioning tasks."""

import asyncio
from datetime import UTC, datetime

from celery.exceptions import Retry
from sqlalchemy import select
from sqlalchemy.orm import Session

from custom_domain.celery import celery_app
from custom_domain.config import settings
from custom_domain.database import get_sync_db
from custom_domain.logging import get_logger
from custom_domain.models import AuthorizedClient, CustomDomain, DomainStatus, NginxTemplate
from custom_domain.services.certbot import certbot_service
from custom_domain.services.events import publish_event
from custom_domain.services.nginx import nginx_manager

logger = get_logger(__name__)


def run_async(coro):
    """Run an async coroutine in a sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def resolve_template(db: Session, domain: CustomDomain) -> NginxTemplate | None:
    """Pick the nginx template of a domain.

    Resolution order: the domain's own template, the default template of the
    domain's client, then the global default. Inactive templates are skipped.
    ``None`` means the default files shipped with the package.
    """
    if domain.nginx_template_id:
        template = db.execute(
            select(NginxTemplate).where(
                NginxTemplate.id == domain.nginx_template_id,
                NginxTemplate.is_active == True,  # noqa: E712
            )
        ).scalar_one_or_none()
        if template:
            return template

    client_template_id = db.execute(
        select(AuthorizedClient.default_nginx_template_id).where(
            AuthorizedClient.client_id == domain.client_id
        )
    ).scalar_one_or_none()
    if client_template_id:
        template = db.execute(
            select(NginxTemplate).where(
                NginxTemplate.id == client_template_id,
                NginxTemplate.is_active == True,  # noqa: E712
            )
        ).scalar_one_or_none()
        if template:
            return template

    return db.execute(
        select(NginxTemplate).where(
            NginxTemplate.is_default == True,  # noqa: E712
            NginxTemplate.is_active == True,  # noqa: E712
        )
    ).scalar_one_or_none()


@celery_app.task(
    bind=True,
    max_retries=settings.provisioning_max_retries,
    default_retry_delay=settings.provisioning_retry_delay_seconds,
)
def provision_domain_ssl(self, domain_id: str) -> None:
    """Provision SSL certificate and nginx configuration.

    Retries with exponential backoff, starting from
    ``PROVISIONING_RETRY_DELAY_SECONDS`` and doubling each time.
    """
    logger.info("Provisioning SSL for domain %s", domain_id)

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

        # Get template
        template = resolve_template(db, domain)

        # Update status
        domain.status = DomainStatus.SSL_PROVISIONING
        db.commit()

        publish_event(
            domain_id,
            "status_change",
            {
                "status": DomainStatus.SSL_PROVISIONING.value,
                "previous_status": DomainStatus.DNS_VERIFIED.value,
            },
        )

        try:
            # Step 1: Write HTTP-only nginx config
            publish_event(
                domain_id,
                "step_started",
                {
                    "step": "nginx_http",
                    "message": "Writing HTTP-only nginx configuration...",
                },
            )

            http_config = run_async(nginx_manager.generate_http_config(domain, template))
            run_async(nginx_manager.write_config(domain.domain, http_config))
            run_async(nginx_manager.reload())

            publish_event(
                domain_id,
                "step_completed",
                {
                    "step": "nginx_http",
                    "message": "HTTP nginx configuration written successfully",
                },
            )

            # Step 2: Provision SSL certificate
            publish_event(
                domain_id,
                "step_started",
                {
                    "step": "certbot",
                    "message": "Requesting SSL certificate from Let's Encrypt...",
                },
            )

            cert_result = run_async(certbot_service.provision_certificate(domain.domain))

            if not cert_result.success:
                publish_event(
                    domain_id,
                    "step_failed",
                    {
                        "step": "certbot",
                        "error": cert_result.error_message,
                    },
                )

                domain.error_message = cert_result.error_message

                # Check if retriable
                if "rate limit" in (cert_result.error_message or "").lower():
                    db.commit()
                    if self.request.retries < self.max_retries:
                        delay = settings.provisioning_retry_delay_seconds * (
                            2**self.request.retries
                        )
                        raise self.retry(countdown=delay)

                domain.status = DomainStatus.FAILED
                db.commit()

                publish_event(
                    domain_id,
                    "error",
                    {
                        "code": "SSL_PROVISIONING_FAILED",
                        "message": cert_result.error_message,
                    },
                )
                return

            publish_event(
                domain_id,
                "step_completed",
                {
                    "step": "certbot",
                    "message": "SSL certificate obtained successfully",
                },
            )

            # Step 3: Write full HTTPS nginx config
            publish_event(
                domain_id,
                "step_started",
                {
                    "step": "nginx_https",
                    "message": "Writing HTTPS nginx configuration...",
                },
            )

            https_config = run_async(nginx_manager.generate_https_config(domain, template))
            run_async(nginx_manager.write_config(domain.domain, https_config))
            run_async(nginx_manager.reload())

            publish_event(
                domain_id,
                "step_completed",
                {
                    "step": "nginx_https",
                    "message": "HTTPS nginx configuration written successfully",
                },
            )

            # Update domain status
            domain.status = DomainStatus.ACTIVE
            domain.ssl_provisioned_at = datetime.now(UTC)
            domain.ssl_expires_at = cert_result.expires_at
            domain.error_message = None
            db.commit()

            logger.info(
                "SSL provisioned for %s, expires at %s",
                domain.domain,
                cert_result.expires_at,
            )

            publish_event(
                domain_id,
                "status_change",
                {
                    "status": DomainStatus.ACTIVE.value,
                    "previous_status": DomainStatus.SSL_PROVISIONING.value,
                },
            )

            publish_event(
                domain_id,
                "completed",
                {
                    "status": DomainStatus.ACTIVE.value,
                    "ssl_expires_at": (
                        cert_result.expires_at.isoformat() if cert_result.expires_at else None
                    ),
                },
            )

        except Retry:
            # Let Celery reschedule the task instead of marking the domain as failed.
            raise

        except self.MaxRetriesExceededError:
            domain.status = DomainStatus.FAILED
            db.commit()

            publish_event(
                domain_id,
                "error",
                {
                    "code": "MAX_RETRIES_EXCEEDED",
                    "message": "Maximum retry attempts exceeded",
                },
            )

        except Exception as e:
            logger.exception("SSL provisioning failed for %s", domain.domain)
            domain.status = DomainStatus.FAILED
            domain.error_message = str(e)[:500]
            db.commit()

            publish_event(
                domain_id,
                "error",
                {
                    "code": "PROVISIONING_ERROR",
                    "message": str(e),
                },
            )


@celery_app.task(
    bind=True,
    max_retries=settings.provisioning_max_retries,
    default_retry_delay=settings.provisioning_retry_delay_seconds,
)
def deprovision_domain(self, domain_id: str, revoke_certificate: bool = True) -> None:
    """Take a domain out of service and finish its deletion.

    The API only marks a domain ``deprovisioning``; the privileged work happens
    here: the nginx file is removed and nginx reloaded, then the certificate is
    revoked (``CERTBOT_REVOKE_ON_DEPROVISION`` and ``revoke_certificate``; a failed
    revocation is logged and does not stop the deletion). A caller that retires a
    domain on its own initiative (the maintenance tasks) passes
    ``revoke_certificate=False``: only an explicit deletion revokes. Failures of the nginx step are retried; once the
    retries are exhausted the domain is marked ``failed`` and kept. On success
    the domain is soft-deleted.
    """
    logger.info("Deprovisioning domain %s", domain_id)

    with get_sync_db() as db:
        domain = db.execute(
            select(CustomDomain).where(CustomDomain.id == domain_id)
        ).scalar_one_or_none()

        if not domain:
            logger.warning("Domain %s not found", domain_id)
            return

        previous_status = domain.status
        if previous_status != DomainStatus.DEPROVISIONING:
            domain.status = DomainStatus.DEPROVISIONING
            db.commit()
            publish_event(
                domain_id,
                "status_change",
                {
                    "status": DomainStatus.DEPROVISIONING.value,
                    "previous_status": previous_status.value,
                },
            )

        try:
            run_async(nginx_manager.remove_config(domain.domain))
            run_async(nginx_manager.reload())
        except Exception as e:
            logger.warning("Failed to deprovision domain %s: %s", domain.domain, e)
            if self.request.retries < self.max_retries:
                raise self.retry(
                    exc=e,
                    countdown=settings.provisioning_retry_delay_seconds * (2**self.request.retries),
                )
            domain.status = DomainStatus.FAILED
            domain.error_message = f"Deprovisioning failed: {e}"[:500]
            db.commit()
            publish_event(
                domain_id,
                "error",
                {"code": "DEPROVISIONING_FAILED", "message": str(e)},
            )
            return

        if revoke_certificate and settings.certbot_revoke_on_deprovision:
            revoked = run_async(certbot_service.revoke_certificate(domain.domain))
            if not revoked.success:
                logger.warning(
                    "Certificate of %s was not revoked: %s", domain.domain, revoked.error_message
                )

        domain.deleted_at = domain.deleted_at or datetime.now(UTC)
        db.commit()
        logger.info("Domain %s deprovisioned", domain.domain)

        publish_event(
            domain_id,
            "completed",
            {"status": DomainStatus.DEPROVISIONING.value, "deleted": True},
        )
