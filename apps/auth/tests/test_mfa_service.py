# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.mfa — MFAService and helpers."""

import hashlib
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.services.mfa import MFAService, generate_backup_code, hash_code

from tests.conftest import (
    make_backup_code,
    make_execute_result,
    make_user_mfa,
)

# ── Helper functions ─────────────────────────────────────────────────────────


class TestGenerateBackupCode:
    def test_format(self):
        code = generate_backup_code()
        assert len(code) == 9  # 8 chars + 1 hyphen
        assert code[4] == "-"

    def test_excludes_ambiguous_chars(self):
        # The alphabet excludes: 0, O, 1, I (not L)
        for _ in range(100):
            code = generate_backup_code().replace("-", "")
            for c in "0O1I":
                assert c not in code

    def test_randomness(self):
        assert generate_backup_code() != generate_backup_code()

    def test_all_chars_uppercase_alphanumeric(self):
        """Verify all characters are from the expected alphabet."""
        allowed = set("ABCDEFGHJKLMNPQRSTUVWXYZ23456789")
        for _ in range(50):
            code = generate_backup_code().replace("-", "")
            for c in code:
                assert c in allowed


class TestHashCode:
    def test_normalizes_and_hashes(self):
        code = "ABCD-EFGH"
        normalized = "ABCDEFGH"
        expected = hashlib.sha256(normalized.encode()).hexdigest()
        assert hash_code(code) == expected

    def test_case_insensitive(self):
        assert hash_code("abcd-efgh") == hash_code("ABCD-EFGH")

    def test_removes_dashes(self):
        """Verify dashes are stripped before hashing."""
        assert hash_code("AB-CD") == hash_code("ABCD")

    def test_no_dashes_input(self):
        """Code without dashes still hashes correctly."""
        expected = hashlib.sha256(b"ABCDEFGH").hexdigest()
        assert hash_code("ABCDEFGH") == expected

    def test_empty_string(self):
        """Edge case: empty string hashes to SHA-256 of empty string."""
        expected = hashlib.sha256(b"").hexdigest()
        assert hash_code("") == expected


# ── MFAService ───────────────────────────────────────────────────────────────


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def encryption():
    enc = MagicMock()
    enc.encrypt.return_value = b"encrypted_secret"
    enc.decrypt.return_value = b"JBSWY3DPEHPK3PXP"  # valid base32
    return enc


@pytest.fixture
def service(encryption):
    return MFAService(encryption)


class TestGetUserMfa:
    async def test_found(self, db, service):
        mfa = make_user_mfa(totp_enabled=True)
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        result = await service.get_user_mfa(db, str(uuid.uuid4()))
        assert result is mfa

    async def test_not_found(self, db, service):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await service.get_user_mfa(db, str(uuid.uuid4()))
        assert result is None


class TestGetOrCreateUserMfa:
    async def test_returns_existing(self, db, service):
        mfa = make_user_mfa()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        result = await service.get_or_create_user_mfa(db, str(uuid.uuid4()))
        assert result is mfa

    async def test_creates_new(self, db, service):
        service.get_user_mfa = AsyncMock(return_value=None)

        with patch("auth.services.mfa.UserMFA") as MockMFA:
            mock_mfa = MagicMock()
            mock_mfa.id = uuid.uuid4()
            MockMFA.return_value = mock_mfa

            result = await service.get_or_create_user_mfa(db, str(uuid.uuid4()))

        db.add.assert_called_once()
        db.flush.assert_called_once()
        assert result is mock_mfa


class TestTotpOperations:
    def test_generate_totp_secret(self, service):
        with patch("auth.services.mfa.pyotp") as mock_pyotp:
            mock_pyotp.random_base32.return_value = "SECRET123"
            result = service.generate_totp_secret()

        assert result == "SECRET123"

    def test_encrypt_totp_secret(self, service, encryption):
        result = service.encrypt_totp_secret("SECRET")
        encryption.encrypt.assert_called_once_with(b"SECRET")
        assert result == b"encrypted_secret"

    def test_decrypt_totp_secret(self, service, encryption):
        result = service.decrypt_totp_secret(b"encrypted")
        encryption.decrypt.assert_called_once_with(b"encrypted")
        assert result == "JBSWY3DPEHPK3PXP"

    def test_get_totp_uri(self, service):
        with patch("auth.services.mfa.pyotp.TOTP") as MockTOTP:
            mock_totp = MagicMock()
            mock_totp.provisioning_uri.return_value = "otpauth://totp/..."
            MockTOTP.return_value = mock_totp

            result = service.get_totp_uri("SECRET", "user@example.com")

        assert result == "otpauth://totp/..."

    def test_get_totp_uri_calls_provisioning_uri_with_settings(self, service):
        """Verify the provisioning_uri is called with issuer_name from settings."""
        with (
            patch("auth.services.mfa.pyotp.TOTP") as MockTOTP,
            patch("auth.services.mfa.settings") as mock_settings,
        ):
            mock_settings.mfa_issuer_name = "TestIssuer"
            mock_totp = MagicMock()
            MockTOTP.return_value = mock_totp

            service.get_totp_uri("SECRET", "user@test.com")

        mock_totp.provisioning_uri.assert_called_once_with(
            name="user@test.com",
            issuer_name="TestIssuer",
        )

    def test_verify_totp_code_valid(self, service):
        with patch("auth.services.mfa.pyotp.TOTP") as MockTOTP:
            mock_totp = MagicMock()
            mock_totp.verify.return_value = True
            MockTOTP.return_value = mock_totp

            assert service.verify_totp_code("SECRET", "123456") is True
            mock_totp.verify.assert_called_once_with("123456", valid_window=1)

    def test_verify_totp_code_invalid(self, service):
        with patch("auth.services.mfa.pyotp.TOTP") as MockTOTP:
            mock_totp = MagicMock()
            mock_totp.verify.return_value = False
            MockTOTP.return_value = mock_totp

            assert service.verify_totp_code("SECRET", "000000") is False


class TestGenerateQrCode:
    def test_returns_data_uri(self, service):
        with patch("auth.services.mfa.qrcode") as mock_qr:
            mock_qr_instance = MagicMock()
            mock_img = MagicMock()
            mock_qr.QRCode.return_value = mock_qr_instance
            mock_qr_instance.make_image.return_value = mock_img
            mock_qr.constants.ERROR_CORRECT_L = 1

            # Simulate saving to buffer
            def fake_save(buf, format):
                buf.write(b"fake_png_data")

            mock_img.save.side_effect = fake_save

            result = service.generate_qr_code_base64("otpauth://totp/test")

        assert result.startswith("data:image/png;base64,")

    def test_qr_code_contains_base64_data(self, service):
        """Verify that the base64 portion is valid base64."""
        import base64

        with patch("auth.services.mfa.qrcode") as mock_qr:
            mock_qr_instance = MagicMock()
            mock_img = MagicMock()
            mock_qr.QRCode.return_value = mock_qr_instance
            mock_qr_instance.make_image.return_value = mock_img
            mock_qr.constants.ERROR_CORRECT_L = 1

            def fake_save(buf, format):
                buf.write(b"test_image_bytes")

            mock_img.save.side_effect = fake_save

            result = service.generate_qr_code_base64("otpauth://totp/test")

        prefix = "data:image/png;base64,"
        b64_part = result[len(prefix) :]
        decoded = base64.b64decode(b64_part)
        assert decoded == b"test_image_bytes"


class TestSetupTotp:
    async def test_success(self, db, service):
        mfa = make_user_mfa()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        with (
            patch.object(service, "generate_totp_secret", return_value="SECRET"),
            patch.object(service, "encrypt_totp_secret", return_value=b"enc"),
            patch.object(service, "get_totp_uri", return_value="otpauth://..."),
            patch.object(service, "generate_qr_code_base64", return_value="data:..."),
        ):
            secret, uri, qr = await service.setup_totp(db, str(uuid.uuid4()), "user@example.com")

        assert secret == "SECRET"
        assert uri == "otpauth://..."
        assert qr == "data:..."

    async def test_stores_encrypted_secret_and_disables_totp(self, db, service):
        """Verify that setup_totp sets totp_enabled=False and stores encrypted secret."""
        mfa = make_user_mfa()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        with (
            patch.object(service, "generate_totp_secret", return_value="SECRET"),
            patch.object(service, "encrypt_totp_secret", return_value=b"enc_data"),
            patch.object(service, "get_totp_uri", return_value="otpauth://..."),
            patch.object(service, "generate_qr_code_base64", return_value="data:..."),
        ):
            await service.setup_totp(db, str(uuid.uuid4()), "user@example.com")

        assert mfa.totp_secret_encrypted == b"enc_data"
        assert mfa.totp_enabled is False

    async def test_creates_new_mfa_record_if_none(self, db, service):
        """Cover setup_totp calling get_or_create_user_mfa when no MFA exists."""
        new_mfa = make_user_mfa()
        service.get_or_create_user_mfa = AsyncMock(return_value=new_mfa)

        with (
            patch.object(service, "generate_totp_secret", return_value="SECRET"),
            patch.object(service, "encrypt_totp_secret", return_value=b"enc"),
            patch.object(service, "get_totp_uri", return_value="otpauth://..."),
            patch.object(service, "generate_qr_code_base64", return_value="data:..."),
        ):
            secret, uri, qr = await service.setup_totp(db, str(uuid.uuid4()), "user@example.com")

        service.get_or_create_user_mfa.assert_called_once()
        assert secret == "SECRET"


class TestEnableTotp:
    async def test_success(self, db, service):
        mfa = make_user_mfa(totp_secret_encrypted=b"enc")
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        with (
            patch.object(service, "decrypt_totp_secret", return_value="SECRET"),
            patch.object(service, "verify_totp_code", return_value=True),
            patch.object(
                service,
                "_generate_backup_codes",
                new_callable=AsyncMock,
                return_value=["CODE-1234"],
            ),
        ):
            result = await service.enable_totp(db, str(uuid.uuid4()), "123456")

        assert result == ["CODE-1234"]
        assert mfa.totp_enabled is True
        assert mfa.totp_enabled_at is not None

    async def test_invalid_code(self, db, service):
        mfa = make_user_mfa(totp_secret_encrypted=b"enc")
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        with (
            patch.object(service, "decrypt_totp_secret", return_value="SECRET"),
            patch.object(service, "verify_totp_code", return_value=False),
        ):
            result = await service.enable_totp(db, str(uuid.uuid4()), "000000")

        assert result is None

    async def test_no_mfa_setup(self, db, service):
        """Cover: user_mfa is None."""
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await service.enable_totp(db, str(uuid.uuid4()), "123456")
        assert result is None

    async def test_mfa_exists_but_no_secret(self, db, service):
        """Cover line 247: user_mfa exists but totp_secret_encrypted is None."""
        mfa = make_user_mfa(totp_secret_encrypted=None)
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        result = await service.enable_totp(db, str(uuid.uuid4()), "123456")
        assert result is None


class TestDisableTotp:
    async def test_success(self, db, service):
        mfa = make_user_mfa(totp_enabled=True, totp_secret_encrypted=b"enc")
        mfa.backup_codes = [make_backup_code()]
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        with (
            patch.object(service, "decrypt_totp_secret", return_value="SECRET"),
            patch.object(service, "verify_totp_code", return_value=True),
        ):
            result = await service.disable_totp(db, str(uuid.uuid4()), "123456")

        assert result is True
        assert mfa.totp_enabled is False
        assert mfa.totp_secret_encrypted is None
        assert mfa.totp_enabled_at is None

    async def test_success_deletes_multiple_backup_codes(self, db, service):
        """Verify all backup codes are deleted on disable."""
        bc1 = make_backup_code()
        bc2 = make_backup_code()
        mfa = make_user_mfa(totp_enabled=True, totp_secret_encrypted=b"enc")
        mfa.backup_codes = [bc1, bc2]
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        with (
            patch.object(service, "decrypt_totp_secret", return_value="SECRET"),
            patch.object(service, "verify_totp_code", return_value=True),
        ):
            result = await service.disable_totp(db, str(uuid.uuid4()), "123456")

        assert result is True
        assert db.delete.call_count == 2

    async def test_invalid_code(self, db, service):
        mfa = make_user_mfa(totp_enabled=True, totp_secret_encrypted=b"enc")
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        with (
            patch.object(service, "decrypt_totp_secret", return_value="SECRET"),
            patch.object(service, "verify_totp_code", return_value=False),
        ):
            result = await service.disable_totp(db, str(uuid.uuid4()), "000000")

        assert result is False

    async def test_not_enabled(self, db, service):
        mfa = make_user_mfa(totp_enabled=False)
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        result = await service.disable_totp(db, str(uuid.uuid4()), "123456")
        assert result is False

    async def test_no_mfa_record(self, db, service):
        """Cover line 288: disable_totp when user_mfa is None."""
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await service.disable_totp(db, str(uuid.uuid4()), "123456")
        assert result is False


class TestVerifyMfaCode:
    async def test_totp_success(self, db, service):
        mfa = make_user_mfa(totp_enabled=True, totp_secret_encrypted=b"enc")
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        with (
            patch.object(service, "decrypt_totp_secret", return_value="SECRET"),
            patch.object(service, "verify_totp_code", return_value=True),
        ):
            result = await service.verify_mfa_code(db, str(uuid.uuid4()), "123456")

        assert result is True

    async def test_backup_code_success(self, db, service):
        bc = make_backup_code(code_hash=hash_code("ABCD-EFGH"), used_at=None)
        mfa = make_user_mfa(totp_enabled=True, totp_secret_encrypted=b"enc", backup_codes=[bc])
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        with (
            patch.object(service, "decrypt_totp_secret", return_value="SECRET"),
            patch.object(service, "verify_totp_code", return_value=False),
        ):
            result = await service.verify_mfa_code(db, str(uuid.uuid4()), "ABCD-EFGH")

        assert result is True
        assert bc.used_at is not None

    async def test_all_codes_fail(self, db, service):
        mfa = make_user_mfa(totp_enabled=True, totp_secret_encrypted=b"enc")
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        with (
            patch.object(service, "decrypt_totp_secret", return_value="SECRET"),
            patch.object(service, "verify_totp_code", return_value=False),
        ):
            result = await service.verify_mfa_code(db, str(uuid.uuid4()), "WRONG-CODE")

        assert result is False

    async def test_mfa_not_enabled(self, db, service):
        mfa = make_user_mfa(totp_enabled=False)
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        result = await service.verify_mfa_code(db, str(uuid.uuid4()), "123456")
        assert result is False

    async def test_no_mfa_record(self, db, service):
        """Cover line 331: verify_mfa_code when user_mfa is None."""
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await service.verify_mfa_code(db, str(uuid.uuid4()), "123456")
        assert result is False

    async def test_totp_fails_then_backup_code(self, db, service):
        """Cover branch: 6-digit TOTP fails, falls through to backup code."""
        bc = make_backup_code(code_hash=hash_code("123456"), used_at=None)
        mfa = make_user_mfa(totp_enabled=True, totp_secret_encrypted=b"enc", backup_codes=[bc])
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        with (
            patch.object(service, "decrypt_totp_secret", return_value="SECRET"),
            patch.object(service, "verify_totp_code", return_value=False),
        ):
            result = await service.verify_mfa_code(db, str(uuid.uuid4()), "123456")

        assert result is True
        assert bc.used_at is not None

    async def test_backup_code_second_in_list(self, db, service):
        """Cover: first backup code doesn't match, second does."""
        wrong_bc = make_backup_code(code_hash="wrong_hash", used_at=None)
        right_bc = make_backup_code(code_hash=hash_code("ABCD-EFGH"), used_at=None)
        mfa = make_user_mfa(
            totp_enabled=True,
            totp_secret_encrypted=b"enc",
            backup_codes=[wrong_bc, right_bc],
        )
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        with (
            patch.object(service, "decrypt_totp_secret", return_value="SECRET"),
            patch.object(service, "verify_totp_code", return_value=False),
        ):
            result = await service.verify_mfa_code(db, str(uuid.uuid4()), "ABCD-EFGH")

        assert result is True
        assert wrong_bc.used_at is None
        assert right_bc.used_at is not None

    async def test_non_6_digit_code_skips_totp(self, db, service):
        """Non-6-digit code should skip the TOTP branch and go to backup codes."""
        mfa = make_user_mfa(totp_enabled=True, totp_secret_encrypted=b"enc")
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        with patch.object(
            service, "_verify_backup_code", new_callable=AsyncMock, return_value=False
        ):
            result = await service.verify_mfa_code(db, str(uuid.uuid4()), "ABCD-EFGH")

        assert result is False


class TestVerifyBackupCode:
    """Direct tests for _verify_backup_code."""

    async def test_valid_code_consumed(self, db, service):
        bc = make_backup_code(code_hash=hash_code("TEST-CODE"), used_at=None)
        mfa = make_user_mfa(backup_codes=[bc])

        result = await service._verify_backup_code(db, mfa, "TEST-CODE")
        assert result is True
        assert bc.used_at is not None
        db.flush.assert_called_once()

    async def test_already_used_code_rejected(self, db, service):
        """Cover line 442: code_hash matches but used_at is not None."""
        bc = make_backup_code(
            code_hash=hash_code("USED-CODE"),
            used_at=datetime.now(UTC),
        )
        mfa = make_user_mfa(backup_codes=[bc])

        result = await service._verify_backup_code(db, mfa, "USED-CODE")
        assert result is False

    async def test_no_matching_code(self, db, service):
        bc = make_backup_code(code_hash="some_other_hash", used_at=None)
        mfa = make_user_mfa(backup_codes=[bc])

        result = await service._verify_backup_code(db, mfa, "WRONG-CODE")
        assert result is False

    async def test_empty_backup_codes(self, db, service):
        mfa = make_user_mfa(backup_codes=[])

        result = await service._verify_backup_code(db, mfa, "ANY-CODE")
        assert result is False


class TestRegenerateBackupCodes:
    async def test_success(self, db, service):
        mfa = make_user_mfa(totp_enabled=True, totp_secret_encrypted=b"enc")
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        with (
            patch.object(service, "decrypt_totp_secret", return_value="SECRET"),
            patch.object(service, "verify_totp_code", return_value=True),
            patch.object(
                service,
                "_generate_backup_codes",
                new_callable=AsyncMock,
                return_value=["NEW1", "NEW2"],
            ),
        ):
            result = await service.regenerate_backup_codes(db, str(uuid.uuid4()), "123456")

        assert result == ["NEW1", "NEW2"]

    async def test_invalid_code(self, db, service):
        mfa = make_user_mfa(totp_enabled=True, totp_secret_encrypted=b"enc")
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        with (
            patch.object(service, "decrypt_totp_secret", return_value="SECRET"),
            patch.object(service, "verify_totp_code", return_value=False),
        ):
            result = await service.regenerate_backup_codes(db, str(uuid.uuid4()), "000000")

        assert result is None

    async def test_mfa_not_enabled(self, db, service):
        """Cover lines 404-406: regenerate_backup_codes when MFA not enabled."""
        mfa = make_user_mfa(totp_enabled=False)
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        result = await service.regenerate_backup_codes(db, str(uuid.uuid4()), "123456")
        assert result is None

    async def test_no_mfa_record(self, db, service):
        """Cover: regenerate_backup_codes when no MFA record."""
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await service.regenerate_backup_codes(db, str(uuid.uuid4()), "123456")
        assert result is None


class TestGetBackupCodesStatus:
    async def test_returns_counts(self, db, service):
        codes = [
            make_backup_code(used_at=None),
            make_backup_code(used_at=None),
            make_backup_code(used_at=datetime.now(UTC)),
        ]
        mfa = make_user_mfa(totp_enabled=True, backup_codes=codes)
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        result = await service.get_backup_codes_status(db, str(uuid.uuid4()))
        assert result == (2, 3)  # 2 remaining, 3 total

    async def test_no_mfa(self, db, service):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await service.get_backup_codes_status(db, str(uuid.uuid4()))
        assert result is None

    async def test_totp_not_enabled(self, db, service):
        """Cover line 465: mfa exists but totp_enabled=False returns None."""
        mfa = make_user_mfa(totp_enabled=False)
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        result = await service.get_backup_codes_status(db, str(uuid.uuid4()))
        assert result is None

    async def test_all_codes_used(self, db, service):
        """All backup codes are used: remaining=0."""
        now = datetime.now(UTC)
        codes = [
            make_backup_code(used_at=now),
            make_backup_code(used_at=now),
        ]
        mfa = make_user_mfa(totp_enabled=True, backup_codes=codes)
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        result = await service.get_backup_codes_status(db, str(uuid.uuid4()))
        assert result == (0, 2)

    async def test_no_codes_at_all(self, db, service):
        """Edge case: TOTP enabled but no backup codes generated."""
        mfa = make_user_mfa(totp_enabled=True, backup_codes=[])
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        result = await service.get_backup_codes_status(db, str(uuid.uuid4()))
        assert result == (0, 0)


class TestEmailMfa:
    async def test_generate_email_code(self, service):
        code = service.generate_email_code()
        assert len(code) == 6
        assert code.isdigit()

    async def test_generate_email_code_randomness(self, service):
        """Verify email codes vary across calls."""
        codes = {service.generate_email_code() for _ in range(50)}
        assert len(codes) > 1

    async def test_send_mfa_email_code(self, db, service):
        with patch("auth.services.mfa.MFAEmailCode"):
            result = await service.send_mfa_email_code(db, str(uuid.uuid4()), "user@example.com")

        assert result is not None
        assert len(result) == 6
        db.add.assert_called_once()

    async def test_send_mfa_email_code_lowercases_email(self, db, service):
        """Cover line 508: email is lowercased before storage."""
        with patch("auth.services.mfa.MFAEmailCode") as MockEmailCode:
            mock_instance = MagicMock()
            MockEmailCode.return_value = mock_instance

            await service.send_mfa_email_code(db, str(uuid.uuid4()), "User@EXAMPLE.COM")

        # The MFAEmailCode was created with lowercased email
        call_kwargs = MockEmailCode.call_args
        assert call_kwargs.kwargs.get("email") == "user@example.com" or (
            len(call_kwargs.args) > 0 or call_kwargs[1].get("email") == "user@example.com"
        )

    async def test_verify_email_code_success(self, db, service):
        mock_code = MagicMock()
        mock_code.used_at = None
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mock_code))

        result = await service.verify_email_code(db, str(uuid.uuid4()), "123456")
        assert result is True
        assert mock_code.used_at is not None

    async def test_verify_email_code_invalid(self, db, service):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await service.verify_email_code(db, str(uuid.uuid4()), "000000")
        assert result is False

    async def test_verify_email_code_marks_used_at(self, db, service):
        """Verify used_at is set to current UTC time."""
        mock_code = MagicMock()
        mock_code.used_at = None
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mock_code))

        await service.verify_email_code(db, str(uuid.uuid4()), "123456")
        assert isinstance(mock_code.used_at, datetime)


class TestGenerateBackupCodes:
    async def test_generates_codes(self, db, service):
        """Test _generate_backup_codes directly."""
        old_code = make_backup_code()
        mfa = make_user_mfa(totp_enabled=True, backup_codes=[old_code])

        with patch("auth.services.mfa.MFABackupCode"):
            codes = await service._generate_backup_codes(db, mfa, count=5)

        assert len(codes) == 5
        # Old codes should be deleted
        db.delete.assert_called_once_with(old_code)
        # New codes should be added
        assert db.add.call_count == 5

    async def test_generates_default_10_codes(self, db, service):
        mfa = make_user_mfa(totp_enabled=True, backup_codes=[])

        with patch("auth.services.mfa.MFABackupCode"):
            codes = await service._generate_backup_codes(db, mfa)

        assert len(codes) == 10

    async def test_codes_are_formatted(self, db, service):
        mfa = make_user_mfa(totp_enabled=True, backup_codes=[])

        with patch("auth.services.mfa.MFABackupCode"):
            codes = await service._generate_backup_codes(db, mfa, count=3)

        for code in codes:
            assert "-" in code
            assert len(code) == 9  # XXXX-XXXX

    async def test_deletes_multiple_old_codes(self, db, service):
        """Cover: deleting multiple old backup codes."""
        old1 = make_backup_code()
        old2 = make_backup_code()
        mfa = make_user_mfa(totp_enabled=True, backup_codes=[old1, old2])

        with patch("auth.services.mfa.MFABackupCode"):
            await service._generate_backup_codes(db, mfa, count=1)

        assert db.delete.call_count == 2

    async def test_flushes_after_generation(self, db, service):
        mfa = make_user_mfa(totp_enabled=True, backup_codes=[])

        with patch("auth.services.mfa.MFABackupCode"):
            await service._generate_backup_codes(db, mfa, count=1)

        db.flush.assert_called()


class TestVerifyMfaCodeWithEmail:
    async def test_totp_success(self, db, service):
        """Cover: TOTP verification via verify_mfa_code_with_email."""
        mfa = make_user_mfa(totp_enabled=True, totp_secret_encrypted=b"enc")
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        with (
            patch.object(service, "decrypt_totp_secret", return_value="SECRET"),
            patch.object(service, "verify_totp_code", return_value=True),
        ):
            result = await service.verify_mfa_code_with_email(db, str(uuid.uuid4()), "123456")

        assert result is True

    async def test_backup_code_success(self, db, service):
        """Cover: backup code via verify_mfa_code_with_email."""
        bc = make_backup_code(code_hash=hash_code("ABCD-EFGH"), used_at=None)
        mfa = make_user_mfa(totp_enabled=True, totp_secret_encrypted=b"enc", backup_codes=[bc])
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        with (
            patch.object(service, "decrypt_totp_secret", return_value="SECRET"),
            patch.object(service, "verify_totp_code", return_value=False),
        ):
            result = await service.verify_mfa_code_with_email(db, str(uuid.uuid4()), "ABCD-EFGH")

        assert result is True

    async def test_email_code_fallback(self, db, service):
        """Cover lines 593-595: email code fallback when TOTP not enabled."""
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=None),  # get_user_mfa -> None
            ]
        )

        with patch.object(service, "verify_email_code", new_callable=AsyncMock, return_value=True):
            result = await service.verify_mfa_code_with_email(db, str(uuid.uuid4()), "654321")

        assert result is True

    async def test_all_fail(self, db, service):
        """Cover: all codes fail."""
        mfa = make_user_mfa(totp_enabled=True, totp_secret_encrypted=b"enc")
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        with (
            patch.object(service, "decrypt_totp_secret", return_value="SECRET"),
            patch.object(service, "verify_totp_code", return_value=False),
            patch.object(service, "verify_email_code", new_callable=AsyncMock, return_value=False),
        ):
            result = await service.verify_mfa_code_with_email(db, str(uuid.uuid4()), "000000")

        assert result is False

    async def test_non_digit_code_skips_totp_and_email(self, db, service):
        """Cover branch: code is not 6 digits, skip TOTP and email attempts."""
        mfa = make_user_mfa(totp_enabled=True, totp_secret_encrypted=b"enc")
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        with patch.object(
            service, "_verify_backup_code", new_callable=AsyncMock, return_value=False
        ):
            result = await service.verify_mfa_code_with_email(db, str(uuid.uuid4()), "NOTDIGIT")

        assert result is False

    async def test_totp_fails_backup_fails_email_succeeds(self, db, service):
        """Cover: TOTP fails, backup fails, then email code succeeds."""
        mfa = make_user_mfa(totp_enabled=True, totp_secret_encrypted=b"enc", backup_codes=[])
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        with (
            patch.object(service, "decrypt_totp_secret", return_value="SECRET"),
            patch.object(service, "verify_totp_code", return_value=False),
            patch.object(service, "verify_email_code", new_callable=AsyncMock, return_value=True),
        ):
            result = await service.verify_mfa_code_with_email(db, str(uuid.uuid4()), "654321")

        assert result is True

    async def test_totp_not_enabled_non_digit_code_fails(self, db, service):
        """Cover: no TOTP, non-digit code, email path skipped -> returns False."""
        db.execute = AsyncMock(
            return_value=make_execute_result(scalar_value=None),  # get_user_mfa -> None
        )

        result = await service.verify_mfa_code_with_email(db, str(uuid.uuid4()), "NOTDIGIT")
        assert result is False

    async def test_totp_enabled_but_5_digit_code(self, db, service):
        """Cover: 5-digit code skips TOTP check (not 6 digits)."""
        mfa = make_user_mfa(totp_enabled=True, totp_secret_encrypted=b"enc", backup_codes=[])
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mfa))

        result = await service.verify_mfa_code_with_email(db, str(uuid.uuid4()), "12345")
        assert result is False


class TestTotpSecretMissing:
    """MFA rows flagged as TOTP-enabled but with no stored secret fail closed."""

    @pytest.mark.asyncio
    async def test_disable_totp_without_secret(self):
        service = MFAService(encryption=MagicMock())
        user_mfa = MagicMock()
        user_mfa.totp_enabled = True
        user_mfa.totp_secret_encrypted = None
        service.get_user_mfa = AsyncMock(return_value=user_mfa)

        assert await service.disable_totp(AsyncMock(), uuid.uuid4(), "123456") is False

    @pytest.mark.asyncio
    async def test_regenerate_backup_codes_without_secret(self):
        service = MFAService(encryption=MagicMock())
        user_mfa = MagicMock()
        user_mfa.totp_enabled = True
        user_mfa.totp_secret_encrypted = None
        service.get_user_mfa = AsyncMock(return_value=user_mfa)

        assert await service.regenerate_backup_codes(AsyncMock(), uuid.uuid4(), "123456") is None
