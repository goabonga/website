# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Authentication service."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from auth.core.security import verify_password
from auth.db.models.user import User
from auth.services.user import UserService

logger = logging.getLogger(__name__)


class AuthService:
    """Service for authentication operations.

    Delegates user/email lookups to :class:`UserService` so that all SQL
    access stays in the repository layer.
    """

    def __init__(self, user_service: UserService | None = None) -> None:
        self._user_service = user_service or UserService()

    async def authenticate(
        self,
        db: AsyncSession,
        email: str,
        password: str,
    ) -> User | None:
        """Authenticate a user by email and password.

        Args:
            db: Database session.
            email: User email.
            password: User password.

        Returns:
            User if authentication successful, None otherwise.
        """
        logger.info("Authentication attempt for email: %s", email.lower())

        # Find user by verified email
        user_email = await self._user_service.get_verified_email_with_user(db, email)

        if not user_email:
            logger.warning(
                "Authentication failed: email not found or not verified: %s", email.lower()
            )
            return None

        user = user_email.user

        if not user.is_active:
            logger.warning("Authentication failed: user account is inactive: %s", user.id)
            return None

        # Load passwords via the user service
        user_loaded = await self._user_service.get_by_id_with_passwords(db, user.id)

        if not user_loaded:
            return None

        # Find current password
        current_password = None
        for pwd in user_loaded.passwords:
            if pwd.is_current:
                current_password = pwd
                break

        if not current_password:
            logger.warning(
                "Authentication failed: no current password set for user: %s", user_loaded.id
            )
            return None

        # Verify password
        if not verify_password(password, current_password.password_hash):
            logger.warning("Authentication failed: invalid password for user: %s", user_loaded.id)
            return None

        logger.info("Authentication successful for user: %s", user_loaded.id)
        return user_loaded

    async def verify_credentials(
        self,
        db: AsyncSession,
        email: str,
        password: str,
    ) -> User | None:
        """Backward-compatible alias for credential verification."""
        return await self.authenticate(db, email, password)

    async def get_user_primary_email(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> str | None:
        """Get the primary email for a user.

        Args:
            db: Database session.
            user_id: User ID.

        Returns:
            Primary email address or None.
        """
        user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))

        user_email = await self._user_service.get_primary_email_row(db, user_uuid)
        if user_email:
            return user_email.email

        # Fallback to first verified email
        user_email = await self._user_service.get_first_verified_email_row(db, user_uuid)
        return user_email.email if user_email else None
