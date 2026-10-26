# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Password reset service."""

import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from auth.config import settings
from auth.core.security import hash_password, verify_password
from auth.db.models.user import PasswordResetToken, User, UserPassword
from auth.db.repositories.password_reset import PasswordResetRepository

logger = logging.getLogger(__name__)


def generate_reset_token() -> str:
    """Generate a secure random token for password reset.

    Returns:
        32-character hex token.
    """
    return secrets.token_hex(16)


def hash_token(token: str) -> str:
    """Hash a reset token using SHA-256.

    Args:
        token: Plain text token.

    Returns:
        SHA-256 hash of the token.
    """
    return hashlib.sha256(token.encode()).hexdigest()


class PasswordService:
    """Service for password reset operations."""

    def __init__(self, repository: PasswordResetRepository | None = None) -> None:
        self._repo = repository or PasswordResetRepository()

    async def create_reset_token(
        self,
        db: AsyncSession,
        email: str,
    ) -> tuple[str, str] | None:
        """Create a password reset token for an email.

        Args:
            db: Database session.
            email: Email address to reset password for.

        Returns:
            Tuple of (token, user_id) if email exists, None otherwise.
        """
        logger.info("Password reset requested for email: %s", email.lower())

        # Find user by email (must be verified)
        user_email = await self._repo.find_verified_user_email(db, email)

        if not user_email:
            logger.warning(
                "Password reset failed: email not found or not verified: %s", email.lower()
            )
            return None

        # Generate token
        token = generate_reset_token()
        token_hash = hash_token(token)

        # Create reset token
        reset_token = PasswordResetToken(
            user_id=user_email.user_id,
            email=email.lower(),
            token_hash=token_hash,
            expires_at=datetime.now(UTC) + timedelta(hours=settings.password_reset_expiry_hours),
        )
        await self._repo.add_reset_token(db, reset_token)

        logger.info("Password reset token created for user %s", user_email.user_id)
        return token, str(user_email.user_id)

    async def verify_reset_token(
        self,
        db: AsyncSession,
        token: str,
    ) -> PasswordResetToken | None:
        """Verify a password reset token.

        Args:
            db: Database session.
            token: Reset token.

        Returns:
            PasswordResetToken if valid, None otherwise.
        """
        token_hash = hash_token(token)
        now = datetime.now(UTC)
        return await self._repo.find_valid_by_hash(db, token_hash, now)

    async def reset_password(
        self,
        db: AsyncSession,
        token: str,
        new_password: str,
    ) -> bool:
        """Reset a user's password using a valid token.

        Args:
            db: Database session.
            token: Reset token.
            new_password: New password to set.

        Returns:
            True if password was reset, False otherwise.
        """
        reset_token = await self.verify_reset_token(db, token)

        if not reset_token:
            logger.warning("Password reset failed: invalid or expired token")
            return False

        # Mark token as used
        reset_token.used_at = datetime.now(UTC)

        # Get user
        user = await self._repo.find_user_for_reset(db, reset_token.user_id)

        if not user:
            logger.warning("Password reset failed: user not found for token")
            return False

        # Load passwords relationship
        await db.refresh(user, ["passwords"])

        # Mark old passwords as not current
        for password in user.passwords:
            if password.is_current:
                password.is_current = False

        # Create new password
        new_password_record = UserPassword(
            user_id=user.id,
            password_hash=hash_password(new_password),
            is_current=True,
        )
        await self._repo.add_password(db, new_password_record)

        await db.commit()
        logger.info("Password reset successful for user %s", user.id)
        return True

    async def get_user_by_reset_token(
        self,
        db: AsyncSession,
        token: str,
    ) -> User | None:
        """Get user associated with a reset token.

        Args:
            db: Database session.
            token: Reset token.

        Returns:
            User if token is valid, None otherwise.
        """
        reset_token = await self.verify_reset_token(db, token)

        if not reset_token:
            return None

        return await self._repo.find_user_for_reset(db, reset_token.user_id)

    async def change_password(
        self,
        db: AsyncSession,
        user_id: str,
        current_password: str,
        new_password: str,
    ) -> tuple[bool, str | None]:
        """Change a user's password after verifying the current password.

        Args:
            db: Database session.
            user_id: User ID.
            current_password: Current password for verification.
            new_password: New password to set.

        Returns:
            Tuple of (success, error_message).
            If success is True, error_message is None.
            If success is False, error_message contains the reason.
        """
        logger.info("Password change requested for user_id=%s", user_id)

        # Get user with passwords
        try:
            user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
            user = await self._repo.find_user_for_reset(db, user_uuid)
        except (ValueError, TypeError):
            user = None

        if not user:
            logger.warning("Password change failed: user not found user_id=%s", user_id)
            return False, "User not found"

        # Load passwords relationship
        await db.refresh(user, ["passwords"])

        # Find current password
        current_password_record = next(
            (p for p in user.passwords if p.is_current),
            None,
        )

        if not current_password_record:
            logger.warning("Password change failed: no current password for user_id=%s", user_id)
            return False, "No current password found"

        # Verify current password
        if not verify_password(current_password, current_password_record.password_hash):
            logger.warning(
                "Password change failed: incorrect current password for user_id=%s", user_id
            )
            return False, "Current password is incorrect"

        # Mark old password as not current
        current_password_record.is_current = False

        # Create new password
        new_password_record = UserPassword(
            user_id=user.id,
            password_hash=hash_password(new_password),
            is_current=True,
        )
        await self._repo.add_password(db, new_password_record)

        await db.flush()
        logger.info("Password changed successfully for user_id=%s", user_id)
        return True, None
