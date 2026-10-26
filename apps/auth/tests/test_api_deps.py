# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.api.deps — FastAPI dependency injection."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from tests.conftest import (
    make_access_token,
    make_personal_access_token,
    make_session,
    make_user,
)

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


class TestBearerTokenAuth:
    def test_fields(self):
        from auth.api.deps import BearerTokenAuth

        auth = BearerTokenAuth(client_id="c1", scopes=["read"], subject="u1")
        assert auth.client_id == "c1"
        assert auth.scopes == ["read"]
        assert auth.subject == "u1"

    def test_defaults(self):
        from auth.api.deps import BearerTokenAuth

        auth = BearerTokenAuth(client_id="c1", scopes=[])
        assert auth.subject is None


class TestPATAuth:
    def test_fields(self):
        from auth.api.deps import PATAuth

        auth = PATAuth(
            user_id="u1",
            pat_id="p1",
            scopes=["read"],
            tenant_id="t1",
            target_client_id="c1",
        )
        assert auth.user_id == "u1"
        assert auth.pat_id == "p1"
        assert auth.scopes == ["read"]
        assert auth.tenant_id == "t1"
        assert auth.target_client_id == "c1"

    def test_defaults(self):
        from auth.api.deps import PATAuth

        auth = PATAuth(user_id="u1", pat_id="p1", scopes=[])
        assert auth.tenant_id is None
        assert auth.target_client_id is None


# ---------------------------------------------------------------------------
# get_db
# ---------------------------------------------------------------------------


class TestGetDb:
    @pytest.mark.asyncio
    @patch("auth.api.deps.async_session_factory")
    async def test_yields_session_and_commits(self, mock_factory):
        from auth.api.deps import get_db

        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        gen = get_db()
        session = await gen.__anext__()
        assert session is mock_session

        # Exhaust the generator (triggers commit)
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()

        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("auth.api.deps.async_session_factory")
    async def test_rollback_on_exception(self, mock_factory):
        from auth.api.deps import get_db

        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        gen = get_db()
        await gen.__anext__()

        # Simulate an exception during yield
        with pytest.raises(ValueError):
            await gen.athrow(ValueError("boom"))

        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_encryption
# ---------------------------------------------------------------------------


class TestGetEncryption:
    @patch("auth.api.deps.settings")
    @patch("auth.api.deps.AESEncryption")
    def test_returns_encryption_instance(self, mock_aes, mock_settings):
        from auth.api.deps import get_encryption

        # Clear lru_cache
        get_encryption.cache_clear()

        mock_settings.jwks_encryption_key = "dGVzdGtleXRlc3RrZXkxMjM0NTY3ODkwMTI="
        mock_aes.from_base64.return_value = MagicMock()

        result = get_encryption()

        mock_aes.from_base64.assert_called_once_with(mock_settings.jwks_encryption_key)
        assert result is mock_aes.from_base64.return_value
        get_encryption.cache_clear()


# ---------------------------------------------------------------------------
# Service factories
# ---------------------------------------------------------------------------


class TestServiceFactories:
    @patch("auth.api.deps.get_encryption", return_value=MagicMock())
    def test_get_jwks_service(self, mock_enc):
        from auth.api.deps import get_jwks_service
        from auth.services.jwks import JWKSService

        result = get_jwks_service()
        assert isinstance(result, JWKSService)

    def test_get_user_service(self):
        from auth.api.deps import get_user_service
        from auth.services.user import UserService

        assert isinstance(get_user_service(), UserService)

    def test_get_email_service(self):
        from auth.api.deps import get_email_service
        from auth.services.email import EmailService

        assert isinstance(get_email_service(), EmailService)

    def test_get_password_service(self):
        from auth.api.deps import get_password_service
        from auth.services.password import PasswordService

        assert isinstance(get_password_service(), PasswordService)

    def test_get_auth_service(self):
        from auth.api.deps import get_auth_service
        from auth.services.auth import AuthService

        assert isinstance(get_auth_service(), AuthService)

    def test_get_session_service(self):
        from auth.api.deps import get_session_service
        from auth.services.session import SessionService

        assert isinstance(get_session_service(), SessionService)

    @patch("auth.api.deps.get_encryption", return_value=MagicMock())
    def test_get_mfa_service(self, mock_enc):
        from auth.api.deps import get_mfa_service
        from auth.services.mfa import MFAService

        assert isinstance(get_mfa_service(), MFAService)

    def test_get_oauth2_client_service(self):
        from auth.api.deps import get_oauth2_client_service
        from auth.services.oauth2_client import OAuth2ClientService

        assert isinstance(get_oauth2_client_service(), OAuth2ClientService)

    @patch("auth.api.deps.get_encryption", return_value=MagicMock())
    @patch("auth.api.deps.get_jwks_service")
    def test_get_token_service(self, mock_jwks, mock_enc):
        from auth.api.deps import get_token_service

        mock_jwks.return_value = MagicMock()
        result = get_token_service()
        assert result is not None

    def test_get_device_code_service(self):
        from auth.api.deps import get_device_code_service
        from auth.services.device_code import DeviceCodeService

        assert isinstance(get_device_code_service(), DeviceCodeService)

    def test_get_par_service(self):
        from auth.api.deps import get_par_service
        from auth.services.par import PARService

        assert isinstance(get_par_service(), PARService)

    def test_get_jar_service(self):
        from auth.api.deps import get_jar_service
        from auth.services.jar import JARService

        assert isinstance(get_jar_service(), JARService)

    def test_get_token_exchange_service(self):
        from auth.api.deps import get_token_exchange_service
        from auth.services.token_exchange import TokenExchangeService

        assert isinstance(get_token_exchange_service(), TokenExchangeService)

    def test_get_profile_service(self):
        from auth.api.deps import get_profile_service
        from auth.services.profile import ProfileService

        assert isinstance(get_profile_service(), ProfileService)

    def test_get_pat_service(self):
        from auth.api.deps import get_pat_service
        from auth.services.pat import PersonalAccessTokenService

        assert isinstance(get_pat_service(), PersonalAccessTokenService)

    def test_get_trust_service(self):
        from auth.api.deps import get_trust_service
        from auth.services.trust import TrustPolicyService

        assert isinstance(get_trust_service(), TrustPolicyService)

    @patch("auth.api.deps.async_session_factory", new_callable=MagicMock)
    @patch("auth.services.branding.BrandingService")
    def test_get_branding_service(self, mock_branding_cls, mock_factory):
        from auth.api.deps import get_branding_service

        get_branding_service.cache_clear()
        mock_branding_cls.return_value = MagicMock()

        result = get_branding_service()

        mock_branding_cls.assert_called_once()
        assert result is mock_branding_cls.return_value
        get_branding_service.cache_clear()

    def test_get_templates(self):
        from auth.api.deps import get_templates

        get_templates.cache_clear()
        result = get_templates()
        assert result is not None
        get_templates.cache_clear()


# ---------------------------------------------------------------------------
# get_current_user
# ---------------------------------------------------------------------------


class TestGetCurrentUser:
    @pytest.mark.asyncio
    @patch("auth.api.deps.get_session_cookie_name", return_value="session_id")
    async def test_no_cookie_returns_none(self, mock_cookie_name):
        from auth.api.deps import get_current_user

        request = MagicMock()
        request.cookies = {}
        db = AsyncMock()

        result = await get_current_user(request, db)
        assert result is None

    @pytest.mark.asyncio
    @patch("auth.api.deps.get_session_cookie_name", return_value="session_id")
    async def test_no_session_found_returns_none(self, mock_cookie_name):
        from auth.api.deps import get_current_user

        request = MagicMock()
        request.cookies = {"session_id": "raw_token"}
        db = AsyncMock()

        with patch("auth.api.deps.get_session_service") as mock_get_svc:
            svc = MagicMock()
            svc.get_session_with_user_by_token = AsyncMock(return_value=None)
            mock_get_svc.return_value = svc
            result = await get_current_user(request, db)
        assert result is None

    @pytest.mark.asyncio
    @patch("auth.api.deps.get_session_cookie_name", return_value="session_id")
    async def test_expired_session_returns_none(self, mock_cookie_name):
        from auth.api.deps import get_current_user

        session_obj = make_session(
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        request = MagicMock()
        request.cookies = {"session_id": "raw_token"}
        db = AsyncMock()

        with patch("auth.api.deps.get_session_service") as mock_get_svc:
            svc = MagicMock()
            svc.get_session_with_user_by_token = AsyncMock(return_value=session_obj)
            mock_get_svc.return_value = svc
            result = await get_current_user(request, db)
        assert result is None

    @pytest.mark.asyncio
    @patch("auth.api.deps.get_session_cookie_name", return_value="session_id")
    async def test_valid_session_returns_user(self, mock_cookie_name):
        from auth.api.deps import get_current_user

        user = make_user()
        session_obj = make_session(
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        session_obj.user = user

        request = MagicMock()
        request.cookies = {"session_id": "raw_token"}
        db = AsyncMock()

        with patch("auth.api.deps.get_session_service") as mock_get_svc:
            svc = MagicMock()
            svc.get_session_with_user_by_token = AsyncMock(return_value=session_obj)
            mock_get_svc.return_value = svc
            result = await get_current_user(request, db)
        assert result is user


# ---------------------------------------------------------------------------
# get_current_user_with_roles
# ---------------------------------------------------------------------------


class TestGetCurrentUserWithRoles:
    @pytest.mark.asyncio
    @patch("auth.api.deps.get_current_user", new_callable=AsyncMock, return_value=None)
    async def test_no_user_returns_none(self, mock_get_user):
        from auth.api.deps import get_current_user_with_roles

        request = MagicMock()
        db = AsyncMock()

        result = await get_current_user_with_roles(request, db)
        assert result is None

    @pytest.mark.asyncio
    @patch("auth.api.deps.get_current_user", new_callable=AsyncMock)
    async def test_returns_user_and_roles(self, mock_get_user):
        from auth.api.deps import get_current_user_with_roles

        user = make_user()
        mock_get_user.return_value = user

        role1 = MagicMock()
        role2 = MagicMock()

        request = MagicMock()
        db = AsyncMock()

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [role1, role2]
        roles_result = MagicMock()
        roles_result.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=roles_result)

        result = await get_current_user_with_roles(request, db)
        assert result == (user, [role1, role2])


# ---------------------------------------------------------------------------
# validate_bearer_token
# ---------------------------------------------------------------------------


class TestValidateBearerToken:
    @pytest.mark.asyncio
    async def test_no_credentials_returns_none(self):
        from auth.api.deps import validate_bearer_token

        result = await validate_bearer_token(MagicMock(), AsyncMock(), None)
        assert result is None

    @pytest.mark.asyncio
    @patch("auth.api.deps.jwt")
    async def test_decode_error_returns_none(self, mock_jwt):
        import jwt as real_jwt
        from auth.api.deps import validate_bearer_token

        mock_jwt.decode.side_effect = real_jwt.DecodeError("bad")
        mock_jwt.DecodeError = real_jwt.DecodeError

        creds = MagicMock()
        creds.credentials = "invalid.token"

        result = await validate_bearer_token(MagicMock(), AsyncMock(), creds)
        assert result is None

    @pytest.mark.asyncio
    @patch("auth.api.deps.jwt")
    async def test_no_jti_returns_none(self, mock_jwt):
        from auth.api.deps import validate_bearer_token

        mock_jwt.decode.return_value = {"sub": "user1"}  # no jti

        creds = MagicMock()
        creds.credentials = "valid.token"

        result = await validate_bearer_token(MagicMock(), AsyncMock(), creds)
        assert result is None

    @pytest.mark.asyncio
    @patch("auth.api.deps.get_token_service")
    @patch("auth.api.deps.jwt")
    async def test_token_not_in_db_returns_none(self, mock_jwt, mock_token_svc):
        from auth.api.deps import validate_bearer_token

        mock_jwt.decode.return_value = {"jti": "abc123", "sub": "user1"}
        svc = MagicMock()
        svc.get_access_token_by_jti = AsyncMock(return_value=None)
        mock_token_svc.return_value = svc

        creds = MagicMock()
        creds.credentials = "valid.token"

        result = await validate_bearer_token(MagicMock(), AsyncMock(), creds)
        assert result is None

    @pytest.mark.asyncio
    @patch("auth.api.deps.get_token_service")
    @patch("auth.api.deps.jwt")
    async def test_revoked_token_returns_none(self, mock_jwt, mock_token_svc):
        from auth.api.deps import validate_bearer_token

        mock_jwt.decode.return_value = {"jti": "abc123"}
        at = make_access_token(jti="abc123", revoked_at=datetime.now(UTC))
        svc = MagicMock()
        svc.get_access_token_by_jti = AsyncMock(return_value=at)
        mock_token_svc.return_value = svc

        creds = MagicMock()
        creds.credentials = "valid.token"

        result = await validate_bearer_token(MagicMock(), AsyncMock(), creds)
        assert result is None

    @pytest.mark.asyncio
    @patch("auth.api.deps.get_token_service")
    @patch("auth.api.deps.jwt")
    async def test_expired_token_returns_none(self, mock_jwt, mock_token_svc):
        from auth.api.deps import validate_bearer_token

        mock_jwt.decode.return_value = {"jti": "abc123"}
        at = make_access_token(
            jti="abc123",
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        at.revoked_at = None
        svc = MagicMock()
        svc.get_access_token_by_jti = AsyncMock(return_value=at)
        mock_token_svc.return_value = svc

        creds = MagicMock()
        creds.credentials = "valid.token"

        result = await validate_bearer_token(MagicMock(), AsyncMock(), creds)
        assert result is None

    @pytest.mark.asyncio
    @patch("auth.api.deps.get_token_service")
    @patch("auth.api.deps.jwt")
    async def test_valid_token_returns_bearer_auth(self, mock_jwt, mock_token_svc):
        from auth.api.deps import BearerTokenAuth, validate_bearer_token

        mock_jwt.decode.return_value = {
            "jti": "abc123",
            "scope": "users:read users:write",
            "client_id": "my_client",
            "sub": "user_42",
        }
        at = make_access_token(jti="abc123")
        at.revoked_at = None
        at.expires_at = datetime.now(UTC) + timedelta(hours=1)
        svc = MagicMock()
        svc.get_access_token_by_jti = AsyncMock(return_value=at)
        mock_token_svc.return_value = svc

        creds = MagicMock()
        creds.credentials = "valid.token"

        # Mock db for pairwise resolution (returns no client → fallback to raw sub)
        mock_db = AsyncMock()
        mock_client_result = MagicMock()
        mock_client_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_client_result

        result = await validate_bearer_token(MagicMock(), mock_db, creds)
        assert isinstance(result, BearerTokenAuth)
        assert result.client_id == "my_client"
        assert result.scopes == ["users:read", "users:write"]
        assert result.subject == "user_42"

    @pytest.mark.asyncio
    @patch("auth.api.deps.get_token_service")
    @patch("auth.api.deps.jwt")
    async def test_empty_scope_returns_empty_list(self, mock_jwt, mock_token_svc):
        from auth.api.deps import validate_bearer_token

        mock_jwt.decode.return_value = {"jti": "abc123", "scope": ""}
        at = make_access_token(jti="abc123")
        at.revoked_at = None
        at.expires_at = datetime.now(UTC) + timedelta(hours=1)
        svc = MagicMock()
        svc.get_access_token_by_jti = AsyncMock(return_value=at)
        mock_token_svc.return_value = svc

        creds = MagicMock()
        creds.credentials = "valid.token"

        result = await validate_bearer_token(MagicMock(), AsyncMock(), creds)
        assert result.scopes == []


# ---------------------------------------------------------------------------
# validate_pat_token
# ---------------------------------------------------------------------------


class TestValidatePatToken:
    @pytest.mark.asyncio
    async def test_no_credentials_returns_none(self):
        from auth.api.deps import validate_pat_token

        result = await validate_pat_token(MagicMock(), AsyncMock(), None)
        assert result is None

    @pytest.mark.asyncio
    async def test_not_pat_prefix_returns_none(self):
        from auth.api.deps import validate_pat_token

        creds = MagicMock()
        creds.credentials = "Bearer some-jwt-token"

        result = await validate_pat_token(MagicMock(), AsyncMock(), creds)
        assert result is None

    @pytest.mark.asyncio
    @patch("auth.api.deps.get_pat_service")
    async def test_invalid_pat_returns_none(self, mock_pat_svc):
        from auth.api.deps import validate_pat_token
        from auth.services.pat import PAT_PREFIX

        svc = MagicMock()
        svc.validate_token = AsyncMock(return_value=None)
        mock_pat_svc.return_value = svc

        creds = MagicMock()
        creds.credentials = f"{PAT_PREFIX}invalidtoken"

        result = await validate_pat_token(MagicMock(), AsyncMock(), creds)
        assert result is None

    @pytest.mark.asyncio
    @patch("auth.api.deps.get_pat_service")
    async def test_valid_pat_returns_pat_auth(self, mock_pat_svc):
        from auth.api.deps import PATAuth, validate_pat_token
        from auth.services.pat import PAT_PREFIX

        uid = uuid.uuid4()
        pat = make_personal_access_token(
            user_id=uid,
            scopes=["users:read", "users:write"],
        )
        pat.tenant_id = uuid.uuid4()
        pat.target_client_id = uuid.uuid4()

        svc = MagicMock()
        svc.validate_token = AsyncMock(return_value=pat)
        svc.update_token_usage = AsyncMock()
        mock_pat_svc.return_value = svc

        creds = MagicMock()
        creds.credentials = f"{PAT_PREFIX}validtoken"

        request = MagicMock()
        request.client.host = "10.0.0.1"

        result = await validate_pat_token(request, AsyncMock(), creds)
        assert isinstance(result, PATAuth)
        assert result.user_id == str(uid)
        assert result.pat_id == str(pat.id)
        assert result.scopes == ["users:read", "users:write"]
        assert result.tenant_id == str(pat.tenant_id)
        assert result.target_client_id == str(pat.target_client_id)
        svc.update_token_usage.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("auth.api.deps.get_pat_service")
    async def test_valid_pat_no_client_ip(self, mock_pat_svc):
        from auth.api.deps import validate_pat_token
        from auth.services.pat import PAT_PREFIX

        pat = make_personal_access_token()
        pat.tenant_id = None
        pat.target_client_id = None

        svc = MagicMock()
        svc.validate_token = AsyncMock(return_value=pat)
        svc.update_token_usage = AsyncMock()
        mock_pat_svc.return_value = svc

        creds = MagicMock()
        creds.credentials = f"{PAT_PREFIX}validtoken"

        request = MagicMock()
        request.client = None

        result = await validate_pat_token(request, AsyncMock(), creds)
        assert result is not None
        assert result.tenant_id is None
        assert result.target_client_id is None
        svc.update_token_usage.assert_awaited_once_with(
            svc.update_token_usage.call_args[0][0],
            pat,
            None,
        )


# ---------------------------------------------------------------------------
# token_has_scope
# ---------------------------------------------------------------------------


class TestTokenHasScope:
    def test_exact_match(self):
        from auth.api.deps import token_has_scope

        assert token_has_scope(["users:read", "users:write"], "users:read") is True

    def test_no_match(self):
        from auth.api.deps import token_has_scope

        assert token_has_scope(["users:read"], "users:write") is False

    def test_wildcard_match(self):
        from auth.api.deps import token_has_scope

        assert token_has_scope(["users:*"], "users:read") is True
        assert token_has_scope(["users:*"], "users:write") is True

    def test_wildcard_no_match_different_prefix(self):
        from auth.api.deps import token_has_scope

        assert token_has_scope(["users:*"], "clients:read") is False

    def test_global_wildcard(self):
        from auth.api.deps import token_has_scope

        assert token_has_scope(["*"], "anything:here") is True

    def test_empty_scopes(self):
        from auth.api.deps import token_has_scope

        assert token_has_scope([], "users:read") is False


# ---------------------------------------------------------------------------
# user_has_scope
# ---------------------------------------------------------------------------


class TestUserHasScope:
    def test_role_has_scope(self):
        from auth.api.deps import user_has_scope

        role = MagicMock()
        role.has_scope.return_value = True

        assert user_has_scope([role], "users:read") is True
        role.has_scope.assert_called_with("users:read")

    def test_no_role_has_scope(self):
        from auth.api.deps import user_has_scope

        role = MagicMock()
        role.has_scope.return_value = False

        assert user_has_scope([role], "users:read") is False

    def test_empty_roles(self):
        from auth.api.deps import user_has_scope

        assert user_has_scope([], "users:read") is False

    def test_multiple_roles_second_matches(self):
        from auth.api.deps import user_has_scope

        role1 = MagicMock()
        role1.has_scope.return_value = False
        role2 = MagicMock()
        role2.has_scope.return_value = True

        assert user_has_scope([role1, role2], "users:read") is True


# ---------------------------------------------------------------------------
# require_scope
# ---------------------------------------------------------------------------


class TestRequireScope:
    """Tests for require_scope dependency factory."""

    @pytest.mark.asyncio
    @patch("auth.api.deps.validate_pat_token", new_callable=AsyncMock)
    async def test_pat_auth_with_scope(self, mock_validate_pat):
        from auth.api.deps import PATAuth, require_scope
        from auth.services.pat import PAT_PREFIX

        pat_auth = PATAuth(user_id="u1", pat_id="p1", scopes=["users:read"])
        mock_validate_pat.return_value = pat_auth

        dep = require_scope("users:read")
        request = MagicMock()
        db = AsyncMock()
        creds = MagicMock()
        creds.credentials = f"{PAT_PREFIX}token"

        result = await dep(request, db, creds)
        assert result is pat_auth

    @pytest.mark.asyncio
    @patch("auth.api.deps.validate_pat_token", new_callable=AsyncMock)
    async def test_pat_auth_missing_scope_raises_403(self, mock_validate_pat):
        from auth.api.deps import PATAuth, require_scope
        from auth.services.pat import PAT_PREFIX

        pat_auth = PATAuth(user_id="u1", pat_id="p1", scopes=["users:read"])
        mock_validate_pat.return_value = pat_auth

        dep = require_scope("users:write")
        request = MagicMock()
        db = AsyncMock()
        creds = MagicMock()
        creds.credentials = f"{PAT_PREFIX}token"

        with pytest.raises(HTTPException) as exc_info:
            await dep(request, db, creds)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @patch("auth.api.deps.validate_pat_token", new_callable=AsyncMock)
    async def test_pat_prefix_but_invalid_raises_401(self, mock_validate_pat):
        from auth.api.deps import require_scope
        from auth.services.pat import PAT_PREFIX

        mock_validate_pat.return_value = None

        dep = require_scope("users:read")
        request = MagicMock()
        db = AsyncMock()
        creds = MagicMock()
        creds.credentials = f"{PAT_PREFIX}badtoken"

        with pytest.raises(HTTPException) as exc_info:
            await dep(request, db, creds)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch("auth.api.deps.validate_bearer_token", new_callable=AsyncMock)
    async def test_bearer_auth_with_scope(self, mock_validate_bearer):
        from auth.api.deps import BearerTokenAuth, require_scope

        bearer_auth = BearerTokenAuth(client_id="c1", scopes=["users:read"])
        mock_validate_bearer.return_value = bearer_auth

        dep = require_scope("users:read")
        request = MagicMock()
        db = AsyncMock()
        creds = MagicMock()
        creds.credentials = "jwt.token.here"

        result = await dep(request, db, creds)
        assert result is bearer_auth

    @pytest.mark.asyncio
    @patch("auth.api.deps.validate_bearer_token", new_callable=AsyncMock)
    async def test_bearer_auth_missing_scope_raises_403(self, mock_validate_bearer):
        from auth.api.deps import BearerTokenAuth, require_scope

        bearer_auth = BearerTokenAuth(client_id="c1", scopes=["users:read"])
        mock_validate_bearer.return_value = bearer_auth

        dep = require_scope("users:write")
        request = MagicMock()
        db = AsyncMock()
        creds = MagicMock()
        creds.credentials = "jwt.token.here"

        with pytest.raises(HTTPException) as exc_info:
            await dep(request, db, creds)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @patch("auth.api.deps.get_current_user_with_roles", new_callable=AsyncMock)
    @patch("auth.api.deps.validate_bearer_token", new_callable=AsyncMock)
    async def test_session_auth_with_scope(self, mock_bearer, mock_user_roles):
        from auth.api.deps import require_scope

        mock_bearer.return_value = None

        user = make_user()
        role = MagicMock()
        role.has_scope.return_value = True
        mock_user_roles.return_value = (user, [role])

        dep = require_scope("users:read")
        request = MagicMock()
        db = AsyncMock()

        result = await dep(request, db, None)
        assert result == (user, [role])

    @pytest.mark.asyncio
    @patch("auth.api.deps.get_current_user_with_roles", new_callable=AsyncMock)
    @patch("auth.api.deps.validate_bearer_token", new_callable=AsyncMock)
    async def test_no_auth_raises_401(self, mock_bearer, mock_user_roles):
        from auth.api.deps import require_scope

        mock_bearer.return_value = None
        mock_user_roles.return_value = None

        dep = require_scope("users:read")
        request = MagicMock()
        db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await dep(request, db, None)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch("auth.api.deps.get_current_user_with_roles", new_callable=AsyncMock)
    @patch("auth.api.deps.validate_bearer_token", new_callable=AsyncMock)
    async def test_no_auth_redirect_to_login(self, mock_bearer, mock_user_roles):
        from auth.api.deps import require_scope

        mock_bearer.return_value = None
        mock_user_roles.return_value = None

        dep = require_scope("users:read", redirect_to_login=True)
        request = MagicMock()
        request.url = "https://example.com/admin"
        db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await dep(request, db, None)
        assert exc_info.value.status_code == 303
        assert "/auth/login" in exc_info.value.headers["Location"]

    @pytest.mark.asyncio
    @patch("auth.api.deps.get_current_user_with_roles", new_callable=AsyncMock)
    @patch("auth.api.deps.validate_bearer_token", new_callable=AsyncMock)
    async def test_inactive_user_raises_403(self, mock_bearer, mock_user_roles):
        from auth.api.deps import require_scope

        mock_bearer.return_value = None
        user = make_user(is_active=False)
        role = MagicMock()
        mock_user_roles.return_value = (user, [role])

        dep = require_scope("users:read")
        request = MagicMock()
        db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await dep(request, db, None)
        assert exc_info.value.status_code == 403
        assert "disabled" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    @patch("auth.api.deps.get_current_user_with_roles", new_callable=AsyncMock)
    @patch("auth.api.deps.validate_bearer_token", new_callable=AsyncMock)
    async def test_user_missing_scope_raises_403(self, mock_bearer, mock_user_roles):
        from auth.api.deps import require_scope

        mock_bearer.return_value = None
        user = make_user()
        role = MagicMock()
        role.has_scope.return_value = False
        mock_user_roles.return_value = (user, [role])

        dep = require_scope("users:write")
        request = MagicMock()
        db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await dep(request, db, None)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @patch("auth.api.deps.validate_bearer_token", new_callable=AsyncMock)
    async def test_bearer_invalid_falls_through_to_session(self, mock_bearer):
        """When bearer returns None (non-PAT creds), fall through to session."""
        from auth.api.deps import require_scope

        mock_bearer.return_value = None

        dep = require_scope("users:read")
        request = MagicMock()
        db = AsyncMock()
        creds = MagicMock()
        creds.credentials = "bad.jwt"

        # No session either
        with patch(
            "auth.api.deps.get_current_user_with_roles",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await dep(request, db, creds)
            assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# require_any_scope
# ---------------------------------------------------------------------------


class TestRequireAnyScope:
    """Tests for require_any_scope dependency factory."""

    @pytest.mark.asyncio
    @patch("auth.api.deps.validate_pat_token", new_callable=AsyncMock)
    async def test_pat_has_any_scope(self, mock_validate_pat):
        from auth.api.deps import PATAuth, require_any_scope
        from auth.services.pat import PAT_PREFIX

        pat_auth = PATAuth(user_id="u1", pat_id="p1", scopes=["users:write"])
        mock_validate_pat.return_value = pat_auth

        dep = require_any_scope("users:read", "users:write")
        request = MagicMock()
        db = AsyncMock()
        creds = MagicMock()
        creds.credentials = f"{PAT_PREFIX}token"

        result = await dep(request, db, creds)
        assert result is pat_auth

    @pytest.mark.asyncio
    @patch("auth.api.deps.validate_pat_token", new_callable=AsyncMock)
    async def test_pat_missing_all_scopes_raises_403(self, mock_validate_pat):
        from auth.api.deps import PATAuth, require_any_scope
        from auth.services.pat import PAT_PREFIX

        pat_auth = PATAuth(user_id="u1", pat_id="p1", scopes=["clients:read"])
        mock_validate_pat.return_value = pat_auth

        dep = require_any_scope("users:read", "users:write")
        request = MagicMock()
        db = AsyncMock()
        creds = MagicMock()
        creds.credentials = f"{PAT_PREFIX}token"

        with pytest.raises(HTTPException) as exc_info:
            await dep(request, db, creds)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @patch("auth.api.deps.validate_pat_token", new_callable=AsyncMock)
    async def test_pat_prefix_invalid_raises_401(self, mock_validate_pat):
        from auth.api.deps import require_any_scope
        from auth.services.pat import PAT_PREFIX

        mock_validate_pat.return_value = None

        dep = require_any_scope("users:read", "users:write")
        request = MagicMock()
        db = AsyncMock()
        creds = MagicMock()
        creds.credentials = f"{PAT_PREFIX}bad"

        with pytest.raises(HTTPException) as exc_info:
            await dep(request, db, creds)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch("auth.api.deps.validate_bearer_token", new_callable=AsyncMock)
    async def test_bearer_has_any_scope(self, mock_bearer):
        from auth.api.deps import BearerTokenAuth, require_any_scope

        bearer_auth = BearerTokenAuth(client_id="c1", scopes=["users:write"])
        mock_bearer.return_value = bearer_auth

        dep = require_any_scope("users:read", "users:write")
        request = MagicMock()
        db = AsyncMock()
        creds = MagicMock()
        creds.credentials = "jwt.token"

        result = await dep(request, db, creds)
        assert result is bearer_auth

    @pytest.mark.asyncio
    @patch("auth.api.deps.validate_bearer_token", new_callable=AsyncMock)
    async def test_bearer_missing_all_scopes_raises_403(self, mock_bearer):
        from auth.api.deps import BearerTokenAuth, require_any_scope

        bearer_auth = BearerTokenAuth(client_id="c1", scopes=["clients:read"])
        mock_bearer.return_value = bearer_auth

        dep = require_any_scope("users:read", "users:write")
        request = MagicMock()
        db = AsyncMock()
        creds = MagicMock()
        creds.credentials = "jwt.token"

        with pytest.raises(HTTPException) as exc_info:
            await dep(request, db, creds)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @patch("auth.api.deps.get_current_user_with_roles", new_callable=AsyncMock)
    @patch("auth.api.deps.validate_bearer_token", new_callable=AsyncMock)
    async def test_session_user_has_any_scope(self, mock_bearer, mock_user_roles):
        from auth.api.deps import require_any_scope

        mock_bearer.return_value = None
        user = make_user()
        role = MagicMock()
        # has_scope returns True for "users:write" only
        role.has_scope.side_effect = lambda s: s == "users:write"
        mock_user_roles.return_value = (user, [role])

        dep = require_any_scope("users:read", "users:write")
        request = MagicMock()
        db = AsyncMock()

        result = await dep(request, db, None)
        assert result == (user, [role])

    @pytest.mark.asyncio
    @patch("auth.api.deps.get_current_user_with_roles", new_callable=AsyncMock)
    @patch("auth.api.deps.validate_bearer_token", new_callable=AsyncMock)
    async def test_session_user_missing_all_scopes_raises_403(self, mock_bearer, mock_user_roles):
        from auth.api.deps import require_any_scope

        mock_bearer.return_value = None
        user = make_user()
        role = MagicMock()
        role.has_scope.return_value = False
        mock_user_roles.return_value = (user, [role])

        dep = require_any_scope("users:read", "users:write")
        request = MagicMock()
        db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await dep(request, db, None)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @patch("auth.api.deps.get_current_user_with_roles", new_callable=AsyncMock)
    @patch("auth.api.deps.validate_bearer_token", new_callable=AsyncMock)
    async def test_no_auth_raises_401(self, mock_bearer, mock_user_roles):
        from auth.api.deps import require_any_scope

        mock_bearer.return_value = None
        mock_user_roles.return_value = None

        dep = require_any_scope("users:read", "users:write")
        request = MagicMock()
        db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await dep(request, db, None)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch("auth.api.deps.get_current_user_with_roles", new_callable=AsyncMock)
    @patch("auth.api.deps.validate_bearer_token", new_callable=AsyncMock)
    async def test_no_auth_redirect_to_login(self, mock_bearer, mock_user_roles):
        from auth.api.deps import require_any_scope

        mock_bearer.return_value = None
        mock_user_roles.return_value = None

        dep = require_any_scope("users:read", "users:write", redirect_to_login=True)
        request = MagicMock()
        request.url = "https://example.com/admin"
        db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await dep(request, db, None)
        assert exc_info.value.status_code == 303
        assert "/auth/login" in exc_info.value.headers["Location"]

    @pytest.mark.asyncio
    @patch("auth.api.deps.get_current_user_with_roles", new_callable=AsyncMock)
    @patch("auth.api.deps.validate_bearer_token", new_callable=AsyncMock)
    async def test_inactive_user_raises_403(self, mock_bearer, mock_user_roles):
        from auth.api.deps import require_any_scope

        mock_bearer.return_value = None
        user = make_user(is_active=False)
        role = MagicMock()
        mock_user_roles.return_value = (user, [role])

        dep = require_any_scope("users:read", "users:write")
        request = MagicMock()
        db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await dep(request, db, None)
        assert exc_info.value.status_code == 403
        assert "disabled" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# get_user_admin_permissions
# ---------------------------------------------------------------------------


class TestGetUserAdminPermissions:
    def test_no_roles_all_false(self):
        from auth.api.deps import get_user_admin_permissions

        perms = get_user_admin_permissions([])

        assert perms["can_view_dashboard"] is False
        assert perms["can_view_users"] is False
        assert perms["users:read"] is False
        assert perms["users:write"] is False

    def test_admin_with_all_scopes(self):
        from auth.api.deps import get_user_admin_permissions

        role = MagicMock()
        role.has_scope.return_value = True

        perms = get_user_admin_permissions([role])

        assert perms["can_view_dashboard"] is True
        assert perms["can_view_users"] is True
        assert perms["can_view_clients"] is True
        assert perms["can_view_sessions"] is True
        assert perms["can_view_jwks"] is True
        assert perms["can_view_roles"] is True
        assert perms["can_view_scopes"] is True
        assert perms["can_view_orgs"] is True
        assert perms["can_view_pats"] is True
        assert perms["users:read"] is True
        assert perms["users:write"] is True
        assert perms["users:delete"] is True
        assert perms["users:disable"] is True
        assert perms["clients:read"] is True
        assert perms["clients:write"] is True
        assert perms["clients:delete"] is True
        assert perms["clients:rotate"] is True
        assert perms["sessions:read"] is True
        assert perms["sessions:revoke"] is True
        assert perms["roles:read"] is True
        assert perms["roles:write"] is True
        assert perms["roles:delete"] is True
        assert perms["roles:assign"] is True
        assert perms["scopes:read"] is True
        assert perms["scopes:write"] is True
        assert perms["scopes:delete"] is True
        assert perms["jwks:read"] is True
        assert perms["jwks:write"] is True
        assert perms["jwks:delete"] is True
        assert perms["jwks:revoke"] is True
        assert perms["jwks:rotate"] is True
        assert perms["org:read"] is True
        assert perms["org:write"] is True
        assert perms["org:delete"] is True
        assert perms["pats:read"] is True
        assert perms["pats:revoke"] is True

    def test_partial_scopes(self):
        from auth.api.deps import get_user_admin_permissions

        role = MagicMock()
        # Only users:read scope
        role.has_scope.side_effect = lambda s: s == "users:read"

        perms = get_user_admin_permissions([role])

        assert perms["can_view_dashboard"] is True  # users:read is in the dashboard check
        assert perms["can_view_users"] is True
        assert perms["users:read"] is True
        assert perms["users:write"] is False
        assert perms["can_view_clients"] is False
        assert perms["clients:read"] is False


class TestServiceFactoriesExtra:
    """Coverage for service factories not exercised elsewhere."""

    def test_get_pairwise_service(self):
        from auth.api.deps import get_pairwise_service
        from auth.services.pairwise import PairwiseSubjectService

        assert isinstance(get_pairwise_service(), PairwiseSubjectService)


class TestRequireAnyScopeBearerFallthrough:
    """Bearer credentials that fail validation fall back to session cookie auth."""

    @pytest.mark.asyncio
    @patch("auth.api.deps.get_current_user_with_roles", new_callable=AsyncMock)
    @patch("auth.api.deps.validate_bearer_token", new_callable=AsyncMock)
    async def test_invalid_bearer_falls_back_to_session(self, mock_bearer, mock_session_user):
        from auth.api.deps import require_any_scope

        mock_bearer.return_value = None
        user = make_user()
        role = MagicMock()
        role.has_scope.side_effect = lambda s: s == "users:read"
        mock_session_user.return_value = (user, [role])

        dep = require_any_scope("users:read")
        request = MagicMock()
        db = AsyncMock()
        creds = MagicMock()
        creds.credentials = "not.a.pat"

        result = await dep(request, db, creds)
        assert result[0] is user
        mock_bearer.assert_awaited_once()
        mock_session_user.assert_awaited_once()
