# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.api.routes.auth.mfa — MFA endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from tests.conftest import make_user

MODULE = "auth.api.routes.auth.mfa"


def _mock_request(cookies=None):
    request = MagicMock()
    request.cookies = cookies or {}
    return request


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestGetTenantPrefix:
    @patch(f"{MODULE}.get_tenant_context", return_value=None)
    def test_no_context(self, _):
        from auth.api.routes.auth.mfa import get_tenant_prefix

        assert get_tenant_prefix() == ""

    @patch(f"{MODULE}.get_tenant_context")
    def test_path_resolution(self, mock_ctx):
        from auth.api.routes.auth.mfa import get_tenant_prefix

        ctx = MagicMock()
        ctx.tenant_slug = "acme"
        ctx.resolution_method = "path"
        mock_ctx.return_value = ctx
        assert get_tenant_prefix() == "/t/acme"


class TestGetCurrentTenantId:
    @patch(f"{MODULE}.get_tenant_context", return_value=None)
    def test_no_context(self, _):
        from auth.api.routes.auth.mfa import get_current_tenant_id

        assert get_current_tenant_id() is None

    @patch(f"{MODULE}.get_tenant_context")
    def test_with_context(self, mock_ctx):
        from auth.api.routes.auth.mfa import get_current_tenant_id

        ctx = MagicMock()
        ctx.tenant_id = "tid"
        mock_ctx.return_value = ctx
        assert get_current_tenant_id() == "tid"


class TestMaskEmail:
    def test_normal_email(self):
        from auth.api.routes.auth.mfa import _mask_email

        assert _mask_email("john@example.com") == "j***n@example.com"

    def test_short_local(self):
        from auth.api.routes.auth.mfa import _mask_email

        # len("ab") == 2, which is <= 2, so uses short branch: local[0] + "***"
        assert _mask_email("ab@example.com") == "a***@example.com"

    def test_single_char_local(self):
        from auth.api.routes.auth.mfa import _mask_email

        assert _mask_email("a@example.com") == "a***@example.com"

    def test_two_char_local(self):
        from auth.api.routes.auth.mfa import _mask_email

        # len("ab") == 2 <= 2, short branch
        assert _mask_email("ab@x.com") == "a***@x.com"

    def test_invalid_no_at(self):
        from auth.api.routes.auth.mfa import _mask_email

        assert _mask_email("noemail") == "***@***"


# ---------------------------------------------------------------------------
# _get_current_user_id
# ---------------------------------------------------------------------------


class TestGetCurrentUserId:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session_id")
    async def test_success(self, _):
        from auth.api.routes.auth.mfa import _get_current_user_id

        request = _mock_request(cookies={"session_id": "tok123"})
        db = AsyncMock()
        session_service = AsyncMock()
        user = make_user()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)

        result = await _get_current_user_id(request, db, session_service)
        assert result == str(user.id)

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session_id")
    async def test_no_cookie(self, _):
        from auth.api.routes.auth.mfa import _get_current_user_id

        request = _mock_request(cookies={})
        db = AsyncMock()
        session_service = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await _get_current_user_id(request, db, session_service)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session_id")
    async def test_invalid_session(self, _):
        from auth.api.routes.auth.mfa import _get_current_user_id

        request = _mock_request(cookies={"session_id": "bad"})
        db = AsyncMock()
        session_service = AsyncMock()
        session_service.get_user_by_session_token = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc:
            await _get_current_user_id(request, db, session_service)
        assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# _get_current_user_email
# ---------------------------------------------------------------------------


class TestGetCurrentUserEmail:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session_id")
    async def test_success(self, _):
        from auth.api.routes.auth.mfa import _get_current_user_email

        request = _mock_request(cookies={"session_id": "tok"})
        db = AsyncMock()
        user = make_user()
        session_service = AsyncMock()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)

        with patch("auth.services.auth.AuthService") as MockAuth:
            auth_instance = MockAuth.return_value
            auth_instance.get_user_primary_email = AsyncMock(return_value="user@example.com")
            uid, email = await _get_current_user_email(request, db, session_service)

        assert uid == str(user.id)
        assert email == "user@example.com"

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session_id")
    async def test_no_email_fallback(self, _):
        from auth.api.routes.auth.mfa import _get_current_user_email

        request = _mock_request(cookies={"session_id": "tok"})
        db = AsyncMock()
        user = make_user()
        session_service = AsyncMock()
        session_service.get_user_by_session_token = AsyncMock(return_value=user)

        with patch("auth.services.auth.AuthService") as MockAuth:
            auth_instance = MockAuth.return_value
            auth_instance.get_user_primary_email = AsyncMock(return_value=None)
            uid, email = await _get_current_user_email(request, db, session_service)

        assert email == "user"

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session_id")
    async def test_no_cookie(self, _):
        from auth.api.routes.auth.mfa import _get_current_user_email

        request = _mock_request(cookies={})
        db = AsyncMock()
        session_service = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await _get_current_user_email(request, db, session_service)
        assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# get_mfa_status
# ---------------------------------------------------------------------------


class TestGetMFAStatus:
    @pytest.mark.asyncio
    @patch(f"{MODULE}._get_current_user_id", new_callable=AsyncMock, return_value="uid-1")
    async def test_not_enabled(self, _):
        from auth.api.routes.auth.mfa import get_mfa_status

        request = _mock_request()
        db = AsyncMock()
        session_service = AsyncMock()
        mfa_service = AsyncMock()
        mfa_service.get_user_mfa = AsyncMock(return_value=None)

        result = await get_mfa_status(request, db, session_service, mfa_service)
        assert result.totp_enabled is False

    @pytest.mark.asyncio
    @patch(f"{MODULE}._get_current_user_id", new_callable=AsyncMock, return_value="uid-1")
    async def test_enabled_with_backup(self, _):
        from auth.api.routes.auth.mfa import get_mfa_status

        request = _mock_request()
        db = AsyncMock()
        session_service = AsyncMock()
        mfa_service = AsyncMock()
        user_mfa = MagicMock()
        user_mfa.totp_enabled = True
        mfa_service.get_user_mfa = AsyncMock(return_value=user_mfa)
        mfa_service.get_backup_codes_status = AsyncMock(return_value=(5, 10))

        result = await get_mfa_status(request, db, session_service, mfa_service)
        assert result.totp_enabled is True
        assert result.backup_codes_remaining == 5
        assert result.backup_codes_total == 10

    @pytest.mark.asyncio
    @patch(f"{MODULE}._get_current_user_id", new_callable=AsyncMock, return_value="uid-1")
    async def test_totp_disabled_in_mfa_object(self, _):
        from auth.api.routes.auth.mfa import get_mfa_status

        request = _mock_request()
        db = AsyncMock()
        session_service = AsyncMock()
        mfa_service = AsyncMock()
        user_mfa = MagicMock()
        user_mfa.totp_enabled = False
        mfa_service.get_user_mfa = AsyncMock(return_value=user_mfa)

        result = await get_mfa_status(request, db, session_service, mfa_service)
        assert result.totp_enabled is False


# ---------------------------------------------------------------------------
# setup_totp
# ---------------------------------------------------------------------------


class TestSetupTotp:
    @pytest.mark.asyncio
    @patch(
        f"{MODULE}._get_current_user_email",
        new_callable=AsyncMock,
        return_value=("uid-1", "u@e.com"),
    )
    async def test_success(self, _):
        from auth.api.routes.auth.mfa import setup_totp

        request = _mock_request()
        db = AsyncMock()
        session_service = AsyncMock()
        mfa_service = AsyncMock()
        mfa_service.get_user_mfa = AsyncMock(return_value=None)
        mfa_service.setup_totp = AsyncMock(
            return_value=("SECRET", "otpauth://...", "data:image/png;base64,...")
        )

        result = await setup_totp(request, db, session_service, mfa_service)
        assert result.secret == "SECRET"
        assert result.qr_code.startswith("data:image")
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(
        f"{MODULE}._get_current_user_email",
        new_callable=AsyncMock,
        return_value=("uid-1", "u@e.com"),
    )
    async def test_already_enabled(self, _):
        from auth.api.routes.auth.mfa import setup_totp

        request = _mock_request()
        db = AsyncMock()
        session_service = AsyncMock()
        mfa_service = AsyncMock()
        user_mfa = MagicMock()
        user_mfa.totp_enabled = True
        mfa_service.get_user_mfa = AsyncMock(return_value=user_mfa)

        with pytest.raises(HTTPException) as exc:
            await setup_totp(request, db, session_service, mfa_service)
        assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# verify_and_enable_totp
# ---------------------------------------------------------------------------


class TestVerifyAndEnableTotp:
    @pytest.mark.asyncio
    @patch(f"{MODULE}._get_current_user_id", new_callable=AsyncMock, return_value="uid-1")
    async def test_success(self, _):
        from auth.api.routes.auth.mfa import TOTPVerifyRequest, verify_and_enable_totp

        request = _mock_request()
        db = AsyncMock()
        session_service = AsyncMock()
        mfa_service = AsyncMock()
        mfa_service.enable_totp = AsyncMock(return_value=["CODE1", "CODE2"])

        data = TOTPVerifyRequest(code="123456")
        result = await verify_and_enable_totp(request, data, db, session_service, mfa_service)

        assert result.message == "TOTP enabled successfully"
        assert result.backup_codes == ["CODE1", "CODE2"]
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(f"{MODULE}._get_current_user_id", new_callable=AsyncMock, return_value="uid-1")
    async def test_invalid_code(self, _):
        from auth.api.routes.auth.mfa import TOTPVerifyRequest, verify_and_enable_totp

        request = _mock_request()
        db = AsyncMock()
        session_service = AsyncMock()
        mfa_service = AsyncMock()
        mfa_service.enable_totp = AsyncMock(return_value=None)

        data = TOTPVerifyRequest(code="wrong")
        with pytest.raises(HTTPException) as exc:
            await verify_and_enable_totp(request, data, db, session_service, mfa_service)
        assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# disable_totp
# ---------------------------------------------------------------------------


class TestDisableTotp:
    @pytest.mark.asyncio
    @patch(f"{MODULE}._get_current_user_id", new_callable=AsyncMock, return_value="uid-1")
    async def test_success(self, _):
        from auth.api.routes.auth.mfa import TOTPVerifyRequest, disable_totp

        request = _mock_request()
        db = AsyncMock()
        session_service = AsyncMock()
        mfa_service = AsyncMock()
        mfa_service.disable_totp = AsyncMock(return_value=True)

        data = TOTPVerifyRequest(code="123456")
        result = await disable_totp(request, data, db, session_service, mfa_service)

        assert result.message == "TOTP disabled successfully"
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(f"{MODULE}._get_current_user_id", new_callable=AsyncMock, return_value="uid-1")
    async def test_invalid_code(self, _):
        from auth.api.routes.auth.mfa import TOTPVerifyRequest, disable_totp

        request = _mock_request()
        db = AsyncMock()
        session_service = AsyncMock()
        mfa_service = AsyncMock()
        mfa_service.disable_totp = AsyncMock(return_value=False)

        data = TOTPVerifyRequest(code="wrong")
        with pytest.raises(HTTPException) as exc:
            await disable_totp(request, data, db, session_service, mfa_service)
        assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# regenerate_backup_codes
# ---------------------------------------------------------------------------


class TestRegenerateBackupCodes:
    @pytest.mark.asyncio
    @patch(f"{MODULE}._get_current_user_id", new_callable=AsyncMock, return_value="uid-1")
    async def test_success(self, _):
        from auth.api.routes.auth.mfa import TOTPVerifyRequest, regenerate_backup_codes

        request = _mock_request()
        db = AsyncMock()
        session_service = AsyncMock()
        mfa_service = AsyncMock()
        mfa_service.regenerate_backup_codes = AsyncMock(return_value=["A", "B", "C"])

        data = TOTPVerifyRequest(code="123456")
        result = await regenerate_backup_codes(request, data, db, session_service, mfa_service)

        assert result.backup_codes == ["A", "B", "C"]
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(f"{MODULE}._get_current_user_id", new_callable=AsyncMock, return_value="uid-1")
    async def test_invalid_code(self, _):
        from auth.api.routes.auth.mfa import TOTPVerifyRequest, regenerate_backup_codes

        request = _mock_request()
        db = AsyncMock()
        session_service = AsyncMock()
        mfa_service = AsyncMock()
        mfa_service.regenerate_backup_codes = AsyncMock(return_value=None)

        data = TOTPVerifyRequest(code="wrong")
        with pytest.raises(HTTPException) as exc:
            await regenerate_backup_codes(request, data, db, session_service, mfa_service)
        assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# verify_mfa_code
# ---------------------------------------------------------------------------


class TestVerifyMFACode:
    @pytest.mark.asyncio
    @patch(f"{MODULE}._get_current_user_id", new_callable=AsyncMock, return_value="uid-1")
    async def test_success(self, _):
        from auth.api.routes.auth.mfa import MFAVerifyRequest, verify_mfa_code

        request = _mock_request()
        db = AsyncMock()
        session_service = AsyncMock()
        mfa_service = AsyncMock()
        mfa_service.verify_mfa_code = AsyncMock(return_value=True)

        data = MFAVerifyRequest(code="123456")
        result = await verify_mfa_code(request, data, db, session_service, mfa_service)

        assert result.message == "Code verified successfully"

    @pytest.mark.asyncio
    @patch(f"{MODULE}._get_current_user_id", new_callable=AsyncMock, return_value="uid-1")
    async def test_invalid_code(self, _):
        from auth.api.routes.auth.mfa import MFAVerifyRequest, verify_mfa_code

        request = _mock_request()
        db = AsyncMock()
        session_service = AsyncMock()
        mfa_service = AsyncMock()
        mfa_service.verify_mfa_code = AsyncMock(return_value=False)

        data = MFAVerifyRequest(code="wrong")
        with pytest.raises(HTTPException) as exc:
            await verify_mfa_code(request, data, db, session_service, mfa_service)
        assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# mfa_setup_page (HTML)
# ---------------------------------------------------------------------------


class TestMFASetupPage:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}._get_current_user_email", new_callable=AsyncMock)
    async def test_not_authenticated(self, mock_email, _pfx, _tid):
        from auth.api.routes.auth.mfa import mfa_setup_page

        mock_email.side_effect = HTTPException(status_code=401, detail="Not authenticated")

        request = _mock_request()
        db = AsyncMock()
        session_service = AsyncMock()
        mfa_service = AsyncMock()
        branding = AsyncMock()
        branding.render_template = AsyncMock(return_value="<html>login</html>")

        result = await mfa_setup_page(request, db, session_service, mfa_service, branding)
        assert result.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(
        f"{MODULE}._get_current_user_email",
        new_callable=AsyncMock,
        return_value=("uid-1", "u@e.com"),
    )
    async def test_already_enabled(self, _email, _pfx, _tid):
        from auth.api.routes.auth.mfa import mfa_setup_page

        request = _mock_request()
        db = AsyncMock()
        session_service = AsyncMock()
        mfa_service = AsyncMock()
        user_mfa = MagicMock()
        user_mfa.totp_enabled = True
        mfa_service.get_user_mfa = AsyncMock(return_value=user_mfa)
        branding = AsyncMock()
        branding.render_template = AsyncMock(return_value="<html>already</html>")

        result = await mfa_setup_page(request, db, session_service, mfa_service, branding)
        assert result.status_code == 200

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(
        f"{MODULE}._get_current_user_email",
        new_callable=AsyncMock,
        return_value=("uid-1", "u@e.com"),
    )
    async def test_setup_success(self, _email, _pfx, _tid):
        from auth.api.routes.auth.mfa import mfa_setup_page

        request = _mock_request()
        db = AsyncMock()
        session_service = AsyncMock()
        mfa_service = AsyncMock()
        mfa_service.get_user_mfa = AsyncMock(return_value=None)
        mfa_service.setup_totp = AsyncMock(
            return_value=("SECRET", "otpauth://...", "data:image/qr")
        )
        branding = AsyncMock()
        branding.render_template = AsyncMock(return_value="<html>setup</html>")

        result = await mfa_setup_page(request, db, session_service, mfa_service, branding)
        assert result.status_code == 200
        db.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# send_mfa_email
# ---------------------------------------------------------------------------


class TestSendMFAEmail:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.settings")
    @patch(
        f"{MODULE}._get_current_user_email",
        new_callable=AsyncMock,
        return_value=("uid-1", "user@example.com"),
    )
    async def test_success(self, _email, mock_settings):
        from auth.api.routes.auth.mfa import send_mfa_email

        mock_settings.mfa_email_code_expiry_minutes = 10
        request = _mock_request()
        db = AsyncMock()
        session_service = AsyncMock()
        mfa_service = AsyncMock()
        mfa_service.send_mfa_email_code = AsyncMock(return_value="123456")
        email_service = AsyncMock()
        email_service.send_email = AsyncMock(return_value=True)

        result = await send_mfa_email(request, db, session_service, mfa_service, email_service)

        assert "sent to your email" in result.message
        assert result.email_masked == "u***r@example.com"
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(
        f"{MODULE}._get_current_user_email",
        new_callable=AsyncMock,
        return_value=("uid-1", "user@example.com"),
    )
    async def test_code_generation_fails(self, _email):
        from auth.api.routes.auth.mfa import send_mfa_email

        request = _mock_request()
        db = AsyncMock()
        session_service = AsyncMock()
        mfa_service = AsyncMock()
        mfa_service.send_mfa_email_code = AsyncMock(return_value=None)
        email_service = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await send_mfa_email(request, db, session_service, mfa_service, email_service)
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    @patch(f"{MODULE}.settings")
    @patch(
        f"{MODULE}._get_current_user_email",
        new_callable=AsyncMock,
        return_value=("uid-1", "user@example.com"),
    )
    async def test_send_email_fails(self, _email, mock_settings):
        from auth.api.routes.auth.mfa import send_mfa_email

        mock_settings.mfa_email_code_expiry_minutes = 10
        request = _mock_request()
        db = AsyncMock()
        session_service = AsyncMock()
        mfa_service = AsyncMock()
        mfa_service.send_mfa_email_code = AsyncMock(return_value="123456")
        email_service = AsyncMock()
        email_service.send_email = AsyncMock(return_value=False)

        with pytest.raises(HTTPException) as exc:
            await send_mfa_email(request, db, session_service, mfa_service, email_service)
        assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# verify_mfa_email
# ---------------------------------------------------------------------------


class TestVerifyMFAEmail:
    @pytest.mark.asyncio
    @patch(f"{MODULE}._get_current_user_id", new_callable=AsyncMock, return_value="uid-1")
    async def test_success(self, _):
        from auth.api.routes.auth.mfa import MFAVerifyRequest, verify_mfa_email

        request = _mock_request()
        db = AsyncMock()
        session_service = AsyncMock()
        mfa_service = AsyncMock()
        mfa_service.verify_email_code = AsyncMock(return_value=True)

        data = MFAVerifyRequest(code="123456")
        result = await verify_mfa_email(request, data, db, session_service, mfa_service)

        assert result.message == "Email code verified successfully"
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(f"{MODULE}._get_current_user_id", new_callable=AsyncMock, return_value="uid-1")
    async def test_invalid_code(self, _):
        from auth.api.routes.auth.mfa import MFAVerifyRequest, verify_mfa_email

        request = _mock_request()
        db = AsyncMock()
        session_service = AsyncMock()
        mfa_service = AsyncMock()
        mfa_service.verify_email_code = AsyncMock(return_value=False)

        data = MFAVerifyRequest(code="wrong")
        with pytest.raises(HTTPException) as exc:
            await verify_mfa_email(request, data, db, session_service, mfa_service)
        assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# mfa_email_page (HTML)
# ---------------------------------------------------------------------------


class TestMFAEmailPage:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}._get_current_user_email", new_callable=AsyncMock)
    async def test_not_authenticated(self, mock_email, _pfx, _tid):
        from auth.api.routes.auth.mfa import mfa_email_page

        mock_email.side_effect = HTTPException(status_code=401, detail="Not authenticated")

        request = _mock_request()
        db = AsyncMock()
        session_service = AsyncMock()
        branding = AsyncMock()
        branding.render_template = AsyncMock(return_value="<html>login</html>")

        result = await mfa_email_page(request, db, session_service, branding)
        assert result.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(
        f"{MODULE}._get_current_user_email",
        new_callable=AsyncMock,
        return_value=("uid-1", "john@e.com"),
    )
    async def test_authenticated(self, _email, _pfx, _tid):
        from auth.api.routes.auth.mfa import mfa_email_page

        request = _mock_request()
        db = AsyncMock()
        session_service = AsyncMock()
        branding = AsyncMock()
        branding.render_template = AsyncMock(return_value="<html>mfa</html>")

        result = await mfa_email_page(request, db, session_service, branding)
        assert result.status_code == 200


class TestGetCurrentUserEmailInvalidSession:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session_id")
    async def test_unknown_session_raises_401(self, _):
        from auth.api.routes.auth.mfa import _get_current_user_email

        session_service = AsyncMock()
        session_service.get_user_by_session_token = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc:
            await _get_current_user_email(
                _mock_request(cookies={"session_id": "tok"}), AsyncMock(), session_service
            )

        assert exc.value.status_code == 401


class TestMFASetupReconfigure:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}._get_current_user_email", new_callable=AsyncMock)
    async def test_not_authenticated_renders_401(self, mock_email, _pfx, _tid):
        from auth.api.routes.auth.mfa import mfa_setup_reconfigure

        mock_email.side_effect = HTTPException(status_code=401, detail="Not authenticated")
        branding = AsyncMock()
        branding.render_template = AsyncMock(return_value="<html>login</html>")

        result = await mfa_setup_reconfigure(
            _mock_request(), AsyncMock(), AsyncMock(), AsyncMock(), branding
        )

        assert result.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(
        f"{MODULE}._get_current_user_email",
        new_callable=AsyncMock,
        return_value=("uid-1", "u@e.com"),
    )
    async def test_generates_a_fresh_secret(self, _email, _pfx, _tid):
        from auth.api.routes.auth.mfa import mfa_setup_reconfigure

        mfa_service = AsyncMock()
        mfa_service.setup_totp = AsyncMock(return_value=("SECRET", "otpauth://uri", "qr-data"))
        branding = AsyncMock()
        branding.render_template = AsyncMock(return_value="<html>setup</html>")
        db = AsyncMock()

        result = await mfa_setup_reconfigure(
            _mock_request(), db, AsyncMock(), mfa_service, branding
        )

        assert result.status_code == 200
        db.commit.assert_awaited_once()
        context = branding.render_template.await_args[0][2]
        assert context["secret"] == "SECRET"
        assert context["qr_code"] == "qr-data"
        assert context["already_enabled"] is False
