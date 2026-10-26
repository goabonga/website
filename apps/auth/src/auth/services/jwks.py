# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""JWKS (JSON Web Key Set) management service."""

from __future__ import annotations

import base64
import logging
import uuid
from builtins import list as BuiltinList
from datetime import UTC, datetime

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy.ext.asyncio import AsyncSession

from auth.core.security import AESEncryption
from auth.db.models.jwk import JWK
from auth.db.repositories.jwk import JWKRepository

logger = logging.getLogger(__name__)


class JWKSService:
    """Service for managing JSON Web Keys in database.

    Orchestrates crypto operations (RSA generation, rotation, activation)
    and delegates SQL access to :class:`JWKRepository`. This service owns
    transaction boundaries (commit after each state change) and the
    encryption/decryption of private keys.
    """

    def __init__(
        self,
        encryption: AESEncryption,
        repository: JWKRepository | None = None,
    ) -> None:
        """Initialize service.

        Args:
            encryption: AES encryption instance for private keys.
            repository: JWK data access layer (defaults to a new
                :class:`JWKRepository`).
        """
        self._encryption = encryption
        self._repo = repository or JWKRepository()

    # ------------------------------------------------------------------
    # Read passthroughs
    # ------------------------------------------------------------------

    async def get_by_id(self, db: AsyncSession, key_uuid: uuid.UUID) -> JWK | None:
        """Get a key by its primary-key UUID."""
        return await self._repo.find_by_id(db, key_uuid)

    async def get_by_kid(self, db: AsyncSession, kid: str) -> JWK | None:
        """Get a key by its ``kid`` identifier."""
        return await self._repo.find_by_kid(db, kid)

    async def get_key_by_kid(self, db: AsyncSession, kid: str) -> JWK | None:
        """Get a key by its ``kid`` identifier (legacy alias for :meth:`get_by_kid`)."""
        return await self._repo.find_by_kid(db, kid)

    async def get_active_key(self, db: AsyncSession) -> JWK | None:
        """Get the currently active signing key, if any."""
        return await self._repo.find_active(db)

    async def list(
        self,
        db: AsyncSession,
        *,
        include_revoked: bool = False,
        active_only: bool = False,
    ) -> BuiltinList[JWK]:
        """List keys. See :meth:`JWKRepository.list`."""
        return await self._repo.list(
            db,
            include_revoked=include_revoked,
            active_only=active_only,
        )

    async def get_all_public_keys(self, db: AsyncSession) -> BuiltinList[JWK]:
        """Get all non-revoked keys for the public JWKS endpoint."""
        return await self._repo.list(db, include_revoked=False)

    # ------------------------------------------------------------------
    # Business flows
    # ------------------------------------------------------------------

    async def generate_key(
        self,
        db: AsyncSession,
        key_size: int = 2048,
        activate: bool = False,
    ) -> JWK:
        """Generate a new RSA key pair and store in database.

        Args:
            db: Database session.
            key_size: RSA key size in bits (default 2048).
            activate: Whether to activate this key immediately.

        Returns:
            Created JWK model.
        """
        # Generate RSA key pair
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_size,
        )
        public_key = private_key.public_key()

        # Serialize keys
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

        # Encrypt private key
        encrypted_private = self._encryption.encrypt(private_pem)

        # Generate key ID
        kid = str(uuid.uuid4())

        # Deactivate other keys if activating this one
        if activate:
            await self._repo.deactivate_active(db)

        # Create JWK record
        jwk = JWK(
            kid=kid,
            kty="RSA",
            alg="RS256",
            use="sig",
            private_key_encrypted=encrypted_private,
            public_key_pem=public_pem,
            is_active=activate,
        )
        await self._repo.add(db, jwk)
        await db.commit()
        await db.refresh(jwk)

        logger.info("Generated new JWK: kid=%s active=%s key_size=%d", kid, activate, key_size)
        return jwk

    async def activate_key(self, db: AsyncSession, kid: str) -> JWK | None:
        """Activate a key (deactivates all others).

        Args:
            db: Database session.
            kid: Key ID to activate.

        Returns:
            Activated JWK or None if not found.
        """
        jwk = await self._repo.find_by_kid(db, kid)
        if not jwk:
            logger.warning("Key activation failed: kid not found: %s", kid)
            return None

        if jwk.revoked_at:
            logger.warning("Key activation failed: key is revoked: %s", kid)
            raise ValueError("Cannot activate a revoked key")

        # Deactivate all keys
        await self._repo.deactivate_all(db)

        # Activate this key
        jwk.is_active = True
        await db.commit()
        await db.refresh(jwk)

        logger.info("Key activated: kid=%s", kid)
        return jwk

    async def revoke_key(self, db: AsyncSession, kid: str) -> JWK | None:
        """Revoke a key (cannot be used for signing, stays in JWKS for verification).

        Args:
            db: Database session.
            kid: Key ID to revoke.

        Returns:
            Revoked JWK or None if not found.
        """
        jwk = await self._repo.find_by_kid(db, kid)
        if not jwk:
            logger.warning("Key revocation failed: kid not found: %s", kid)
            return None

        jwk.is_active = False
        jwk.revoked_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(jwk)

        logger.info("Key revoked: kid=%s", kid)
        return jwk

    async def rotate_keys(self, db: AsyncSession, key_size: int = 2048) -> JWK:
        """Rotate keys: generate new key and activate it.

        Args:
            db: Database session.
            key_size: RSA key size in bits.

        Returns:
            New active JWK.
        """
        logger.info("Rotating keys with key_size=%d", key_size)
        return await self.generate_key(db, key_size=key_size, activate=True)

    async def delete(self, db: AsyncSession, kid: str) -> bool:
        """Delete a revoked key.

        Args:
            db: Database session.
            kid: Key ID to delete.

        Returns:
            True if deleted, False if not found or not revoked.
        """
        jwk = await self._repo.find_by_kid(db, kid)
        if not jwk or not jwk.revoked_at:
            logger.warning("Key deletion failed: kid not found or not revoked: %s", kid)
            return False

        await self._repo.delete(db, jwk)
        await db.commit()
        logger.info("Key deleted: kid=%s", kid)
        return True

    async def delete_key(self, db: AsyncSession, kid: str) -> bool:
        """Delete a revoked key (legacy alias for :meth:`delete`)."""
        return await self.delete(db, kid)

    def decrypt_private_key(self, jwk: JWK) -> rsa.RSAPrivateKey:
        """Decrypt and load private key from JWK.

        Args:
            jwk: JWK model with encrypted private key.

        Returns:
            RSA private key object.
        """
        private_pem = self._encryption.decrypt(jwk.private_key_encrypted)
        private_key = serialization.load_pem_private_key(private_pem, password=None)
        assert isinstance(private_key, rsa.RSAPrivateKey)
        return private_key

    def to_jwk_public(self, jwk: JWK) -> dict:
        """Convert JWK model to public JWK format.

        Args:
            jwk: JWK model.

        Returns:
            Dictionary in JWK public key format.
        """
        public_key = serialization.load_pem_public_key(jwk.public_key_pem.encode("utf-8"))
        assert isinstance(public_key, rsa.RSAPublicKey)
        numbers = public_key.public_numbers()

        # Convert to base64url
        def to_base64url(n: int, length: int) -> str:
            data = n.to_bytes(length, byteorder="big")
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

        # RSA modulus size in bytes (256 for 2048-bit key)
        n_bytes = (numbers.n.bit_length() + 7) // 8

        return {
            "kty": jwk.kty,
            "use": jwk.use,
            "alg": jwk.alg,
            "kid": jwk.kid,
            "n": to_base64url(numbers.n, n_bytes),
            "e": to_base64url(numbers.e, 3),
        }
