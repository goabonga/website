# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Encryption utilities for sensitive data storage."""

import logging

from auth.config import settings
from auth.core.security import AESEncryption

logger = logging.getLogger(__name__)

# Global encryption instance (lazy initialized)
_encryption: AESEncryption | None = None


def _get_encryption() -> AESEncryption:
    """Get or initialize the global encryption instance."""
    global _encryption
    if _encryption is None:
        if not settings.jwks_encryption_key:
            raise ValueError(
                "JWKS_ENCRYPTION_KEY is not configured. Cannot encrypt/decrypt sensitive data."
            )
        _encryption = AESEncryption.from_base64(settings.jwks_encryption_key)
    return _encryption


def encrypt_value(value: str) -> bytes:
    """Encrypt a string value.

    Args:
        value: String to encrypt.

    Returns:
        Encrypted bytes (nonce + ciphertext).
    """
    encryption = _get_encryption()
    return encryption.encrypt(value.encode("utf-8"))


def decrypt_value(encrypted: bytes) -> str:
    """Decrypt an encrypted value back to string.

    Args:
        encrypted: Encrypted bytes (nonce + ciphertext).

    Returns:
        Decrypted string.

    Raises:
        cryptography.exceptions.InvalidTag: If decryption fails.
    """
    encryption = _get_encryption()
    return encryption.decrypt(encrypted).decode("utf-8")
