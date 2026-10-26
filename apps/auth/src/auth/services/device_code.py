# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Device Authorization service (RFC 8628)."""

import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from auth.config import settings
from auth.db.models.oauth2 import DeviceCode, DeviceCodeStatus, OAuth2Client
from auth.db.repositories.device_code import DeviceCodeRepository

logger = logging.getLogger(__name__)


def generate_device_code() -> str:
    """Generate a cryptographically random device code.

    Returns:
        64-character hex string.
    """
    return secrets.token_hex(32)


def generate_user_code(length: int = 8) -> str:
    """Generate a user-friendly code for device authorization.

    Uses uppercase letters and digits, excluding ambiguous characters
    like O, 0, I, 1, L for better readability.

    Args:
        length: Length of the user code (default 8).

    Returns:
        User-friendly code like "ABCD-EFGH".
    """
    # Exclude ambiguous characters: O, 0, I, 1, L
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    code = "".join(secrets.choice(alphabet) for _ in range(length))

    # Add hyphen in the middle for readability
    if length >= 4:
        mid = length // 2
        code = f"{code[:mid]}-{code[mid:]}"

    return code


def hash_device_code(code: str) -> str:
    """Hash a device code using SHA-256.

    Args:
        code: Plain text device code.

    Returns:
        SHA-256 hash of the code.
    """
    return hashlib.sha256(code.encode()).hexdigest()


class DeviceCodeService:
    """Service for device authorization flow (RFC 8628)."""

    def __init__(self, repository: DeviceCodeRepository | None = None) -> None:
        self._repo = repository or DeviceCodeRepository()

    async def create_device_authorization(
        self,
        db: AsyncSession,
        client: OAuth2Client,
        scopes: list[str],
        verification_uri: str,
    ) -> tuple[str, DeviceCode]:
        """Create a new device authorization request.

        Args:
            db: Database session.
            client: OAuth2 client.
            scopes: Requested scopes.
            verification_uri: URI where user should go to authorize.

        Returns:
            Tuple of (plain_device_code, DeviceCode model).
        """
        # Generate codes
        device_code = generate_device_code()
        device_code_hash = hash_device_code(device_code)
        user_code = generate_user_code()

        # Ensure user_code is unique (regenerate if collision)
        max_attempts = 10
        for _ in range(max_attempts):
            existing = await self.get_by_user_code(db, user_code)
            if not existing:
                break
            user_code = generate_user_code()
        else:
            raise ValueError("Failed to generate unique user code")

        # Calculate expiration
        expires_at = datetime.now(UTC) + timedelta(minutes=settings.device_code_expiry_minutes)

        # Create device code record
        device = DeviceCode(
            device_code_hash=device_code_hash,
            user_code=user_code,
            client_id=client.id,
            scopes=scopes,
            verification_uri=verification_uri,
            interval=settings.device_code_interval,
            expires_at=expires_at,
            status=DeviceCodeStatus.PENDING.value,
        )

        await self._repo.add(db, device)

        logger.info(
            "Device authorization created for client %s user_code=%s", client.client_id, user_code
        )
        return device_code, device

    async def get_by_device_code(
        self,
        db: AsyncSession,
        device_code: str,
    ) -> DeviceCode | None:
        """Get a device authorization by device code.

        Args:
            db: Database session.
            device_code: Plain text device code.

        Returns:
            DeviceCode if found, None otherwise.
        """
        device_code_hash = hash_device_code(device_code)
        return await self._repo.find_by_device_code_hash(db, device_code_hash)

    async def get_by_user_code(
        self,
        db: AsyncSession,
        user_code: str,
    ) -> DeviceCode | None:
        """Get a device authorization by user code.

        Args:
            db: Database session.
            user_code: User-facing code (case-insensitive).

        Returns:
            DeviceCode if found, None otherwise.
        """
        # Normalize user code: uppercase and remove hyphens
        normalized = user_code.upper().replace("-", "").replace(" ", "")

        # Search with original format (with hyphen)
        if len(normalized) >= 4:
            mid = len(normalized) // 2
            formatted = f"{normalized[:mid]}-{normalized[mid:]}"
        else:
            formatted = normalized

        return await self._repo.find_by_user_code(db, formatted)

    async def authorize(
        self,
        db: AsyncSession,
        device: DeviceCode,
        user_id: uuid.UUID,
    ) -> None:
        """Authorize a device code request.

        Args:
            db: Database session.
            device: DeviceCode to authorize.
            user_id: ID of the authorizing user.
        """
        device.status = DeviceCodeStatus.AUTHORIZED.value
        device.user_id = user_id
        await db.flush()
        logger.info("Device code authorized: user_code=%s user=%s", device.user_code, user_id)

    async def deny(
        self,
        db: AsyncSession,
        device: DeviceCode,
    ) -> None:
        """Deny a device code request.

        Args:
            db: Database session.
            device: DeviceCode to deny.
        """
        device.status = DeviceCodeStatus.DENIED.value
        await db.flush()
        logger.info("Device code denied: user_code=%s", device.user_code)

    async def update_poll_time(
        self,
        db: AsyncSession,
        device: DeviceCode,
    ) -> None:
        """Update the last poll time for rate limiting.

        Args:
            db: Database session.
            device: DeviceCode that was polled.
        """
        device.last_poll_at = datetime.now(UTC)
        await db.flush()

    def is_expired(self, device: DeviceCode) -> bool:
        """Check if a device code has expired.

        Args:
            device: DeviceCode to check.

        Returns:
            True if expired.
        """
        return datetime.now(UTC) > device.expires_at

    def is_slow_down_required(self, device: DeviceCode) -> bool:
        """Check if the client is polling too fast.

        Args:
            device: DeviceCode being polled.

        Returns:
            True if client should slow down.
        """
        if not device.last_poll_at:
            return False

        elapsed = (datetime.now(UTC) - device.last_poll_at).total_seconds()
        return elapsed < device.interval

    async def delete(self, db: AsyncSession, device: DeviceCode) -> None:
        """Stage a device code deletion and flush.

        Used by the token endpoint to consume the code after token
        issuance in RFC 8628 flows. The caller owns the commit.
        """
        await self._repo.delete(db, device)
        await db.flush()

    async def cleanup_expired(self, db: AsyncSession) -> int:
        """Delete expired device codes.

        Args:
            db: Database session.

        Returns:
            Number of deleted records.
        """
        now = datetime.now(UTC)
        expired = await self._repo.list_expired(db, now)

        count = len(expired)
        for device in expired:
            await self._repo.delete(db, device)

        await db.flush()
        return count
