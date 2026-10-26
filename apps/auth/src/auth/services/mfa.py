# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Multi-Factor Authentication service."""

import base64
import hashlib
import io
import logging
import secrets
from datetime import UTC, datetime

import pyotp
import qrcode
from sqlalchemy.ext.asyncio import AsyncSession

from auth.config import settings
from auth.core.security import AESEncryption
from auth.db.models.user import MFABackupCode, MFAEmailCode, UserMFA
from auth.db.repositories.mfa import MFARepository

logger = logging.getLogger(__name__)


def generate_backup_code() -> str:
    """Generate a random backup code.

    Returns:
        8-character alphanumeric code (format: XXXX-XXXX).
    """
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # Exclude confusing chars (0, O, 1, I)
    code = "".join(secrets.choice(chars) for _ in range(8))
    return f"{code[:4]}-{code[4:]}"


def hash_code(code: str) -> str:
    """Hash a code using SHA-256.

    Args:
        code: Plain text code.

    Returns:
        SHA-256 hash of the code.
    """
    # Normalize: remove dashes and uppercase
    normalized = code.replace("-", "").upper()
    return hashlib.sha256(normalized.encode()).hexdigest()


class MFAService:
    """Service for MFA operations."""

    def __init__(
        self,
        encryption: AESEncryption,
        repository: MFARepository | None = None,
    ) -> None:
        """Initialize with encryption service.

        Args:
            encryption: AES encryption for TOTP secrets.
            repository: Optional :class:`MFARepository` override (dependency
                injection hook for tests). A default instance is used when
                not provided.
        """
        self._encryption = encryption
        self._repo = repository or MFARepository()

    async def get_user_mfa(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> UserMFA | None:
        """Get MFA configuration for a user.

        Args:
            db: Database session.
            user_id: User ID.

        Returns:
            UserMFA if exists, None otherwise.
        """
        return await self._repo.find_user_mfa(db, user_id)

    async def get_or_create_user_mfa(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> UserMFA:
        """Get or create MFA configuration for a user.

        Args:
            db: Database session.
            user_id: User ID.

        Returns:
            UserMFA record.
        """
        user_mfa = await self.get_user_mfa(db, user_id)

        if not user_mfa:
            user_mfa = UserMFA(user_id=user_id)
            await self._repo.add(db, user_mfa)

        return user_mfa

    def generate_totp_secret(self) -> str:
        """Generate a new TOTP secret.

        Returns:
            Base32-encoded TOTP secret.
        """
        return pyotp.random_base32()

    def encrypt_totp_secret(self, secret: str) -> bytes:
        """Encrypt a TOTP secret for storage.

        Args:
            secret: Base32-encoded TOTP secret.

        Returns:
            Encrypted secret.
        """
        return self._encryption.encrypt(secret.encode())

    def decrypt_totp_secret(self, encrypted: bytes) -> str:
        """Decrypt a stored TOTP secret.

        Args:
            encrypted: Encrypted TOTP secret.

        Returns:
            Base32-encoded TOTP secret.
        """
        return self._encryption.decrypt(encrypted).decode()

    def get_totp_uri(
        self,
        secret: str,
        email: str,
    ) -> str:
        """Get TOTP provisioning URI for QR code.

        Args:
            secret: Base32-encoded TOTP secret.
            email: User email for account label.

        Returns:
            otpauth:// URI.
        """
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(
            name=email,
            issuer_name=settings.mfa_issuer_name,
        )

    def generate_qr_code_base64(self, uri: str) -> str:
        """Generate QR code as base64 data URI.

        Args:
            uri: TOTP provisioning URI.

        Returns:
            Base64 data URI for QR code image.
        """
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(uri)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        b64 = base64.b64encode(buffer.getvalue()).decode()
        return f"data:image/png;base64,{b64}"

    def verify_totp_code(self, secret: str, code: str) -> bool:
        """Verify a TOTP code.

        Args:
            secret: Base32-encoded TOTP secret.
            code: 6-digit code from authenticator.

        Returns:
            True if code is valid.
        """
        totp = pyotp.TOTP(secret)
        # Allow 1 window before/after for clock drift
        return totp.verify(code, valid_window=1)

    async def setup_totp(
        self,
        db: AsyncSession,
        user_id: str,
        email: str,
    ) -> tuple[str, str, str]:
        """Start TOTP setup for a user.

        Args:
            db: Database session.
            user_id: User ID.
            email: User email for QR code label.

        Returns:
            Tuple of (secret, uri, qr_code_base64).
        """
        logger.debug("Starting TOTP setup for user %s", user_id)
        user_mfa = await self.get_or_create_user_mfa(db, user_id)

        # Generate new secret
        secret = self.generate_totp_secret()

        # Store encrypted (not enabled yet)
        user_mfa.totp_secret_encrypted = self.encrypt_totp_secret(secret)
        user_mfa.totp_enabled = False

        await db.flush()

        # Generate QR code
        uri = self.get_totp_uri(secret, email)
        qr_code = self.generate_qr_code_base64(uri)

        logger.info("ACTION: mfa_totp_setup_init, user_id=%s", user_id)
        return secret, uri, qr_code

    async def enable_totp(
        self,
        db: AsyncSession,
        user_id: str,
        code: str,
    ) -> list[str] | None:
        """Enable TOTP after verifying code.

        Args:
            db: Database session.
            user_id: User ID.
            code: TOTP code to verify.

        Returns:
            List of backup codes if successful, None otherwise.
        """
        user_mfa = await self.get_user_mfa(db, user_id)

        if not user_mfa or not user_mfa.totp_secret_encrypted:
            logger.warning("TOTP enable failed: no MFA setup found for user %s", user_id)
            return None

        # Decrypt and verify
        secret = self.decrypt_totp_secret(user_mfa.totp_secret_encrypted)

        if not self.verify_totp_code(secret, code):
            logger.warning("TOTP enable failed: invalid code for user %s", user_id)
            return None

        # Enable TOTP
        user_mfa.totp_enabled = True
        user_mfa.totp_enabled_at = datetime.now(UTC)

        # Generate backup codes
        backup_codes = await self._generate_backup_codes(db, user_mfa)

        await db.flush()

        logger.info(
            "ACTION: mfa_totp_enable, user_id=%s, backup_codes=%d", user_id, len(backup_codes)
        )
        return backup_codes

    async def disable_totp(
        self,
        db: AsyncSession,
        user_id: str,
        code: str,
    ) -> bool:
        """Disable TOTP for a user.

        Args:
            db: Database session.
            user_id: User ID.
            code: TOTP code to verify.

        Returns:
            True if disabled successfully.
        """
        user_mfa = await self.get_user_mfa(db, user_id)

        if not user_mfa or not user_mfa.totp_enabled:
            logger.warning("TOTP disable failed: TOTP not enabled for user %s", user_id)
            return False

        # Verify code before disabling
        if user_mfa.totp_secret_encrypted is None:
            logger.warning("TOTP disable failed: no TOTP secret for user %s", user_id)
            return False
        secret = self.decrypt_totp_secret(user_mfa.totp_secret_encrypted)

        if not self.verify_totp_code(secret, code):
            logger.warning("TOTP disable failed: invalid code for user %s", user_id)
            return False

        # Disable TOTP
        user_mfa.totp_enabled = False
        user_mfa.totp_enabled_at = None
        user_mfa.totp_secret_encrypted = None

        # Delete backup codes
        for backup_code in user_mfa.backup_codes:
            await self._repo.delete(db, backup_code)

        await db.flush()

        logger.info("ACTION: mfa_totp_disable, user_id=%s", user_id)
        return True

    async def verify_mfa_code(
        self,
        db: AsyncSession,
        user_id: str,
        code: str,
    ) -> bool:
        """Verify an MFA code (TOTP or backup code).

        Args:
            db: Database session.
            user_id: User ID.
            code: TOTP code or backup code.

        Returns:
            True if code is valid.
        """
        user_mfa = await self.get_user_mfa(db, user_id)

        if not user_mfa or not user_mfa.totp_enabled:
            logger.warning("MFA verification failed: MFA not enabled for user %s", user_id)
            return False

        # Try TOTP first (6 digits)
        if code.isdigit() and len(code) == 6 and user_mfa.totp_secret_encrypted is not None:
            secret = self.decrypt_totp_secret(user_mfa.totp_secret_encrypted)
            if self.verify_totp_code(secret, code):
                logger.info("ACTION: mfa_verify_totp, user_id=%s", user_id)
                return True

        # Try backup code
        if await self._verify_backup_code(db, user_mfa, code):
            logger.info("ACTION: mfa_verify_backup_code, user_id=%s", user_id)
            return True

        logger.warning("MFA verification failed: invalid code for user %s", user_id)
        return False

    async def _generate_backup_codes(
        self,
        db: AsyncSession,
        user_mfa: UserMFA,
        count: int = 10,
    ) -> list[str]:
        """Generate backup codes for a user.

        Args:
            db: Database session.
            user_mfa: UserMFA record.
            count: Number of codes to generate.

        Returns:
            List of plain text backup codes.
        """
        # Delete existing codes
        for old_code in user_mfa.backup_codes:
            await self._repo.delete(db, old_code)

        # Generate new codes
        codes = []
        for _ in range(count):
            code = generate_backup_code()
            codes.append(code)

            backup = MFABackupCode(
                user_mfa_id=user_mfa.id,
                code_hash=hash_code(code),
            )
            await self._repo.stage(db, backup)

        await db.flush()

        return codes

    async def regenerate_backup_codes(
        self,
        db: AsyncSession,
        user_id: str,
        code: str,
    ) -> list[str] | None:
        """Regenerate backup codes after verifying current MFA.

        Args:
            db: Database session.
            user_id: User ID.
            code: Current TOTP code to verify.

        Returns:
            List of new backup codes if successful, None otherwise.
        """
        user_mfa = await self.get_user_mfa(db, user_id)

        if not user_mfa or not user_mfa.totp_enabled:
            logger.warning("Backup code regeneration failed: MFA not enabled for user %s", user_id)
            return None

        # Verify TOTP code
        if user_mfa.totp_secret_encrypted is None:
            logger.warning("Backup code regeneration failed: no TOTP secret for user %s", user_id)
            return None
        secret = self.decrypt_totp_secret(user_mfa.totp_secret_encrypted)

        if not self.verify_totp_code(secret, code):
            logger.warning(
                "Backup code regeneration failed: invalid TOTP code for user %s", user_id
            )
            return None

        # Regenerate backup codes
        codes = await self._generate_backup_codes(db, user_mfa)

        await db.flush()

        logger.info(
            "ACTION: mfa_backup_codes_regenerate, user_id=%s, count=%d", user_id, len(codes)
        )
        return codes

    async def _verify_backup_code(
        self,
        db: AsyncSession,
        user_mfa: UserMFA,
        code: str,
    ) -> bool:
        """Verify and consume a backup code.

        Args:
            db: Database session.
            user_mfa: UserMFA record.
            code: Backup code.

        Returns:
            True if code is valid and consumed.
        """
        code_hash = hash_code(code)

        for backup in user_mfa.backup_codes:
            if backup.code_hash == code_hash and backup.used_at is None:
                backup.used_at = datetime.now(UTC)
                await db.flush()
                return True

        return False

    async def get_backup_codes_status(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> tuple[int, int] | None:
        """Get backup codes status (used/total).

        Args:
            db: Database session.
            user_id: User ID.

        Returns:
            Tuple of (remaining, total) or None if no MFA.
        """
        user_mfa = await self.get_user_mfa(db, user_id)

        if not user_mfa or not user_mfa.totp_enabled:
            return None

        total = len(user_mfa.backup_codes)
        used = sum(1 for c in user_mfa.backup_codes if c.used_at is not None)

        return (total - used, total)

    # ===== Email MFA Methods =====

    def generate_email_code(self) -> str:
        """Generate a 6-digit email MFA code.

        Returns:
            6-digit numeric code.
        """
        return "".join(secrets.choice("0123456789") for _ in range(6))

    async def send_mfa_email_code(
        self,
        db: AsyncSession,
        user_id: str,
        email: str,
    ) -> str | None:
        """Create and store an MFA email code.

        Args:
            db: Database session.
            user_id: User ID.
            email: Email address to send code to.

        Returns:
            Plain text code if created, None on error.
        """
        from datetime import timedelta

        code = self.generate_email_code()
        code_hash = hash_code(code)

        # Create code record
        mfa_code = MFAEmailCode(
            user_id=user_id,
            email=email.lower(),
            code_hash=code_hash,
            expires_at=datetime.now(UTC)
            + timedelta(minutes=settings.mfa_email_code_expiry_minutes),
        )
        await self._repo.add(db, mfa_code)

        logger.info("ACTION: mfa_email_code_create, user_id=%s", user_id)
        return code

    async def verify_email_code(
        self,
        db: AsyncSession,
        user_id: str,
        code: str,
    ) -> bool:
        """Verify an MFA email code.

        Args:
            db: Database session.
            user_id: User ID.
            code: 6-digit code.

        Returns:
            True if code is valid.
        """
        code_hash = hash_code(code)
        now = datetime.now(UTC)

        mfa_code = await self._repo.find_valid_email_code(db, user_id, code_hash, now=now)

        if not mfa_code:
            logger.warning(
                "Email MFA verification failed: invalid or expired code for user %s", user_id
            )
            return False

        # Mark code as used
        mfa_code.used_at = now
        await db.flush()

        logger.info("ACTION: mfa_email_verify, user_id=%s", user_id)
        return True

    async def verify_mfa_code_with_email(
        self,
        db: AsyncSession,
        user_id: str,
        code: str,
    ) -> bool:
        """Verify an MFA code (TOTP, backup code, or email code).

        Args:
            db: Database session.
            user_id: User ID.
            code: TOTP code, backup code, or email code.

        Returns:
            True if code is valid.
        """
        # Try TOTP first if enabled
        user_mfa = await self.get_user_mfa(db, user_id)

        if user_mfa and user_mfa.totp_enabled:
            # Try TOTP (6 digits)
            if code.isdigit() and len(code) == 6 and user_mfa.totp_secret_encrypted is not None:
                secret = self.decrypt_totp_secret(user_mfa.totp_secret_encrypted)
                if self.verify_totp_code(secret, code):
                    logger.info("ACTION: mfa_verify_totp, user_id=%s", user_id)
                    return True

            # Try backup code
            if await self._verify_backup_code(db, user_mfa, code):
                logger.info("ACTION: mfa_verify_backup_code, user_id=%s", user_id)
                return True

        # Try email code (6 digits)
        if code.isdigit() and len(code) == 6 and await self.verify_email_code(db, user_id, code):
            return True

        logger.warning("MFA verification (with email) failed for user %s", user_id)
        return False
