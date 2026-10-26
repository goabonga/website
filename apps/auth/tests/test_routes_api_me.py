# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.api.routes.me_legacy — User-facing API with Bearer auth."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

MODULE = "auth.api.routes.me_legacy"


_SENTINEL = object()


def _make_token_record(revoked=False, expired=False, user_id=_SENTINEL):
    rec = MagicMock()
    rec.revoked_at = datetime.now(UTC) if revoked else None
    if expired:
        rec.expires_at = datetime.now(UTC) - timedelta(hours=1)
    else:
        rec.expires_at = datetime.now(UTC) + timedelta(hours=1)
    rec.user_id = uuid.uuid4() if user_id is _SENTINEL else user_id
    return rec


def _make_user(with_profile=True, with_email=True, active=True):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = active

    if with_profile:
        profile = MagicMock()
        profile.nickname = "johnny"
        profile.name = "John Doe"
        profile.given_name = "John"
        profile.family_name = "Doe"
        profile.middle_name = None
        profile.preferred_username = "johnd"
        profile.picture_url = "https://pic.com/j.jpg"
        profile.website = "https://jd.com"
        profile.gender = "male"
        profile.birthdate = "1990-01-01"
        profile.zoneinfo = "UTC"
        profile.locale = "en"
        profile.phone_number = "+123"
        user.profile = profile
    else:
        user.profile = None

    if with_email:
        email_obj = MagicMock()
        email_obj.email = "john@example.com"
        email_obj.is_primary = True
        user.emails = [email_obj]
    else:
        user.emails = []

    return user


# ---------------------------------------------------------------------------
# _extract_bearer_token
# ---------------------------------------------------------------------------


class TestExtractBearerToken:
    def test_valid(self):
        from auth.api.routes.me_legacy import _extract_bearer_token

        assert _extract_bearer_token("Bearer tok") == "tok"

    def test_none(self):
        from auth.api.routes.me_legacy import _extract_bearer_token

        assert _extract_bearer_token(None) is None

    def test_wrong_prefix(self):
        from auth.api.routes.me_legacy import _extract_bearer_token

        assert _extract_bearer_token("Basic abc") is None


# ---------------------------------------------------------------------------
# get_current_user_from_token
# ---------------------------------------------------------------------------


class TestGetCurrentUserFromToken:
    @pytest.mark.asyncio
    async def test_invalid_jwt(self):
        from auth.api.routes.me_legacy import get_current_user_from_token

        with pytest.raises(HTTPException) as exc:
            await get_current_user_from_token(AsyncMock(), AsyncMock(), "not-a-jwt")
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.jwt")
    async def test_missing_jti(self, mock_jwt):
        from auth.api.routes.me_legacy import get_current_user_from_token

        mock_jwt.decode.return_value = {"sub": "u"}
        mock_jwt.DecodeError = Exception

        with pytest.raises(HTTPException) as exc:
            await get_current_user_from_token(AsyncMock(), AsyncMock(), "tok")
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.jwt")
    async def test_token_not_found(self, mock_jwt):
        from auth.api.routes.me_legacy import get_current_user_from_token

        mock_jwt.decode.return_value = {"jti": "j1"}
        mock_jwt.DecodeError = Exception

        ts = AsyncMock()
        ts.get_access_token_by_jti = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc:
            await get_current_user_from_token(AsyncMock(), ts, "tok")
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.jwt")
    async def test_token_revoked(self, mock_jwt):
        from auth.api.routes.me_legacy import get_current_user_from_token

        mock_jwt.decode.return_value = {"jti": "j1"}
        mock_jwt.DecodeError = Exception

        ts = AsyncMock()
        ts.get_access_token_by_jti = AsyncMock(return_value=_make_token_record(revoked=True))

        with pytest.raises(HTTPException) as exc:
            await get_current_user_from_token(AsyncMock(), ts, "tok")
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.jwt")
    async def test_token_expired(self, mock_jwt):
        from auth.api.routes.me_legacy import get_current_user_from_token

        mock_jwt.decode.return_value = {"jti": "j1"}
        mock_jwt.DecodeError = Exception

        ts = AsyncMock()
        ts.get_access_token_by_jti = AsyncMock(return_value=_make_token_record(expired=True))

        with pytest.raises(HTTPException) as exc:
            await get_current_user_from_token(AsyncMock(), ts, "tok")
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.jwt")
    async def test_no_user_id(self, mock_jwt):
        from auth.api.routes.me_legacy import get_current_user_from_token

        mock_jwt.decode.return_value = {"jti": "j1"}
        mock_jwt.DecodeError = Exception

        ts = AsyncMock()
        ts.get_access_token_by_jti = AsyncMock(return_value=_make_token_record(user_id=None))

        with pytest.raises(HTTPException) as exc:
            await get_current_user_from_token(AsyncMock(), ts, "tok")
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.jwt")
    async def test_user_inactive(self, mock_jwt):
        from auth.api.routes.me_legacy import get_current_user_from_token

        uid = uuid.uuid4()
        mock_jwt.decode.return_value = {"jti": "j1"}
        mock_jwt.DecodeError = Exception

        ts = AsyncMock()
        ts.get_access_token_by_jti = AsyncMock(return_value=_make_token_record(user_id=uid))

        user = _make_user(active=False)
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = user
        db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(HTTPException) as exc:
            await get_current_user_from_token(db, ts, "tok")
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.jwt")
    async def test_success(self, mock_jwt):
        from auth.api.routes.me_legacy import get_current_user_from_token

        uid = uuid.uuid4()
        mock_jwt.decode.return_value = {"jti": "j1"}
        mock_jwt.DecodeError = Exception

        ts = AsyncMock()
        ts.get_access_token_by_jti = AsyncMock(return_value=_make_token_record(user_id=uid))

        user = _make_user()
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = user
        db.execute = AsyncMock(return_value=result_mock)

        user_result, jwt_sub = await get_current_user_from_token(db, ts, "tok")
        assert user_result.is_active is True
        assert isinstance(jwt_sub, str)


# ---------------------------------------------------------------------------
# PasswordChangeRequest validation
# ---------------------------------------------------------------------------


class TestPasswordChangeRequest:
    def test_valid(self):
        from auth.api.routes.me_legacy import PasswordChangeRequest

        r = PasswordChangeRequest(current_password="old", new_password="NewStr0ng!")
        assert r.new_password == "NewStr0ng!"

    def test_short(self):
        from auth.api.routes.me_legacy import PasswordChangeRequest

        with pytest.raises(ValidationError, match="at least 8"):
            PasswordChangeRequest(current_password="old", new_password="Sh1!")

    def test_no_upper(self):
        from auth.api.routes.me_legacy import PasswordChangeRequest

        with pytest.raises(ValidationError, match="uppercase"):
            PasswordChangeRequest(current_password="old", new_password="nouppercase1")

    def test_no_lower(self):
        from auth.api.routes.me_legacy import PasswordChangeRequest

        with pytest.raises(ValidationError, match="lowercase"):
            PasswordChangeRequest(current_password="old", new_password="NOLOWER123!")

    def test_no_digit(self):
        from auth.api.routes.me_legacy import PasswordChangeRequest

        with pytest.raises(ValidationError, match="digit"):
            PasswordChangeRequest(current_password="old", new_password="NoDigitHere!")


# ---------------------------------------------------------------------------
# get_profile
# ---------------------------------------------------------------------------


class TestGetProfile:
    @pytest.mark.asyncio
    async def test_no_token(self):
        from auth.api.routes.me_legacy import get_profile

        with pytest.raises(HTTPException) as exc:
            await get_profile(AsyncMock(), AsyncMock(), AsyncMock(), authorization=None)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user_from_token", new_callable=AsyncMock)
    async def test_success(self, mock_get_user):
        from auth.api.routes.me_legacy import get_profile

        user = _make_user()
        mock_get_user.return_value = (user, str(user.id))

        result = await get_profile(
            AsyncMock(), AsyncMock(), AsyncMock(), authorization="Bearer tok"
        )
        assert result.sub == str(user.id)
        assert result.nickname == "johnny"

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user_from_token", new_callable=AsyncMock)
    async def test_no_profile(self, mock_get_user):
        from auth.api.routes.me_legacy import get_profile

        user = _make_user(with_profile=False)
        mock_get_user.return_value = (user, str(user.id))

        result = await get_profile(
            AsyncMock(), AsyncMock(), AsyncMock(), authorization="Bearer tok"
        )
        assert result.sub == str(user.id)
        assert result.nickname is None


# ---------------------------------------------------------------------------
# update_profile
# ---------------------------------------------------------------------------


class TestUpdateProfile:
    @pytest.mark.asyncio
    async def test_no_token(self):
        from auth.api.routes.me_legacy import ProfileUpdateRequest, update_profile

        data = ProfileUpdateRequest(nickname="new")
        with pytest.raises(HTTPException) as exc:
            await update_profile(data, AsyncMock(), AsyncMock(), AsyncMock(), authorization=None)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user_from_token", new_callable=AsyncMock)
    async def test_success(self, mock_get_user):
        from auth.api.routes.me_legacy import ProfileUpdateRequest, update_profile

        user = _make_user()
        mock_get_user.return_value = (user, str(user.id))

        profile = MagicMock()
        profile.nickname = "updated"
        profile.name = None
        profile.given_name = None
        profile.family_name = None
        profile.middle_name = None
        profile.preferred_username = None
        profile.picture_url = None
        profile.website = None
        profile.gender = None
        profile.birthdate = None
        profile.zoneinfo = None
        profile.locale = None
        profile.phone_number = None

        profile_service = AsyncMock()
        profile_service.update_profile = AsyncMock(return_value=profile)

        db = AsyncMock()
        data = ProfileUpdateRequest(nickname="updated")

        result = await update_profile(
            data, db, AsyncMock(), profile_service, authorization="Bearer tok"
        )
        assert result.nickname == "updated"
        db.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# change_password
# ---------------------------------------------------------------------------


class TestChangePassword:
    @pytest.mark.asyncio
    async def test_no_token(self):
        from auth.api.routes.me_legacy import PasswordChangeRequest, change_password

        data = PasswordChangeRequest(current_password="old", new_password="NewStr0ng!")
        with pytest.raises(HTTPException) as exc:
            await change_password(data, AsyncMock(), AsyncMock(), AsyncMock(), authorization=None)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch("auth.services.auth.AuthService")
    @patch(f"{MODULE}.get_current_user_from_token", new_callable=AsyncMock)
    async def test_no_email(self, mock_get_user, MockAuth):
        from auth.api.routes.me_legacy import PasswordChangeRequest, change_password

        user = _make_user(with_email=False)
        mock_get_user.return_value = (user, str(user.id))

        data = PasswordChangeRequest(current_password="old", new_password="NewStr0ng!")
        with pytest.raises(HTTPException) as exc:
            await change_password(
                data, AsyncMock(), AsyncMock(), AsyncMock(), authorization="Bearer tok"
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    @patch("auth.services.auth.AuthService")
    @patch(f"{MODULE}.get_current_user_from_token", new_callable=AsyncMock)
    async def test_wrong_current_password(self, mock_get_user, MockAuth):
        from auth.api.routes.me_legacy import PasswordChangeRequest, change_password

        user = _make_user()
        mock_get_user.return_value = (user, str(user.id))

        auth_instance = MockAuth.return_value
        auth_instance.verify_credentials = AsyncMock(return_value=None)

        data = PasswordChangeRequest(current_password="wrong", new_password="NewStr0ng!")
        with pytest.raises(HTTPException) as exc:
            await change_password(
                data, AsyncMock(), AsyncMock(), AsyncMock(), authorization="Bearer tok"
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    @patch("auth.services.auth.AuthService")
    @patch(f"{MODULE}.get_current_user_from_token", new_callable=AsyncMock)
    async def test_success(self, mock_get_user, MockAuth):
        from auth.api.routes.me_legacy import PasswordChangeRequest, change_password

        user = _make_user()
        mock_get_user.return_value = (user, str(user.id))

        auth_instance = MockAuth.return_value
        auth_instance.verify_credentials = AsyncMock(return_value=user)

        password_service = AsyncMock()
        password_service.change_password = AsyncMock(return_value=True)
        db = AsyncMock()

        data = PasswordChangeRequest(current_password="old", new_password="NewStr0ng!")
        result = await change_password(
            data, db, AsyncMock(), password_service, authorization="Bearer tok"
        )

        assert result["message"] == "Password changed successfully"
        db.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# MFA endpoints
# ---------------------------------------------------------------------------


class TestGetMfaStatus:
    @pytest.mark.asyncio
    async def test_no_token(self):
        from auth.api.routes.me_legacy import get_mfa_status

        with pytest.raises(HTTPException) as exc:
            await get_mfa_status(AsyncMock(), AsyncMock(), AsyncMock(), authorization=None)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user_from_token", new_callable=AsyncMock)
    async def test_not_enabled(self, mock_get_user):
        from auth.api.routes.me_legacy import get_mfa_status

        user = _make_user()
        mock_get_user.return_value = (user, str(user.id))
        mfa_service = AsyncMock()
        mfa_service.get_user_mfa = AsyncMock(return_value=None)

        result = await get_mfa_status(
            AsyncMock(), AsyncMock(), mfa_service, authorization="Bearer tok"
        )
        assert result.totp_enabled is False

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user_from_token", new_callable=AsyncMock)
    async def test_enabled(self, mock_get_user):
        from auth.api.routes.me_legacy import get_mfa_status

        user = _make_user()
        mock_get_user.return_value = (user, str(user.id))
        mfa_service = AsyncMock()
        user_mfa = MagicMock()
        user_mfa.totp_enabled = True
        mfa_service.get_user_mfa = AsyncMock(return_value=user_mfa)
        mfa_service.get_backup_codes_status = AsyncMock(return_value=(5, 10))

        result = await get_mfa_status(
            AsyncMock(), AsyncMock(), mfa_service, authorization="Bearer tok"
        )
        assert result.totp_enabled is True
        assert result.backup_codes_remaining == 5


class TestSetupTotp:
    @pytest.mark.asyncio
    async def test_no_token(self):
        from auth.api.routes.me_legacy import setup_totp

        with pytest.raises(HTTPException) as exc:
            await setup_totp(AsyncMock(), AsyncMock(), AsyncMock(), authorization=None)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user_from_token", new_callable=AsyncMock)
    async def test_already_enabled(self, mock_get_user):
        from auth.api.routes.me_legacy import setup_totp

        user = _make_user()
        mock_get_user.return_value = (user, str(user.id))
        mfa_service = AsyncMock()
        user_mfa = MagicMock()
        user_mfa.totp_enabled = True
        mfa_service.get_user_mfa = AsyncMock(return_value=user_mfa)

        with pytest.raises(HTTPException) as exc:
            await setup_totp(AsyncMock(), AsyncMock(), mfa_service, authorization="Bearer tok")
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user_from_token", new_callable=AsyncMock)
    async def test_success(self, mock_get_user):
        from auth.api.routes.me_legacy import setup_totp

        user = _make_user()
        mock_get_user.return_value = (user, str(user.id))
        mfa_service = AsyncMock()
        mfa_service.get_user_mfa = AsyncMock(return_value=None)
        mfa_service.setup_totp = AsyncMock(
            return_value=("SECRET", "otpauth://...", "data:image/qr")
        )
        db = AsyncMock()

        result = await setup_totp(db, AsyncMock(), mfa_service, authorization="Bearer tok")
        assert result.secret == "SECRET"
        db.commit.assert_awaited_once()


class TestVerifyAndEnableTotp:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user_from_token", new_callable=AsyncMock)
    async def test_success(self, mock_get_user):
        from auth.api.routes.me_legacy import TOTPVerifyRequest, verify_and_enable_totp

        user = _make_user()
        mock_get_user.return_value = (user, str(user.id))
        mfa_service = AsyncMock()
        mfa_service.enable_totp = AsyncMock(return_value=["C1", "C2"])
        db = AsyncMock()

        data = TOTPVerifyRequest(code="123456")
        result = await verify_and_enable_totp(
            data, db, AsyncMock(), mfa_service, authorization="Bearer tok"
        )
        assert result.backup_codes == ["C1", "C2"]

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user_from_token", new_callable=AsyncMock)
    async def test_invalid_code(self, mock_get_user):
        from auth.api.routes.me_legacy import TOTPVerifyRequest, verify_and_enable_totp

        user = _make_user()
        mock_get_user.return_value = (user, str(user.id))
        mfa_service = AsyncMock()
        mfa_service.enable_totp = AsyncMock(return_value=None)

        data = TOTPVerifyRequest(code="wrong")
        with pytest.raises(HTTPException) as exc:
            await verify_and_enable_totp(
                data, AsyncMock(), AsyncMock(), mfa_service, authorization="Bearer tok"
            )
        assert exc.value.status_code == 400


class TestDisableTotp:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user_from_token", new_callable=AsyncMock)
    async def test_success(self, mock_get_user):
        from auth.api.routes.me_legacy import TOTPVerifyRequest, disable_totp

        user = _make_user()
        mock_get_user.return_value = (user, str(user.id))
        mfa_service = AsyncMock()
        mfa_service.disable_totp = AsyncMock(return_value=True)
        db = AsyncMock()

        data = TOTPVerifyRequest(code="123456")
        result = await disable_totp(data, db, AsyncMock(), mfa_service, authorization="Bearer tok")
        assert result["message"] == "TOTP disabled successfully"

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user_from_token", new_callable=AsyncMock)
    async def test_invalid_code(self, mock_get_user):
        from auth.api.routes.me_legacy import TOTPVerifyRequest, disable_totp

        user = _make_user()
        mock_get_user.return_value = (user, str(user.id))
        mfa_service = AsyncMock()
        mfa_service.disable_totp = AsyncMock(return_value=False)

        data = TOTPVerifyRequest(code="wrong")
        with pytest.raises(HTTPException) as exc:
            await disable_totp(
                data, AsyncMock(), AsyncMock(), mfa_service, authorization="Bearer tok"
            )
        assert exc.value.status_code == 400


class TestRegenerateBackupCodes:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user_from_token", new_callable=AsyncMock)
    async def test_success(self, mock_get_user):
        from auth.api.routes.me_legacy import TOTPVerifyRequest, regenerate_backup_codes

        user = _make_user()
        mock_get_user.return_value = (user, str(user.id))
        mfa_service = AsyncMock()
        mfa_service.regenerate_backup_codes = AsyncMock(return_value=["A", "B"])
        db = AsyncMock()

        data = TOTPVerifyRequest(code="123456")
        result = await regenerate_backup_codes(
            data, db, AsyncMock(), mfa_service, authorization="Bearer tok"
        )
        assert result.backup_codes == ["A", "B"]

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user_from_token", new_callable=AsyncMock)
    async def test_invalid_code(self, mock_get_user):
        from auth.api.routes.me_legacy import TOTPVerifyRequest, regenerate_backup_codes

        user = _make_user()
        mock_get_user.return_value = (user, str(user.id))
        mfa_service = AsyncMock()
        mfa_service.regenerate_backup_codes = AsyncMock(return_value=None)

        data = TOTPVerifyRequest(code="wrong")
        with pytest.raises(HTTPException) as exc:
            await regenerate_backup_codes(
                data, AsyncMock(), AsyncMock(), mfa_service, authorization="Bearer tok"
            )
        assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# Remaining branches
# ---------------------------------------------------------------------------


def _user_with_secondary_email_first():
    """A user whose non-primary email is listed before the primary one."""
    user = _make_user()
    secondary = MagicMock()
    secondary.email = "alias@example.com"
    secondary.is_primary = False
    user.emails = [secondary, *user.emails]
    return user


class TestChangePasswordSkipsNonPrimaryEmails:
    @pytest.mark.asyncio
    @patch("auth.services.auth.AuthService")
    @patch(f"{MODULE}.get_current_user_from_token", new_callable=AsyncMock)
    async def test_primary_email_is_selected(self, mock_get_user, MockAuth):
        from auth.api.routes.me_legacy import PasswordChangeRequest, change_password

        user = _user_with_secondary_email_first()
        mock_get_user.return_value = (user, str(user.id))
        MockAuth.return_value.verify_credentials = AsyncMock(return_value=user)

        password_service = AsyncMock()
        password_service.change_password = AsyncMock(return_value=True)

        data = PasswordChangeRequest(current_password="old", new_password="NewStr0ng!")
        result = await change_password(
            data, AsyncMock(), AsyncMock(), password_service, authorization="Bearer tok"
        )

        assert result["message"] == "Password changed successfully"
        assert MockAuth.return_value.verify_credentials.await_args[0][1] == "john@example.com"


class TestChangePasswordServiceFailure:
    @pytest.mark.asyncio
    @patch("auth.services.auth.AuthService")
    @patch(f"{MODULE}.get_current_user_from_token", new_callable=AsyncMock)
    async def test_failed_change_raises_500(self, mock_get_user, MockAuth):
        from auth.api.routes.me_legacy import PasswordChangeRequest, change_password

        user = _make_user()
        mock_get_user.return_value = (user, str(user.id))
        MockAuth.return_value.verify_credentials = AsyncMock(return_value=user)

        password_service = AsyncMock()
        password_service.change_password = AsyncMock(return_value=(False, "too weak"))
        db = AsyncMock()

        data = PasswordChangeRequest(current_password="old", new_password="NewStr0ng!")
        with pytest.raises(HTTPException) as exc:
            await change_password(
                data, db, AsyncMock(), password_service, authorization="Bearer tok"
            )

        assert exc.value.status_code == 500
        db.commit.assert_not_awaited()


class TestSetupTotpEmailSelection:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user_from_token", new_callable=AsyncMock)
    async def test_primary_email_used_as_qr_label(self, mock_get_user):
        from auth.api.routes.me_legacy import setup_totp

        user = _user_with_secondary_email_first()
        mock_get_user.return_value = (user, str(user.id))
        mfa_service = AsyncMock()
        mfa_service.get_user_mfa = AsyncMock(return_value=None)
        mfa_service.setup_totp = AsyncMock(return_value=("SECRET", "otpauth://uri", "qr"))

        result = await setup_totp(AsyncMock(), AsyncMock(), mfa_service, authorization="Bearer t")

        assert result.secret == "SECRET"
        assert mfa_service.setup_totp.await_args[0][2] == "john@example.com"

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_user_from_token", new_callable=AsyncMock)
    async def test_user_without_email_falls_back_to_placeholder(self, mock_get_user):
        from auth.api.routes.me_legacy import setup_totp

        user = _make_user(with_email=False)
        mock_get_user.return_value = (user, str(user.id))
        mfa_service = AsyncMock()
        mfa_service.get_user_mfa = AsyncMock(return_value=None)
        mfa_service.setup_totp = AsyncMock(return_value=("SECRET", "otpauth://uri", "qr"))

        await setup_totp(AsyncMock(), AsyncMock(), mfa_service, authorization="Bearer t")

        assert mfa_service.setup_totp.await_args[0][2] == "user"


class TestMfaEndpointsRequireBearerToken:
    @pytest.mark.asyncio
    async def test_verify_and_enable_totp(self):
        from auth.api.routes.me_legacy import TOTPVerifyRequest, verify_and_enable_totp

        with pytest.raises(HTTPException) as exc:
            await verify_and_enable_totp(
                TOTPVerifyRequest(code="123456"),
                AsyncMock(),
                AsyncMock(),
                AsyncMock(),
                authorization=None,
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_disable_totp(self):
        from auth.api.routes.me_legacy import TOTPVerifyRequest, disable_totp

        with pytest.raises(HTTPException) as exc:
            await disable_totp(
                TOTPVerifyRequest(code="123456"),
                AsyncMock(),
                AsyncMock(),
                AsyncMock(),
                authorization=None,
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_regenerate_backup_codes(self):
        from auth.api.routes.me_legacy import TOTPVerifyRequest, regenerate_backup_codes

        with pytest.raises(HTTPException) as exc:
            await regenerate_backup_codes(
                TOTPVerifyRequest(code="123456"),
                AsyncMock(),
                AsyncMock(),
                AsyncMock(),
                authorization=None,
            )
        assert exc.value.status_code == 401
