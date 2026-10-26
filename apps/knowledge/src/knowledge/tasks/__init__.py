# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Celery tasks for background processing."""

import logging
from datetime import UTC

from knowledge import email_templates
from knowledge.celery import celery_app
from knowledge.config import get_settings
from knowledge.services.mailler import MaillerError, get_mailler_client

logger = logging.getLogger(__name__)


def _send_template(task, to: str, template_slug: str, variables: dict) -> dict:
    """Send a template email through mailler from a Celery task.

    The id of the task is the idempotency key: when mailler accepted the email but the
    answer was lost, the retry of the task does not send a second email. Failures that
    can pass (mailler down, rate limit reached) retry the task with an exponential
    delay; the others (client not registered, template not imported) are returned.

    Returns:
        dict with ``success`` and either the mailler email id or the error
    """
    settings = get_settings()
    task_id = task.request.id
    logger.info("Sending email | to=%s template=%s", to, template_slug)

    try:
        result = get_mailler_client().send_template(
            template_slug,
            to,
            variables,
            idempotency_key=f"{task.name}:{task_id}" if task_id else None,
        )
    except MaillerError as error:
        if error.retryable and task.request.retries < settings.mailler_max_retries:
            delay = settings.mailler_retry_delay * 2**task.request.retries
            logger.warning("Email will be retried | to=%s error=%s", to, error.detail)
            raise task.retry(
                exc=error, countdown=delay, max_retries=settings.mailler_max_retries
            ) from error
        logger.error("Email not sent | to=%s template=%s error=%s", to, template_slug, error.detail)
        return {"success": False, "error": error.detail, "status_code": error.status_code}

    logger.info("Email accepted by mailler | to=%s email_id=%s", to, result.id)
    return {
        "success": True,
        "email_id": result.id,
        "missing_variables": result.missing_variables,
    }


@celery_app.task(bind=True, name="knowledge.tasks.send_email")
def send_email_task(self, to: str, template_slug: str, variables: dict) -> dict:
    """Send an email asynchronously from a template of the application.

    Args:
        to: Recipient email address
        template_slug: Slug of the template imported into mailler for this application
        variables: Values of the template variables

    Returns:
        dict with status and error if any
    """
    return _send_template(self, to, template_slug, variables)


@celery_app.task(bind=True, name="knowledge.tasks.send_workspace_deletion_email")
def send_workspace_deletion_email(
    self,
    to: str,
    workspace_name: str,
    confirmation_url: str,
    year: int,
) -> dict:
    """Send workspace deletion confirmation email.

    Args:
        to: Recipient email address
        workspace_name: Name of the workspace being deleted
        confirmation_url: URL to confirm deletion
        year: Current year for footer

    Returns:
        dict with status and error if any
    """
    return _send_template(
        self,
        to,
        email_templates.WORKSPACE_DELETION,
        {
            "workspace_name": workspace_name,
            "confirmation_url": confirmation_url,
            "user_email": to,
            "year": year,
        },
    )


@celery_app.task(bind=True, name="knowledge.tasks.send_workspace_deletion_scheduled_email")
def send_workspace_deletion_scheduled_email(
    self,
    to: str,
    workspace_name: str,
    deletion_date: str,
    year: int,
) -> dict:
    """Send email notifying that workspace deletion is scheduled.

    Args:
        to: Recipient email address
        workspace_name: Name of the workspace being deleted
        deletion_date: Formatted date when deletion will occur
        year: Current year for footer

    Returns:
        dict with status and error if any
    """
    return _send_template(
        self,
        to,
        email_templates.WORKSPACE_DELETION_SCHEDULED,
        {
            "workspace_name": workspace_name,
            "deletion_date": deletion_date,
            "user_email": to,
            "year": year,
        },
    )


@celery_app.task(bind=True, name="knowledge.tasks.send_workspace_deleted_email")
def send_workspace_deleted_email(
    self,
    to: str,
    workspace_name: str,
    support_url: str,
    year: int,
) -> dict:
    """Send email confirming that workspace has been deleted.

    Args:
        to: Recipient email address
        workspace_name: Name of the workspace that was deleted
        support_url: URL to contact support
        year: Current year for footer

    Returns:
        dict with status and error if any
    """
    return _send_template(
        self,
        to,
        email_templates.WORKSPACE_DELETED,
        {
            "workspace_name": workspace_name,
            "support_url": support_url,
            "user_email": to,
            "year": year,
        },
    )


@celery_app.task(bind=True, name="knowledge.tasks.send_workspace_deletion_reminder_email")
def send_workspace_deletion_reminder_email(
    self,
    to: str,
    workspace_name: str,
    deletion_date: str,
    cancel_url: str,
    year: int,
) -> dict:
    """Send reminder email 1 day before workspace deletion.

    Args:
        to: Recipient email address
        workspace_name: Name of the workspace being deleted
        deletion_date: Formatted date when deletion will occur
        cancel_url: URL to cancel the deletion
        year: Current year for footer

    Returns:
        dict with status and error if any
    """
    return _send_template(
        self,
        to,
        email_templates.WORKSPACE_DELETION_REMINDER,
        {
            "workspace_name": workspace_name,
            "deletion_date": deletion_date,
            "cancel_url": cancel_url,
            "user_email": to,
            "year": year,
        },
    )


@celery_app.task(bind=True, name="knowledge.tasks.send_workspace_invitation_email")
def send_workspace_invitation_email(
    self,
    to: str,
    workspace_name: str,
    inviter_name: str,
    role: str,
    invitation_url: str,
    year: int,
) -> dict:
    """Send workspace invitation email.

    Args:
        to: Recipient email address
        workspace_name: Name of the workspace
        inviter_name: Name/email of the person who sent the invitation
        role: Role assigned to the invitee
        invitation_url: URL to accept the invitation
        year: Current year for footer

    Returns:
        dict with status and error if any
    """
    return _send_template(
        self,
        to,
        email_templates.WORKSPACE_INVITATION,
        {
            "workspace_name": workspace_name,
            "inviter_name": inviter_name,
            "role": role,
            "invitation_url": invitation_url,
            "user_email": to,
            "year": year,
        },
    )


@celery_app.task(bind=True, name="knowledge.tasks.send_deletion_reminders")
def send_deletion_reminders(self) -> dict:
    """Send reminder emails for scheduled deletions happening within 24 hours.

    This task runs periodically to send reminders to users whose workspaces
    are scheduled for deletion within the next 24 hours.

    Returns:
        dict with processing results
    """
    import asyncio
    from datetime import datetime

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.orm import selectinload

    from knowledge.config import get_settings
    from knowledge.models.workspace_deletion_request import (
        DeletionRequestStatus,
        WorkspaceDeletionRequest,
    )

    settings = get_settings()
    logger.info("Starting deletion reminders processing")

    async def _process():
        engine = create_async_engine(settings.database_url)
        async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        sent_count = 0
        error_count = 0

        async with async_session() as db:
            # Get all scheduled deletions that need a reminder
            result = await db.execute(
                select(WorkspaceDeletionRequest)
                .options(selectinload(WorkspaceDeletionRequest.organization))
                .where(
                    WorkspaceDeletionRequest.status == DeletionRequestStatus.SCHEDULED,
                    WorkspaceDeletionRequest.reminder_sent_at.is_(None),
                )
            )
            pending_reminders = result.scalars().all()

            for deletion_request in pending_reminders:
                try:
                    if not deletion_request.needs_reminder:
                        continue

                    if not deletion_request.organization:
                        logger.warning(
                            "Organization not found for deletion request %s",
                            deletion_request.id,
                        )
                        continue

                    workspace_name = deletion_request.organization.name
                    base_url = settings.app_base_url.rstrip("/")
                    cancel_url = (
                        f"{base_url}/organizations/delete/cancel/{deletion_request.cancel_token}"
                    )

                    # Send reminder email
                    scheduled_at = deletion_request.scheduled_deletion_at
                    if not scheduled_at:
                        continue

                    send_workspace_deletion_reminder_email.delay(
                        to=deletion_request.email,
                        workspace_name=workspace_name,
                        deletion_date=scheduled_at.strftime("%B %d, %Y at %H:%M UTC"),
                        cancel_url=cancel_url,
                        year=datetime.now(UTC).year,
                    )

                    # Mark reminder as sent
                    deletion_request.mark_reminder_sent()
                    await db.commit()

                    logger.info(
                        "Deletion reminder sent | org_id=%s email=%s",
                        deletion_request.organization_id,
                        deletion_request.email,
                    )
                    sent_count += 1

                except Exception as e:
                    logger.exception(
                        "Failed to send deletion reminder %s: %s",
                        deletion_request.id,
                        e,
                    )
                    error_count += 1
                    await db.rollback()

        await engine.dispose()
        return {"sent": sent_count, "errors": error_count}

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_process())
    finally:
        loop.close()
    logger.info(
        "Deletion reminders processing complete | sent=%d errors=%d",
        result["sent"],
        result["errors"],
    )
    return result


@celery_app.task(bind=True, name="knowledge.tasks.process_scheduled_deletions")
def process_scheduled_deletions(self) -> dict:
    """Process workspace deletions that are scheduled for today.

    This task runs periodically to delete workspaces whose billing period has ended.

    Returns:
        dict with processing results
    """
    import asyncio
    from datetime import datetime

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from knowledge.config import get_settings
    from knowledge.models import Organization
    from knowledge.models.workspace_deletion_request import (
        DeletionRequestStatus,
        WorkspaceDeletionRequest,
    )

    settings = get_settings()
    logger.info("Starting scheduled deletions processing")

    async def _process():
        engine = create_async_engine(settings.database_url)
        async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        deleted_count = 0
        error_count = 0

        async with async_session() as db:
            # Get all scheduled deletions that are ready to execute
            result = await db.execute(
                select(WorkspaceDeletionRequest).where(
                    WorkspaceDeletionRequest.status == DeletionRequestStatus.SCHEDULED,
                    WorkspaceDeletionRequest.scheduled_deletion_at <= datetime.now(UTC),
                )
            )
            pending_deletions = result.scalars().all()

            logger.info(f"Found {len(pending_deletions)} scheduled deletions to process")

            for deletion_request in pending_deletions:
                try:
                    # Get the organization
                    org_result = await db.execute(
                        select(Organization).where(
                            Organization.id == deletion_request.organization_id
                        )
                    )
                    organization = org_result.scalar_one_or_none()

                    if organization:
                        org_name = organization.name
                        org_id = organization.id

                        # Delete the organization
                        await db.delete(organization)

                        # Mark the deletion request as confirmed
                        deletion_request.execute_scheduled()

                        await db.commit()

                        logger.info(
                            "Scheduled workspace deleted | org_id=%s org_name=%s",
                            org_id,
                            org_name,
                        )
                        deleted_count += 1
                    else:
                        # Organization already deleted, just update status
                        deletion_request.execute_scheduled()
                        await db.commit()
                        logger.warning(
                            "Organization already deleted for deletion request %s",
                            deletion_request.id,
                        )

                except Exception as e:
                    logger.exception(
                        "Failed to process scheduled deletion %s: %s",
                        deletion_request.id,
                        e,
                    )
                    error_count += 1
                    await db.rollback()

        await engine.dispose()
        return {"deleted": deleted_count, "errors": error_count}

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_process())
    finally:
        loop.close()
    logger.info(
        "Scheduled deletions processing complete | deleted=%d errors=%d",
        result["deleted"],
        result["errors"],
    )
    return result
