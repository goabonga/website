# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Email sending service."""

import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from auth.config import settings
from auth.db.models.user import VerificationCode
from auth.db.repositories.email_verification import EmailVerificationRepository
from auth.tasks.email import send_email as send_email_task

if TYPE_CHECKING:
    from auth.services.branding import BrandingConfig

logger = logging.getLogger(__name__)


def generate_verification_code() -> str:
    """Generate a random verification code.

    Returns:
        6-digit verification code.
    """
    return "".join(secrets.choice("0123456789") for _ in range(6))


def hash_code(code: str) -> str:
    """Hash a verification code using SHA-256.

    Args:
        code: Plain text code.

    Returns:
        SHA-256 hash of the code.
    """
    return hashlib.sha256(code.encode()).hexdigest()


class EmailService:
    """Service for sending emails via Celery."""

    def __init__(self, repository: EmailVerificationRepository | None = None) -> None:
        self._repo = repository or EmailVerificationRepository()

    async def send_email(
        self,
        to: str,
        subject: str,
        body_html: str,
        body_text: str = "",
        from_email: str | None = None,
        from_name: str | None = None,
    ) -> bool:
        """Queue an email for async sending via Celery.

        Args:
            to: Recipient email address.
            subject: Email subject.
            body_html: HTML body content.
            body_text: Plain text body content.
            from_email: Sender email (optional, uses platform tenant or global default).
            from_name: Sender name (optional).

        Returns:
            True if queued successfully, False on error.
        """
        try:
            logger.info(f"Queuing email to {to} via Celery")
            send_email_task.delay(to, subject, body_html, body_text, from_email, from_name)
            return True
        except Exception as e:
            logger.error(f"Failed to queue email to {to}: {e}")
            return False

    async def create_verification_code(
        self,
        db: AsyncSession,
        user_id: str,
        email: str,
    ) -> str:
        """Create a new verification code for email.

        Args:
            db: Database session.
            user_id: User ID.
            email: Email to verify.

        Returns:
            Plain text verification code (to send to user).
        """
        code = generate_verification_code()
        code_hash = hash_code(code)

        logger.debug("Creating verification code for user %s, email %s", user_id, email)

        # Convert user_id to UUID if it's a string
        user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id

        verification = VerificationCode(
            user_id=user_uuid,
            email=email.lower(),
            code_hash=code_hash,
            expires_at=datetime.now(UTC) + timedelta(hours=settings.verification_code_expiry_hours),
        )
        await self._repo.add(db, verification)

        logger.info("ACTION: verification_code_create, user_id=%s, email=%s", user_id, email)

        return code

    async def has_valid_verification_code(
        self,
        db: AsyncSession,
        email: str,
    ) -> bool:
        """Check if there's a valid (unused, non-expired) verification code for an email.

        Args:
            db: Database session.
            email: Email address to check.

        Returns:
            True if a valid code exists.
        """
        now = datetime.now(UTC)
        existing = await self._repo.find_valid_for_email(db, email, now)
        return existing is not None

    async def verify_code(
        self,
        db: AsyncSession,
        email: str,
        code: str,
    ) -> bool:
        """Verify an email verification code.

        Args:
            db: Database session.
            email: Email address.
            code: Verification code.

        Returns:
            True if code is valid and email was verified.
        """
        code_hash = hash_code(code)
        now = datetime.now(UTC)

        # Find valid verification code
        verification = await self._repo.find_valid_by_hash(db, email, code_hash, now)

        if not verification:
            logger.warning(f"Invalid or expired verification code for {email}")
            return False

        # Mark code as used
        verification.used_at = now

        # Mark email as verified
        user_email = await self._repo.find_user_email(db, email)

        if user_email:
            user_email.is_verified = True
            user_email.verified_at = now
            logger.info("ACTION: email_verify, user_id=%s, email=%s", user_email.user_id, email)

        await db.commit()
        return True

    async def send_verification_email(
        self,
        db: AsyncSession,
        user_id: str,
        email: str,
        base_url: str | None = None,
        branding: "BrandingConfig | None" = None,
        tenant_id: str | None = None,
    ) -> bool:
        """Create and queue a verification email via Celery.

        Args:
            db: Database session.
            user_id: User ID.
            email: Email address to verify.
            base_url: Base URL for verification link (e.g., https://auth.example.com).
            branding: Optional BrandingConfig for tenant branding.
            tenant_id: Optional tenant UUID string for tenant-specific template overrides.

        Returns:
            True if email was queued successfully, False on error.
        """
        try:
            logger.info(f"Preparing verification email for user {user_id}, email {email}")

            code = await self.create_verification_code(db, user_id, email)

            # Build verification link
            verify_url = ""
            if base_url:
                verify_url = f"{base_url.rstrip('/')}/auth/verify-email?email={email}"

            subject = "Verify your email address"

            from auth.services.email_renderer import get_email_renderer

            renderer = get_email_renderer()
            body_html, body_text = await renderer.render_email_for_tenant(
                db,
                "email_verification",
                {
                    "code": code,
                    "verify_url": verify_url,
                    "verification_code_expiry_hours": settings.verification_code_expiry_hours,
                },
                branding=branding,
                tenant_id=tenant_id,
            )

            await db.commit()

            success = await self.send_email(email, subject, body_html, body_text)
            if success:
                logger.info(f"Verification email queued for {email}")
            else:
                logger.warning(f"Failed to queue verification email for {email}")
            return success
        except Exception as e:
            logger.error(f"Error sending verification email to {email}: {e}")
            return False
