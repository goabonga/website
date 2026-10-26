# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for pairwise subject identifier integration in token creation and validation."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.services.token import TokenService

from tests.conftest import (
    make_access_token,
    make_execute_result,
    make_jwk,
    make_oauth2_client,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def jwks_service():
    svc = MagicMock()
    svc.get_active_key = AsyncMock()
    svc.get_key_by_kid = AsyncMock()
    svc.decrypt_private_key = MagicMock()
    return svc


@pytest.fixture
def token_service(jwks_service):
    return TokenService(jwks_service)


# ---------------------------------------------------------------------------
# create_access_token — pairwise sub
# ---------------------------------------------------------------------------


class TestCreateAccessTokenPairwise:
    @pytest.mark.asyncio
    @patch("auth.services.token.settings")
    @patch("auth.services.token.PairwiseSubjectService")
    async def test_uses_pairwise_sub(
        self, mock_pairwise_cls, mock_settings, db, token_service, jwks_service
    ):
        """When user_id is set, sub should be pairwise."""
        mock_settings.access_token_expiry_minutes = 60
        mock_settings.issuer = "https://auth.example.com"

        pairwise_sub = str(uuid.uuid4())
        mock_pairwise = MagicMock()
        mock_pairwise.get_sub_for_client = AsyncMock(return_value=pairwise_sub)
        mock_pairwise_cls.return_value = mock_pairwise

        jwk = make_jwk()
        jwks_service.get_active_key.return_value = jwk
        jwks_service.decrypt_private_key.return_value = MagicMock()

        client = make_oauth2_client()
        user_id = uuid.uuid4()

        with patch("auth.services.token.jwt") as mock_jwt:
            mock_jwt.encode.return_value = "jwt_pairwise"
            jwt_str, at = await token_service.create_access_token(
                db, client, ["openid"], user_id=user_id
            )

        # Verify pairwise service was called
        mock_pairwise.get_sub_for_client.assert_awaited_once_with(db, user_id, client)

        # Verify the JWT payload uses the pairwise sub
        call_args = mock_jwt.encode.call_args[0][0]
        assert call_args["sub"] == pairwise_sub

    @pytest.mark.asyncio
    @patch("auth.services.token.settings")
    async def test_client_credentials_uses_client_id(
        self, mock_settings, db, token_service, jwks_service
    ):
        """Client credentials flow (user_id=None) uses client_id."""
        mock_settings.access_token_expiry_minutes = 60
        mock_settings.issuer = "https://auth.example.com"

        jwk = make_jwk()
        jwks_service.get_active_key.return_value = jwk
        jwks_service.decrypt_private_key.return_value = MagicMock()

        client = make_oauth2_client(client_id="machine_client")

        with patch("auth.services.token.jwt") as mock_jwt:
            mock_jwt.encode.return_value = "jwt_cc"
            await token_service.create_access_token(db, client, ["openid"], user_id=None)

        call_args = mock_jwt.encode.call_args[0][0]
        assert call_args["sub"] == "machine_client"


# ---------------------------------------------------------------------------
# create_id_token — pairwise sub
# ---------------------------------------------------------------------------


class TestCreateIdTokenPairwise:
    @pytest.mark.asyncio
    @patch("auth.services.token.settings")
    @patch("auth.services.token.PairwiseSubjectService")
    async def test_uses_pairwise_sub(
        self, mock_pairwise_cls, mock_settings, db, token_service, jwks_service
    ):
        """ID token should use pairwise sub."""
        mock_settings.id_token_expiry_minutes = 60
        mock_settings.issuer = "https://auth.example.com"

        pairwise_sub = str(uuid.uuid4())
        mock_pairwise = MagicMock()
        mock_pairwise.get_sub_for_client = AsyncMock(return_value=pairwise_sub)
        mock_pairwise_cls.return_value = mock_pairwise

        jwk = make_jwk()
        jwks_service.get_active_key.return_value = jwk
        jwks_service.decrypt_private_key.return_value = MagicMock()

        client = make_oauth2_client()
        user_id = uuid.uuid4()

        with patch("auth.services.token.jwt") as mock_jwt:
            mock_jwt.encode.return_value = "id_token_pairwise"
            await token_service.create_id_token(db, client, user_id)

        call_args = mock_jwt.encode.call_args[0][0]
        assert call_args["sub"] == pairwise_sub
        mock_pairwise.get_sub_for_client.assert_awaited_once_with(db, user_id, client)


# ---------------------------------------------------------------------------
# validate_bearer_token — pairwise resolution
# ---------------------------------------------------------------------------


class TestValidateBearerTokenPairwise:
    @pytest.mark.asyncio
    @patch("auth.api.deps.get_pairwise_service")
    @patch("auth.api.deps.get_token_service")
    @patch("auth.api.deps.jwt")
    async def test_resolves_pairwise_sub_to_real_user_id(
        self, mock_jwt, mock_token_svc, mock_pairwise_svc_fn
    ):
        """The returned subject should be the real user_id resolved from pairwise."""
        from auth.api.deps import BearerTokenAuth, validate_bearer_token

        real_user_id = uuid.uuid4()
        pairwise_sub = str(uuid.uuid4())

        mock_jwt.decode.return_value = {
            "jti": "jti123",
            "scope": "openid",
            "client_id": "my_client",
            "sub": pairwise_sub,
        }

        at = make_access_token(jti="jti123")
        at.revoked_at = None
        at.expires_at = datetime.now(UTC) + timedelta(hours=1)
        svc = MagicMock()
        svc.get_access_token_by_jti = AsyncMock(return_value=at)
        mock_token_svc.return_value = svc

        # Mock the client lookup in _resolve_pairwise_subject
        mock_client = make_oauth2_client(client_id="my_client")
        mock_client.tenant_id = uuid.uuid4()

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mock_client))

        # Mock pairwise service resolution
        mock_pairwise = MagicMock()
        mock_pairwise.resolve_user_id_for_client = AsyncMock(return_value=real_user_id)
        mock_pairwise_svc_fn.return_value = mock_pairwise

        creds = MagicMock()
        creds.credentials = "valid.token"

        result = await validate_bearer_token(MagicMock(), mock_db, creds)

        assert isinstance(result, BearerTokenAuth)
        assert result.subject == str(real_user_id)
        mock_pairwise.resolve_user_id_for_client.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("auth.api.deps.get_pairwise_service")
    @patch("auth.api.deps.get_token_service")
    @patch("auth.api.deps.jwt")
    async def test_falls_back_to_raw_sub_for_old_tokens(
        self, mock_jwt, mock_token_svc, mock_pairwise_svc_fn
    ):
        """When pairwise resolution fails, fall back to the raw sub (backward compat)."""
        from auth.api.deps import BearerTokenAuth, validate_bearer_token

        raw_user_id = str(uuid.uuid4())

        mock_jwt.decode.return_value = {
            "jti": "jti456",
            "scope": "openid",
            "client_id": "my_client",
            "sub": raw_user_id,
        }

        at = make_access_token(jti="jti456")
        at.revoked_at = None
        at.expires_at = datetime.now(UTC) + timedelta(hours=1)
        svc = MagicMock()
        svc.get_access_token_by_jti = AsyncMock(return_value=at)
        mock_token_svc.return_value = svc

        # Mock client lookup
        mock_client = make_oauth2_client(client_id="my_client")
        mock_client.tenant_id = uuid.uuid4()

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=make_execute_result(scalar_value=mock_client))

        # Pairwise resolution returns None (old token, sub is raw user_id)
        mock_pairwise = MagicMock()
        mock_pairwise.resolve_user_id_for_client = AsyncMock(return_value=None)
        mock_pairwise_svc_fn.return_value = mock_pairwise

        creds = MagicMock()
        creds.credentials = "valid.token"

        result = await validate_bearer_token(MagicMock(), mock_db, creds)

        assert isinstance(result, BearerTokenAuth)
        # Falls back to the raw sub value
        assert result.subject == raw_user_id

    @pytest.mark.asyncio
    @patch("auth.api.deps.get_token_service")
    @patch("auth.api.deps.jwt")
    async def test_skips_resolution_when_no_subject(self, mock_jwt, mock_token_svc):
        """Client credentials tokens (no sub) should not trigger pairwise resolution."""
        from auth.api.deps import BearerTokenAuth, validate_bearer_token

        mock_jwt.decode.return_value = {
            "jti": "jti_cc",
            "scope": "openid",
            "client_id": "machine_client",
            # No "sub" key
        }

        at = make_access_token(jti="jti_cc")
        at.revoked_at = None
        at.expires_at = datetime.now(UTC) + timedelta(hours=1)
        svc = MagicMock()
        svc.get_access_token_by_jti = AsyncMock(return_value=at)
        mock_token_svc.return_value = svc

        creds = MagicMock()
        creds.credentials = "valid.token"

        result = await validate_bearer_token(MagicMock(), AsyncMock(), creds)

        assert isinstance(result, BearerTokenAuth)
        assert result.subject is None


# ---------------------------------------------------------------------------
# _resolve_pairwise_subject — edge cases
# ---------------------------------------------------------------------------


class TestResolvePairwiseSubject:
    @pytest.mark.asyncio
    async def test_client_not_found_returns_raw_subject(self):
        """When client lookup fails, return the original subject."""
        from auth.api.deps import _resolve_pairwise_subject

        pairwise_sub = str(uuid.uuid4())
        at = make_access_token()

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await _resolve_pairwise_subject(mock_db, pairwise_sub, at)
        assert result == pairwise_sub


# ---------------------------------------------------------------------------
# get_current_user_bearer — pairwise_sub on request.state
# ---------------------------------------------------------------------------
