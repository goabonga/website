# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Session management service."""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from auth.config import settings
from auth.db.models.user import Session, User
from auth.db.repositories.session import SessionRepository
from auth.db.repositories.user import UserRepository

logger = logging.getLogger(__name__)


def generate_token() -> str:
    """Generate a secure random token.

    Returns:
        32-character hex token.
    """
    return secrets.token_hex(32)


def hash_token(token: str) -> str:
    """Hash a token using SHA-256.

    Args:
        token: Plain text token.

    Returns:
        SHA-256 hash of the token.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def _as_uuid(value: str | uuid.UUID) -> uuid.UUID:
    """Normalise a value to ``uuid.UUID``."""
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


class SessionService:
    """Service for managing user sessions.

    Orchestrates session-related business flows (token generation, CSRF
    verification, sliding expiry). SQL access is delegated to
    :class:`SessionRepository`.
    """

    def __init__(
        self,
        repository: SessionRepository | None = None,
        user_repository: UserRepository | None = None,
    ) -> None:
        self._repo = repository or SessionRepository()
        self._user_repo = user_repository or UserRepository()

    def generate_session_token(self) -> str:
        """Generate a new session token."""
        return generate_token()

    def generate_csrf_token(self) -> str:
        """Generate a new CSRF token."""
        return generate_token()

    async def add(self, db: AsyncSession, session: Session) -> Session:
        """Stage a pre-built :class:`Session` row and flush.

        Used by flows that need to construct the row themselves (e.g.
        federation callbacks) but should not touch ``db.add`` directly.
        The caller owns the transaction boundary.
        """
        await self._repo.add(db, session)
        return session

    async def create_session(
        self,
        db: AsyncSession,
        user_id: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[str, str]:
        """Create a new session for a user.

        Args:
            db: Database session.
            user_id: User ID.
            ip_address: Client IP address.
            user_agent: Client user agent.

        Returns:
            Tuple of (session_token, csrf_token).
        """
        session_token = self.generate_session_token()
        csrf_token = self.generate_csrf_token()

        session = Session(
            user_id=user_id,
            session_token_hash=hash_token(session_token),
            csrf_token_hash=hash_token(csrf_token),
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=datetime.now(UTC) + timedelta(days=settings.session_expiry_days),
        )
        await self._repo.add(db, session)

        logger.info("ACTION: session_create, user_id=%s, ip=%s", user_id, ip_address)
        return session_token, csrf_token

    async def get_session_by_token(
        self,
        db: AsyncSession,
        session_token: str,
    ) -> Session | None:
        """Get a valid session by token.

        Args:
            db: Database session.
            session_token: Session token.

        Returns:
            Session if valid, None otherwise.
        """
        return await self._repo.find_by_token_hash(db, hash_token(session_token), active_only=True)

    async def get_session_with_user_by_token(
        self,
        db: AsyncSession,
        session_token: str,
    ) -> Session | None:
        """Get a non-revoked session with ``user`` eager-loaded by token.

        Expiration is the caller's responsibility; this mirrors the
        ``deps.get_current_user`` legacy query so callers can inspect
        ``session.expires_at`` before trusting the return value.
        """
        return await self._repo.find_by_token_hash_with_user(db, hash_token(session_token))

    async def get_user_by_session_token(
        self,
        db: AsyncSession,
        session_token: str,
    ) -> User | None:
        """Get user from a valid session token.

        Args:
            db: Database session.
            session_token: Session token.

        Returns:
            User if session is valid, None otherwise.
        """
        session = await self.get_session_by_token(db, session_token)

        if not session:
            return None

        user = await self._user_repo.find_by_id(db, session.user_id)
        if user is None or not user.is_active:
            return None
        return user

    async def verify_csrf_token(
        self,
        db: AsyncSession,
        session_token: str,
        csrf_token: str,
    ) -> bool:
        """Verify a CSRF token for a session.

        Args:
            db: Database session.
            session_token: Session token.
            csrf_token: CSRF token to verify.

        Returns:
            True if CSRF token is valid for the session.
        """
        session = await self.get_session_by_token(db, session_token)

        if not session:
            logger.warning("CSRF verification failed: session not found")
            return False

        if session.csrf_token_hash != hash_token(csrf_token):
            logger.warning("CSRF verification failed: token mismatch for session %s", session.id)
            return False

        return True

    async def revoke_session(
        self,
        db: AsyncSession,
        session_token: str,
    ) -> bool:
        """Revoke a session.

        Args:
            db: Database session.
            session_token: Session token to revoke.

        Returns:
            True if session was revoked.
        """
        session = await self.get_session_by_token(db, session_token)

        if not session:
            logger.warning("Session revocation failed: session not found")
            return False

        await self._repo.revoke(db, session)
        logger.info(
            "ACTION: session_revoke, session_id=%s, user_id=%s", session.id, session.user_id
        )
        return True

    async def revoke_all_user_sessions(
        self,
        db: AsyncSession,
        user_id: str,
        except_session_id: str | None = None,
    ) -> int:
        """Revoke all sessions for a user.

        Args:
            db: Database session.
            user_id: User ID.
            except_session_id: Session ID to exclude from revocation (current session).

        Returns:
            Number of sessions revoked.
        """
        except_uuid = _as_uuid(except_session_id) if except_session_id else None
        sessions = await self._repo.list_active_for_user(
            db,
            _as_uuid(user_id),
            except_session_id=except_uuid,
        )

        await self._repo.revoke_many(db, sessions)
        logger.info("ACTION: session_revoke_all, user_id=%s, count=%d", user_id, len(sessions))
        return len(sessions)

    async def get_user_sessions(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> list[Session]:
        """Get all active sessions for a user.

        Args:
            db: Database session.
            user_id: User ID.

        Returns:
            List of active sessions.
        """
        return await self._repo.list_for_user(db, _as_uuid(user_id), active_only=True)

    async def list_sessions(
        self,
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
        user_id: uuid.UUID | None = None,
        active_only: bool = False,
        with_user: bool = False,
    ) -> tuple[list[Session], int]:
        """List sessions with filters and pagination.

        Thin passthrough to :meth:`SessionRepository.list`.
        """
        return await self._repo.list(
            db,
            page=page,
            page_size=page_size,
            user_id=user_id,
            active_only=active_only,
            with_user=with_user,
        )

    async def count_active(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID | None = None,
    ) -> int:
        """Return the number of currently active sessions (optionally for a user)."""
        return await self._repo.count_active(db, user_id=user_id)

    async def get_session_by_id_with_user(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
    ) -> Session | None:
        """Fetch a session by ID, eager-loading the owning user + emails."""
        return await self._repo.find_by_id_with_user(db, session_id)

    async def revoke_session_by_id_admin(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
    ) -> Session | None:
        """Revoke a session by ID regardless of owner.

        Returns the updated :class:`Session` on success or ``None`` if the
        session does not exist or is already revoked. Does not commit;
        callers own the transaction boundary.
        """
        session = await self._repo.find_unrevoked_by_id(db, session_id)
        if session is None:
            return None
        await self._repo.revoke(db, session)
        return session

    async def revoke_all_active_sessions(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID | None = None,
    ) -> int:
        """Revoke every currently active session (optionally scoped to a user).

        Returns the number of sessions revoked. Does not commit; callers own
        the transaction boundary.
        """
        sessions = await self._repo.list_active(db, user_id=user_id)
        if not sessions:
            return 0
        await self._repo.revoke_many(db, sessions)
        return len(sessions)

    async def revoke_session_by_id(
        self,
        db: AsyncSession,
        user_id: str,
        session_id: str,
    ) -> bool:
        """Revoke a specific session by ID.

        Args:
            db: Database session.
            user_id: User ID (for authorization check).
            session_id: Session ID to revoke.

        Returns:
            True if session was revoked, False if not found or not owned by user.
        """
        session = await self._repo.find_active_for_user(
            db,
            _as_uuid(session_id),
            _as_uuid(user_id),
        )

        if not session:
            logger.warning(
                "Session revocation failed: session %s not found for user %s",
                session_id,
                user_id,
            )
            return False

        await self._repo.revoke(db, session)
        logger.info("ACTION: session_revoke_by_id, session_id=%s, user_id=%s", session_id, user_id)
        return True

    async def get_session(
        self,
        db: AsyncSession,
        session_token: str,
    ) -> Session | None:
        """Get session by token (alias for get_session_by_token).

        Args:
            db: Database session.
            session_token: Session token.

        Returns:
            Session if valid, None otherwise.
        """
        return await self.get_session_by_token(db, session_token)

    async def refresh_session(
        self,
        db: AsyncSession,
        session: Session,
    ) -> datetime:
        """Refresh session expiration (sliding expiration).

        Only refreshes if session is within the sliding window (last 10% of lifetime).
        This prevents unnecessary database writes on every request.

        Args:
            db: Database session.
            session: Session to refresh.

        Returns:
            New expiration datetime.
        """
        now = datetime.now(UTC)
        new_expires_at = now + timedelta(days=settings.session_expiry_days)

        # Calculate sliding window: refresh if less than 10% of session lifetime remains
        # For a 7-day session, this means refresh when less than ~17 hours remain
        total_lifetime = timedelta(days=settings.session_expiry_days)
        sliding_threshold = total_lifetime * 0.1
        time_remaining = session.expires_at - now

        if time_remaining < sliding_threshold:
            await self._repo.touch_expiry(db, session, new_expires_at)
            logger.debug(
                "Session %s refreshed, new expiration: %s",
                session.id,
                new_expires_at.isoformat(),
            )

        return session.expires_at

    async def refresh_sliding_expiry(
        self,
        db: AsyncSession,
        session_token: str,
    ) -> datetime | None:
        """Refresh a session's expiry if it is inside the sliding window.

        Intended as a middleware entry point that owns its own commit.
        Returns the new ``expires_at`` on refresh, ``None`` when the
        session cannot be found, is revoked/expired, or is still outside
        the sliding window.
        """
        session = await self._repo.find_by_token_hash(
            db,
            hash_token(session_token),
            active_only=True,
        )
        if session is None:
            return None

        now = datetime.now(UTC)
        total_lifetime = timedelta(days=settings.session_expiry_days)
        sliding_threshold = total_lifetime * 0.1
        time_remaining = session.expires_at - now

        if time_remaining >= sliding_threshold:
            return None

        new_expires_at = now + total_lifetime
        session.expires_at = new_expires_at
        await db.commit()
        logger.debug(
            "Session %s refreshed via middleware, new expiration: %s",
            session.id,
            new_expires_at.isoformat(),
        )
        return new_expires_at

    async def cleanup_expired_sessions(
        self,
        db: AsyncSession,
        days: int = 30,
    ) -> int:
        """Delete sessions that expired more than X days ago.

        Args:
            db: Database session.
            days: Delete sessions expired more than this many days ago.

        Returns:
            Number of sessions deleted.
        """
        cutoff = datetime.now(UTC) - timedelta(days=days)

        sessions = await self._repo.list_expired_before(db, cutoff)

        for session in sessions:
            await self._repo.delete(db, session)

        await db.flush()
        return len(sessions)
