# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.core.security — password hashing and AES encryption."""

import base64
import os

import pytest
from auth.core.security import (
    AESEncryption,
    check_needs_rehash,
    hash_password,
    verify_password,
)
from cryptography.exceptions import InvalidTag

# ── Password hashing ────────────────────────────────────────────────────────


class TestHashPassword:
    def test_returns_argon2_hash(self):
        h = hash_password("my_secret")
        assert h.startswith("$argon2")

    def test_different_passwords_produce_different_hashes(self):
        h1 = hash_password("password1")
        h2 = hash_password("password2")
        assert h1 != h2

    def test_same_password_produces_different_hashes_due_to_salt(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2


class TestVerifyPassword:
    def test_correct_password(self):
        h = hash_password("correct_horse")
        assert verify_password("correct_horse", h) is True

    def test_wrong_password(self):
        h = hash_password("correct_horse")
        assert verify_password("wrong_horse", h) is False

    def test_empty_password(self):
        h = hash_password("")
        assert verify_password("", h) is True
        assert verify_password("notempty", h) is False


class TestCheckNeedsRehash:
    def test_current_hash_does_not_need_rehash(self):
        h = hash_password("test")
        assert check_needs_rehash(h) is False


# ── AES-256-GCM Encryption ──────────────────────────────────────────────────


class TestAESEncryption:
    def _make_key(self):
        return os.urandom(32)

    def test_encrypt_decrypt_roundtrip(self):
        key = self._make_key()
        enc = AESEncryption(key)
        plaintext = b"Hello, World!"
        encrypted = enc.encrypt(plaintext)
        assert enc.decrypt(encrypted) == plaintext

    def test_encrypted_differs_from_plaintext(self):
        key = self._make_key()
        enc = AESEncryption(key)
        plaintext = b"secret data"
        encrypted = enc.encrypt(plaintext)
        assert encrypted != plaintext

    def test_same_plaintext_produces_different_ciphertext(self):
        key = self._make_key()
        enc = AESEncryption(key)
        plaintext = b"nonce makes it different"
        e1 = enc.encrypt(plaintext)
        e2 = enc.encrypt(plaintext)
        assert e1 != e2

    def test_wrong_key_fails_decryption(self):
        key1 = self._make_key()
        key2 = self._make_key()
        enc1 = AESEncryption(key1)
        enc2 = AESEncryption(key2)
        encrypted = enc1.encrypt(b"data")
        with pytest.raises(InvalidTag):
            enc2.decrypt(encrypted)

    def test_invalid_key_length_raises(self):
        with pytest.raises(ValueError, match="32 bytes"):
            AESEncryption(b"too_short")

    def test_from_base64(self):
        key = os.urandom(32)
        key_b64 = base64.b64encode(key).decode()
        enc = AESEncryption.from_base64(key_b64)
        plaintext = b"base64 key test"
        assert enc.decrypt(enc.encrypt(plaintext)) == plaintext

    def test_generate_key_length(self):
        key = AESEncryption.generate_key()
        assert len(key) == 32

    def test_generate_key_b64_decodes(self):
        key_b64 = AESEncryption.generate_key_b64()
        key = base64.b64decode(key_b64)
        assert len(key) == 32

    def test_empty_plaintext(self):
        key = self._make_key()
        enc = AESEncryption(key)
        encrypted = enc.encrypt(b"")
        assert enc.decrypt(encrypted) == b""

    def test_large_plaintext(self):
        key = self._make_key()
        enc = AESEncryption(key)
        plaintext = os.urandom(10_000)
        assert enc.decrypt(enc.encrypt(plaintext)) == plaintext
