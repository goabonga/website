# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Security utilities for encryption, hashing, and key management."""

import base64
import os

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Password hasher with secure defaults
_password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    """Hash a password using Argon2id.

    Args:
        password: Plain text password.

    Returns:
        Hashed password string.
    """
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash.

    Args:
        password: Plain text password to verify.
        password_hash: Stored password hash.

    Returns:
        True if password matches, False otherwise.
    """
    try:
        _password_hasher.verify(password_hash, password)
        return True
    except VerifyMismatchError:
        return False


def check_needs_rehash(password_hash: str) -> bool:
    """Check if a password hash needs to be rehashed.

    Args:
        password_hash: Stored password hash.

    Returns:
        True if hash should be updated with new parameters.
    """
    return _password_hasher.check_needs_rehash(password_hash)


class AESEncryption:
    """AES-256-GCM encryption for sensitive data."""

    NONCE_SIZE = 12  # 96 bits recommended for GCM
    KEY_SIZE = 32  # 256 bits

    def __init__(self, key: bytes) -> None:
        """Initialize with encryption key.

        Args:
            key: 32-byte encryption key for AES-256.
        """
        if len(key) != self.KEY_SIZE:
            raise ValueError(f"Key must be {self.KEY_SIZE} bytes")
        self._aesgcm = AESGCM(key)

    @classmethod
    def from_base64(cls, key_b64: str) -> "AESEncryption":
        """Create instance from base64-encoded key.

        Args:
            key_b64: Base64-encoded 32-byte key.

        Returns:
            AESEncryption instance.
        """
        key = base64.b64decode(key_b64)
        return cls(key)

    @classmethod
    def generate_key(cls) -> bytes:
        """Generate a new random encryption key.

        Returns:
            32-byte random key.
        """
        return os.urandom(cls.KEY_SIZE)

    @classmethod
    def generate_key_b64(cls) -> str:
        """Generate a new random encryption key as base64.

        Returns:
            Base64-encoded 32-byte random key.
        """
        return base64.b64encode(cls.generate_key()).decode("ascii")

    def encrypt(self, plaintext: bytes) -> bytes:
        """Encrypt data with AES-256-GCM.

        Args:
            plaintext: Data to encrypt.

        Returns:
            Encrypted data with nonce prepended (nonce + ciphertext).
        """
        nonce = os.urandom(self.NONCE_SIZE)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext, None)
        return nonce + ciphertext

    def decrypt(self, encrypted: bytes) -> bytes:
        """Decrypt data encrypted with AES-256-GCM.

        Args:
            encrypted: Encrypted data with nonce prepended.

        Returns:
            Decrypted plaintext.

        Raises:
            cryptography.exceptions.InvalidTag: If authentication fails.
        """
        nonce = encrypted[: self.NONCE_SIZE]
        ciphertext = encrypted[self.NONCE_SIZE :]
        return self._aesgcm.decrypt(nonce, ciphertext, None)
