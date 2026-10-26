# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for knowledge/services/auth_api.py — AuthAPIClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from knowledge.services.auth_api import (
    AuthAPIClient,
    AuthAPIError,
    MFAStatus,
    PlanType,
    ProfileResult,
    RegisterResult,
    TokenResult,
    TOTPEnableResult,
    TOTPSetupResult,
    get_auth_api_client,
)


def _mock_settings():
    s = MagicMock()
    s.oauth2_issuer = "http://auth.test"
    s.oauth2_client_id = "client-id"
    s.oauth2_client_secret = "client-secret"
    s.app_base_url = "https://knowledge.test"
    return s


def _make_response(status_code=200, json_data=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    if json_data is not None:
        resp.json.return_value = json_data
    else:
        resp.json.side_effect = Exception("no json")
    resp.text = text
    return resp


def _make_async_client(response):
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=response)
    mock_client.get = AsyncMock(return_value=response)
    mock_client.put = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


class TestAuthAPIError:
    def test_auth_api_error(self):
        err = AuthAPIError("test error", error_code="test_code")
        assert err.message == "test error"
        assert err.error_code == "test_code"
        assert "test error" in str(err)


class TestPlanType:
    def test_plan_types(self):
        assert PlanType.PERSONAL == "personal"
        assert PlanType.ENTERPRISE == "enterprise"


class TestAuthAPIClient:
    @patch("knowledge.services.auth_api.settings", _mock_settings())
    def _make_client(self):
        return AuthAPIClient()

    # --- register ---

    async def test_register_success(self):
        client = self._make_client()
        resp = _make_response(200, {"id": "user-1", "email": "a@b.com", "message": "ok"})
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            result = await client.register("a@b.com", "pass", "nick", "First", "Last")
        assert isinstance(result, RegisterResult)
        assert result.user_id == "user-1"

    async def test_register_with_profile_extra(self):
        client = self._make_client()
        resp = _make_response(200, {"id": "user-1", "email": "a@b.com", "message": "ok"})
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            result = await client.register(
                "a@b.com",
                "pass",
                "nick",
                "First",
                "Last",
                profile_extra={"locale": "fr"},
            )
        assert result.user_id == "user-1"

    async def test_register_error_json(self):
        client = self._make_client()
        resp = _make_response(400, {"detail": "Email taken"})
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError, match="Email taken"):
                await client.register("a@b.com", "pass", "nick", "First", "Last")

    async def test_register_error_no_json(self):
        client = self._make_client()
        resp = _make_response(500, text="Internal error")
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError):
                await client.register("a@b.com", "pass", "nick", "First", "Last")

    async def test_register_connection_error(self):
        client = self._make_client()
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=httpx.RequestError("fail"))
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError, match="Unable to connect"):
                await client.register("a@b.com", "pass", "nick", "First", "Last")

    # --- verify_email ---

    async def test_verify_email_success(self):
        client = self._make_client()
        resp = _make_response(200, {"message": "verified"})
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            result = await client.verify_email("a@b.com", "123456")
        assert result is True

    async def test_verify_email_error_json(self):
        client = self._make_client()
        resp = _make_response(400, {"detail": "Invalid code"})
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError, match="Invalid code"):
                await client.verify_email("a@b.com", "wrong")

    async def test_verify_email_error_no_json(self):
        client = self._make_client()
        resp = _make_response(500, text="Error")
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError):
                await client.verify_email("a@b.com", "code")

    async def test_verify_email_connection_error(self):
        client = self._make_client()
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=httpx.RequestError("fail"))
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError, match="Unable to connect"):
                await client.verify_email("a@b.com", "code")

    # --- resend_verification ---

    async def test_resend_verification_success(self):
        client = self._make_client()
        resp = _make_response(200, {"message": "sent"})
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            result = await client.resend_verification("a@b.com")
        assert result is True

    async def test_resend_verification_failure_returns_true(self):
        client = self._make_client()
        resp = _make_response(500, text="Error")
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            result = await client.resend_verification("a@b.com")
        assert result is True  # always True to prevent enumeration

    async def test_resend_verification_connection_error(self):
        client = self._make_client()
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=httpx.RequestError("fail"))
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError, match="Unable to connect"):
                await client.resend_verification("a@b.com")

    # --- forgot_password ---

    async def test_forgot_password_success(self):
        client = self._make_client()
        resp = _make_response(200, {"message": "sent"})
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            result = await client.forgot_password("a@b.com")
        assert result is True

    async def test_forgot_password_with_custom_url(self):
        client = self._make_client()
        resp = _make_response(200, {"message": "sent"})
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            result = await client.forgot_password("a@b.com", reset_base_url="https://custom.test")
        assert result is True

    async def test_forgot_password_failure_returns_true(self):
        client = self._make_client()
        resp = _make_response(500, text="Error")
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            result = await client.forgot_password("a@b.com")
        assert result is True  # always True to prevent enumeration

    async def test_forgot_password_connection_error(self):
        client = self._make_client()
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=httpx.RequestError("fail"))
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError, match="Unable to connect"):
                await client.forgot_password("a@b.com")

    async def test_forgot_password_no_base_url(self):
        """Test forgot_password when both reset_base_url and app_base_url are empty."""
        client = self._make_client()
        resp = _make_response(200, {"message": "sent"})
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with patch("knowledge.services.auth_api.settings") as mock_settings:
                mock_settings.app_base_url = ""
                mock_settings.oauth2_issuer = "http://auth.test"
                mock_settings.oauth2_client_id = "client-id"
                mock_settings.oauth2_client_secret = "client-secret"
                result = await client.forgot_password("a@b.com")
        assert result is True

    # --- reset_password ---

    async def test_reset_password_success(self):
        client = self._make_client()
        resp = _make_response(200, {"message": "reset"})
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            result = await client.reset_password("token", "newpass")
        assert result is True

    async def test_reset_password_error_json(self):
        client = self._make_client()
        resp = _make_response(400, {"detail": "Token expired"})
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError, match="Token expired"):
                await client.reset_password("bad-token", "newpass")

    async def test_reset_password_error_no_json(self):
        client = self._make_client()
        resp = _make_response(500, text="Error")
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError):
                await client.reset_password("token", "newpass")

    async def test_reset_password_connection_error(self):
        client = self._make_client()
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=httpx.RequestError("fail"))
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError, match="Unable to connect"):
                await client.reset_password("token", "newpass")

    # --- login ---

    async def test_login_success(self):
        client = self._make_client()
        resp = _make_response(
            200,
            {
                "access_token": "at",
                "refresh_token": "rt",
                "expires_in": 3600,
                "token_type": "Bearer",
                "id_token": "idt",
            },
        )
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            result = await client.login("a@b.com", "pass")
        assert isinstance(result, TokenResult)
        assert result.access_token == "at"
        assert result.refresh_token == "rt"
        assert result.id_token == "idt"

    async def test_login_custom_scopes(self):
        client = self._make_client()
        resp = _make_response(
            200,
            {
                "access_token": "at",
                "expires_in": 3600,
            },
        )
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            result = await client.login("a@b.com", "pass", scopes=["openid"])
        assert result.access_token == "at"

    async def test_login_with_otp(self):
        client = self._make_client()
        resp = _make_response(
            200,
            {
                "access_token": "at",
                "expires_in": 3600,
            },
        )
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            result = await client.login("a@b.com", "pass", otp="123456")
        assert result.access_token == "at"
        call_kwargs = mock_http.post.call_args.kwargs
        assert call_kwargs["data"]["otp"] == "123456"

    async def test_login_error_json(self):
        client = self._make_client()
        resp = _make_response(
            401,
            {
                "error": "invalid_grant",
                "error_description": "Invalid credentials",
            },
        )
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError, match="Invalid credentials"):
                await client.login("a@b.com", "wrong")

    async def test_login_error_no_json(self):
        client = self._make_client()
        resp = _make_response(500, text="Error")
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError):
                await client.login("a@b.com", "pass")

    async def test_login_connection_error(self):
        client = self._make_client()
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=httpx.RequestError("fail"))
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError, match="Unable to connect"):
                await client.login("a@b.com", "pass")

    async def test_send_login_mfa_email_code_success(self):
        client = self._make_client()
        step1 = _make_response(200, text="ok")
        step2 = _make_response(200, text="Verification code sent to t***t@example.com")
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=[step1, step2])
        mock_http.get = AsyncMock(return_value=step2)
        mock_http.put = AsyncMock(return_value=step2)
        mock_http.cookies = MagicMock()
        mock_http.cookies.get = MagicMock(return_value="challenge-token")
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            result = await client.send_login_mfa_email_code("a@b.com", "pass")
        assert result == "t***t@example.com"

    async def test_send_login_mfa_email_code_requires_mfa(self):
        client = self._make_client()
        step1 = _make_response(200, text="ok")
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=step1)
        mock_http.get = AsyncMock(return_value=step1)
        mock_http.put = AsyncMock(return_value=step1)
        mock_http.cookies = MagicMock()
        mock_http.cookies.get = MagicMock(return_value=None)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError, match="MFA is not enabled"):
                await client.send_login_mfa_email_code("a@b.com", "pass")

    # --- get_userinfo ---

    async def test_get_userinfo_success(self):
        client = self._make_client()
        resp = _make_response(200, {"sub": "user-1", "email": "a@b.com"})
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            result = await client.get_userinfo("access-token")
        assert result["sub"] == "user-1"

    async def test_get_userinfo_error(self):
        client = self._make_client()
        resp = _make_response(401, text="Unauthorized")
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError, match="Failed to get user info"):
                await client.get_userinfo("bad-token")

    async def test_get_userinfo_connection_error(self):
        client = self._make_client()
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=httpx.RequestError("fail"))
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError, match="Unable to connect"):
                await client.get_userinfo("token")

    # --- get_profile ---

    async def test_get_profile_success(self):
        client = self._make_client()
        resp = _make_response(
            200,
            {
                "sub": "user-1",
                "nickname": "nick",
                "name": "User Name",
                "given_name": "User",
                "family_name": "Name",
            },
        )
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            result = await client.get_profile("access-token")
        assert isinstance(result, ProfileResult)
        assert result.sub == "user-1"
        assert result.nickname == "nick"

    async def test_get_profile_error(self):
        client = self._make_client()
        resp = _make_response(401, text="Unauthorized")
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError, match="Failed to get profile"):
                await client.get_profile("bad-token")

    async def test_get_profile_connection_error(self):
        client = self._make_client()
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=httpx.RequestError("fail"))
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError, match="Unable to connect"):
                await client.get_profile("token")

    # --- update_profile ---

    async def test_update_profile_success(self):
        client = self._make_client()
        resp = _make_response(
            200,
            {
                "sub": "user-1",
                "nickname": "new-nick",
                "name": "New Name",
                "given_name": "New",
                "family_name": "Name",
            },
        )
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            result = await client.update_profile(
                "access-token",
                nickname="new-nick",
                given_name="New",
                family_name="Name",
                middle_name="M",
                preferred_username="newuser",
                picture="http://pic.test",
                website="http://web.test",
                gender="other",
                birthdate="1990-01-01",
                zoneinfo="America/New_York",
                locale="en",
                phone_number="+1234567890",
            )
        assert isinstance(result, ProfileResult)
        assert result.nickname == "new-nick"

    async def test_update_profile_only_given_name(self):
        """Test update_profile with only given_name set (nickname=None, branch 595->597)."""
        client = self._make_client()
        resp = _make_response(
            200,
            {
                "sub": "user-1",
                "given_name": "Updated",
            },
        )
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            result = await client.update_profile(
                "access-token",
                given_name="Updated",
            )
        assert isinstance(result, ProfileResult)
        # Verify only given_name was in payload (nickname was not sent)
        call_kwargs = mock_http.put.call_args
        import json

        body = json.loads(
            call_kwargs.kwargs.get(
                "content", call_kwargs.args[1] if len(call_kwargs.args) > 1 else b"{}"
            )
        )
        assert "nickname" not in body

    async def test_update_profile_error_json(self):
        client = self._make_client()
        resp = _make_response(400, {"detail": "Validation error"})
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError, match="Validation error"):
                await client.update_profile("token", nickname="bad")

    async def test_update_profile_error_no_json(self):
        client = self._make_client()
        resp = _make_response(500, text="Error")
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError):
                await client.update_profile("token", nickname="bad")

    async def test_update_profile_connection_error(self):
        client = self._make_client()
        mock_http = AsyncMock()
        mock_http.put = AsyncMock(side_effect=httpx.RequestError("fail"))
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError, match="Unable to connect"):
                await client.update_profile("token", nickname="new")

    # --- change_password ---

    async def test_change_password_success(self):
        client = self._make_client()
        resp = _make_response(200, {"message": "changed"})
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            result = await client.change_password("token", "oldpass", "newpass")
        assert result is True

    async def test_change_password_error_json(self):
        client = self._make_client()
        resp = _make_response(400, {"detail": "Wrong password"})
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError, match="Wrong password"):
                await client.change_password("token", "wrong", "newpass")

    async def test_change_password_error_no_json(self):
        client = self._make_client()
        resp = _make_response(500, text="Error")
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError):
                await client.change_password("token", "old", "new")

    async def test_change_password_connection_error(self):
        client = self._make_client()
        mock_http = AsyncMock()
        mock_http.put = AsyncMock(side_effect=httpx.RequestError("fail"))
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError, match="Unable to connect"):
                await client.change_password("token", "old", "new")

    # --- get_mfa_status ---

    async def test_get_mfa_status_success(self):
        client = self._make_client()
        resp = _make_response(
            200,
            {
                "totp_enabled": True,
                "backup_codes_remaining": 5,
                "backup_codes_total": 10,
            },
        )
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            result = await client.get_mfa_status("token")
        assert isinstance(result, MFAStatus)
        assert result.totp_enabled is True
        assert result.backup_codes_remaining == 5

    async def test_get_mfa_status_error(self):
        client = self._make_client()
        resp = _make_response(401, text="Unauthorized")
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError, match="Failed to get MFA status"):
                await client.get_mfa_status("bad-token")

    async def test_get_mfa_status_connection_error(self):
        client = self._make_client()
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=httpx.RequestError("fail"))
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError, match="Unable to connect"):
                await client.get_mfa_status("token")

    # --- setup_totp ---

    async def test_setup_totp_success(self):
        client = self._make_client()
        resp = _make_response(
            200, {"secret": "JBSWY3DPEHPK3PXP", "qr_code": "data:image/png;base64,..."}
        )
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            result = await client.setup_totp("token")
        assert isinstance(result, TOTPSetupResult)
        assert result.secret == "JBSWY3DPEHPK3PXP"

    async def test_setup_totp_error_json(self):
        client = self._make_client()
        resp = _make_response(400, {"detail": "Already enabled"})
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError, match="Already enabled"):
                await client.setup_totp("token")

    async def test_setup_totp_error_no_json(self):
        client = self._make_client()
        resp = _make_response(500, text="Error")
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError):
                await client.setup_totp("token")

    async def test_setup_totp_connection_error(self):
        client = self._make_client()
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=httpx.RequestError("fail"))
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError, match="Unable to connect"):
                await client.setup_totp("token")

    # --- verify_and_enable_totp ---

    async def test_verify_and_enable_totp_success(self):
        client = self._make_client()
        resp = _make_response(
            200,
            {
                "message": "TOTP enabled",
                "backup_codes": ["code1", "code2", "code3"],
            },
        )
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            result = await client.verify_and_enable_totp("token", "123456")
        assert isinstance(result, TOTPEnableResult)
        assert result.message == "TOTP enabled"
        assert len(result.backup_codes) == 3

    async def test_verify_and_enable_totp_error_json(self):
        client = self._make_client()
        resp = _make_response(400, {"detail": "Invalid TOTP code"})
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError, match="Invalid TOTP code"):
                await client.verify_and_enable_totp("token", "wrong")

    async def test_verify_and_enable_totp_error_no_json(self):
        client = self._make_client()
        resp = _make_response(500, text="Error")
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError):
                await client.verify_and_enable_totp("token", "code")

    async def test_verify_and_enable_totp_connection_error(self):
        client = self._make_client()
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=httpx.RequestError("fail"))
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError, match="Unable to connect"):
                await client.verify_and_enable_totp("token", "code")

    # --- disable_totp ---

    async def test_disable_totp_success(self):
        client = self._make_client()
        resp = _make_response(200, {"message": "disabled"})
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            result = await client.disable_totp("token", "123456")
        assert result is True

    async def test_disable_totp_error_json(self):
        client = self._make_client()
        resp = _make_response(400, {"detail": "Invalid code"})
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError, match="Invalid code"):
                await client.disable_totp("token", "wrong")

    async def test_disable_totp_error_no_json(self):
        client = self._make_client()
        resp = _make_response(500, text="Error")
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError):
                await client.disable_totp("token", "code")

    async def test_disable_totp_connection_error(self):
        client = self._make_client()
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=httpx.RequestError("fail"))
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError, match="Unable to connect"):
                await client.disable_totp("token", "code")

    # --- regenerate_backup_codes ---

    async def test_regenerate_backup_codes_success(self):
        client = self._make_client()
        resp = _make_response(200, {"backup_codes": ["c1", "c2", "c3"]})
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            result = await client.regenerate_backup_codes("token", "123456")
        assert result == ["c1", "c2", "c3"]

    async def test_regenerate_backup_codes_error_json(self):
        client = self._make_client()
        resp = _make_response(400, {"detail": "Invalid code"})
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError, match="Invalid code"):
                await client.regenerate_backup_codes("token", "wrong")

    async def test_regenerate_backup_codes_error_no_json(self):
        client = self._make_client()
        resp = _make_response(500, text="Error")
        mock_http = _make_async_client(resp)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError):
                await client.regenerate_backup_codes("token", "code")

    async def test_regenerate_backup_codes_connection_error(self):
        client = self._make_client()
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=httpx.RequestError("fail"))
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("knowledge.services.auth_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(AuthAPIError, match="Unable to connect"):
                await client.regenerate_backup_codes("token", "code")


# --- get_auth_api_client ---


class TestGetAuthApiClient:
    @patch("knowledge.services.auth_api.settings", _mock_settings())
    def test_get_auth_api_client(self):
        client = get_auth_api_client()
        assert isinstance(client, AuthAPIClient)
