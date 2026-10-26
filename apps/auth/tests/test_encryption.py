# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.core.encryption — encrypt/decrypt utilities."""

from unittest.mock import MagicMock, patch

import pytest

# ── _get_encryption ─────────────────────────────────────────────────────────


class TestGetEncryption:
    def test_no_key_raises(self):
        import auth.core.encryption as mod

        mod._encryption = None
        with patch.object(mod, "settings") as mock_settings:
            mock_settings.jwks_encryption_key = ""
            with pytest.raises(ValueError, match="JWKS_ENCRYPTION_KEY is not configured"):
                mod._get_encryption()
        mod._encryption = None  # Cleanup

    def test_creates_instance(self):
        import auth.core.encryption as mod

        mod._encryption = None
        with (
            patch.object(mod, "settings") as mock_settings,
            patch.object(mod, "AESEncryption") as MockAES,
        ):
            mock_settings.jwks_encryption_key = "dGVzdGtleQ=="
            mock_instance = MagicMock()
            MockAES.from_base64.return_value = mock_instance
            result = mod._get_encryption()
        assert result is mock_instance
        MockAES.from_base64.assert_called_once_with("dGVzdGtleQ==")
        mod._encryption = None  # Cleanup

    def test_cached_instance(self):
        import auth.core.encryption as mod

        mock_instance = MagicMock()
        mod._encryption = mock_instance
        result = mod._get_encryption()
        assert result is mock_instance
        mod._encryption = None  # Cleanup


# ── encrypt_value ───────────────────────────────────────────────────────────


class TestEncryptValue:
    def test_success(self):
        import auth.core.encryption as mod

        mock_enc = MagicMock()
        mock_enc.encrypt.return_value = b"encrypted_bytes"
        mod._encryption = mock_enc
        result = mod.encrypt_value("hello")
        assert result == b"encrypted_bytes"
        mock_enc.encrypt.assert_called_once_with(b"hello")
        mod._encryption = None


# ── decrypt_value ───────────────────────────────────────────────────────────


class TestDecryptValue:
    def test_success(self):
        import auth.core.encryption as mod

        mock_enc = MagicMock()
        mock_enc.decrypt.return_value = b"hello"
        mod._encryption = mock_enc
        result = mod.decrypt_value(b"encrypted_bytes")
        assert result == "hello"
        mock_enc.decrypt.assert_called_once_with(b"encrypted_bytes")
        mod._encryption = None
