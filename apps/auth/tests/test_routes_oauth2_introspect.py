# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.api.routes.oauth2.introspect -- Token introspection endpoint (RFC 7662)."""

import base64
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from tests.conftest import (
    make_access_token,
    make_oauth2_client,
    make_personal_access_token,
    make_refresh_token,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MODULE = "auth.api.routes.oauth2.introspect"


def _basic_auth(client_id: str, client_secret: str) -> str:
    encoded = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    return f"Basic {encoded}"


# ---------------------------------------------------------------------------
# _parse_basic_auth
# ---------------------------------------------------------------------------


class TestParseBasicAuth:
    def test_none(self):
        from auth.api.routes.oauth2.introspect import _parse_basic_auth

        assert _parse_basic_auth(None) == (None, None)

    def test_non_basic(self):
        from auth.api.routes.oauth2.introspect import _parse_basic_auth

        assert _parse_basic_auth("Bearer token") == (None, None)

    def test_valid_basic(self):
        from auth.api.routes.oauth2.introspect import _parse_basic_auth

        header = _basic_auth("my_client", "my_secret")
        cid, cs = _parse_basic_auth(header)
        assert cid == "my_client"
        assert cs == "my_secret"

    def test_invalid_base64(self):
        from auth.api.routes.oauth2.introspect import _parse_basic_auth

        assert _parse_basic_auth("Basic !!!invalid!!!") == (None, None)

    def test_missing_colon(self):
        from auth.api.routes.oauth2.introspect import _parse_basic_auth

        encoded = base64.b64encode(b"nocolon").decode()
        assert _parse_basic_auth(f"Basic {encoded}") == (None, None)


# ---------------------------------------------------------------------------
# IntrospectionResponse model
# ---------------------------------------------------------------------------


class TestIntrospectionResponse:
    def test_inactive_response(self):
        from auth.api.routes.oauth2.introspect import IntrospectionResponse

        resp = IntrospectionResponse(active=False)
        assert resp.active is False
        assert resp.scope is None

    def test_active_response(self):
        from auth.api.routes.oauth2.introspect import IntrospectionResponse

        resp = IntrospectionResponse(
            active=True,
            scope="openid profile",
            client_id="c1",
            token_type="Bearer",
            sub="user-123",
        )
        assert resp.active is True
        assert resp.scope == "openid profile"


# ---------------------------------------------------------------------------
# introspect_token endpoint
# ---------------------------------------------------------------------------


class TestIntrospectToken:
    @pytest.mark.asyncio
    async def test_no_client_id_raises_401(self):
        from auth.api.routes.oauth2.introspect import introspect_token

        with pytest.raises(HTTPException) as exc_info:
            await introspect_token(
                token="some_token",
                db=AsyncMock(),
                oauth2_service=AsyncMock(),
                token_service=AsyncMock(),
                pat_service=AsyncMock(),
                authorization=None,
                client_id=None,
                client_secret=None,
                token_type_hint=None,
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_client_raises_401(self):
        from auth.api.routes.oauth2.introspect import introspect_token

        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await introspect_token(
                token="some_token",
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                token_service=AsyncMock(),
                pat_service=AsyncMock(),
                authorization=None,
                client_id="bad_client",
                client_secret=None,
                token_type_hint=None,
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_inactive_client_raises_401(self):
        from auth.api.routes.oauth2.introspect import introspect_token

        client = make_oauth2_client()
        client.is_active = False
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)

        with pytest.raises(HTTPException) as exc_info:
            await introspect_token(
                token="some_token",
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                token_service=AsyncMock(),
                pat_service=AsyncMock(),
                authorization=None,
                client_id="test_client_id",
                client_secret=None,
                token_type_hint=None,
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_confidential_client_missing_secret_raises_401(self):
        from auth.api.routes.oauth2.introspect import introspect_token

        client = make_oauth2_client(is_confidential=True)
        client.is_active = True
        client.allowed_scopes = ["introspect"]
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)

        with pytest.raises(HTTPException) as exc_info:
            await introspect_token(
                token="some_token",
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                token_service=AsyncMock(),
                pat_service=AsyncMock(),
                authorization=None,
                client_id="test_client_id",
                client_secret=None,
                token_type_hint=None,
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_confidential_client_wrong_secret_raises_401(self):
        from auth.api.routes.oauth2.introspect import introspect_token

        client = make_oauth2_client(is_confidential=True)
        client.is_active = True
        client.allowed_scopes = ["introspect"]
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.verify_client_secret = MagicMock(return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            await introspect_token(
                token="some_token",
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                token_service=AsyncMock(),
                pat_service=AsyncMock(),
                authorization=None,
                client_id="test_client_id",
                client_secret="wrong_secret",
                token_type_hint=None,
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_client_missing_introspect_scope_raises_403(self):
        from auth.api.routes.oauth2.introspect import introspect_token

        client = make_oauth2_client(is_confidential=False, allowed_scopes=["openid"])
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)

        with pytest.raises(HTTPException) as exc_info:
            await introspect_token(
                token="some_token",
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                token_service=AsyncMock(),
                pat_service=AsyncMock(),
                authorization=None,
                client_id="test_client_id",
                client_secret=None,
                token_type_hint=None,
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @patch(f"{MODULE}._introspect_access_token")
    async def test_default_tries_access_token_first(self, mock_introspect_at):
        from auth.api.routes.oauth2.introspect import IntrospectionResponse, introspect_token

        client = make_oauth2_client(is_confidential=False, allowed_scopes=["introspect"])
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)

        active_resp = IntrospectionResponse(active=True, scope="openid", token_type="Bearer")
        mock_introspect_at.return_value = active_resp

        result = await introspect_token(
            token="jwt_token",
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            token_service=AsyncMock(),
            pat_service=AsyncMock(),
            authorization=None,
            client_id="test_client_id",
            client_secret=None,
            token_type_hint=None,
        )

        assert result.active is True
        mock_introspect_at.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(f"{MODULE}._introspect_refresh_token")
    @patch(f"{MODULE}._introspect_access_token")
    async def test_default_falls_through_to_refresh(self, mock_at, mock_rt):
        from auth.api.routes.oauth2.introspect import IntrospectionResponse, introspect_token

        client = make_oauth2_client(is_confidential=False, allowed_scopes=["introspect"])
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)

        mock_at.return_value = IntrospectionResponse(active=False)
        mock_rt.return_value = IntrospectionResponse(active=True, token_type="refresh_token")

        result = await introspect_token(
            token="refresh_token_value",
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            token_service=AsyncMock(),
            pat_service=AsyncMock(),
            authorization=None,
            client_id="test_client_id",
            client_secret=None,
            token_type_hint=None,
        )

        assert result.active is True
        assert result.token_type == "refresh_token"

    @pytest.mark.asyncio
    @patch(f"{MODULE}._introspect_refresh_token")
    @patch(f"{MODULE}._introspect_access_token")
    async def test_default_both_inactive(self, mock_at, mock_rt):
        from auth.api.routes.oauth2.introspect import IntrospectionResponse, introspect_token

        client = make_oauth2_client(is_confidential=False, allowed_scopes=["introspect"])
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)

        mock_at.return_value = IntrospectionResponse(active=False)
        mock_rt.return_value = None

        result = await introspect_token(
            token="bad_token",
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            token_service=AsyncMock(),
            pat_service=AsyncMock(),
            authorization=None,
            client_id="test_client_id",
            client_secret=None,
            token_type_hint=None,
        )

        assert result.active is False

    @pytest.mark.asyncio
    @patch(f"{MODULE}._introspect_refresh_token")
    async def test_hint_refresh_token_found(self, mock_rt):
        from auth.api.routes.oauth2.introspect import IntrospectionResponse, introspect_token

        client = make_oauth2_client(is_confidential=False, allowed_scopes=["introspect"])
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)

        mock_rt.return_value = IntrospectionResponse(active=True, token_type="refresh_token")

        result = await introspect_token(
            token="rt_value",
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            token_service=AsyncMock(),
            pat_service=AsyncMock(),
            authorization=None,
            client_id="test_client_id",
            client_secret=None,
            token_type_hint="refresh_token",
        )

        assert result.active is True

    @pytest.mark.asyncio
    @patch(f"{MODULE}._introspect_access_token")
    @patch(f"{MODULE}._introspect_refresh_token")
    async def test_hint_refresh_not_found_falls_to_access(self, mock_rt, mock_at):
        from auth.api.routes.oauth2.introspect import IntrospectionResponse, introspect_token

        client = make_oauth2_client(is_confidential=False, allowed_scopes=["introspect"])
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)

        mock_rt.return_value = None
        mock_at.return_value = IntrospectionResponse(active=True, token_type="Bearer")

        result = await introspect_token(
            token="jwt_token",
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            token_service=AsyncMock(),
            pat_service=AsyncMock(),
            authorization=None,
            client_id="test_client_id",
            client_secret=None,
            token_type_hint="refresh_token",
        )

        assert result.active is True
        assert result.token_type == "Bearer"

    @pytest.mark.asyncio
    async def test_basic_auth_used_for_client_credentials(self):
        from auth.api.routes.oauth2.introspect import IntrospectionResponse, introspect_token

        client = make_oauth2_client(is_confidential=True, allowed_scopes=["introspect"])
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.verify_client_secret = MagicMock(return_value=True)

        token_svc = AsyncMock()
        token_svc.get_access_token_by_jti = AsyncMock(return_value=None)

        with (
            patch(f"{MODULE}._introspect_access_token", new_callable=AsyncMock) as mock_at,
            patch(f"{MODULE}._introspect_refresh_token", new_callable=AsyncMock) as mock_rt,
        ):
            mock_at.return_value = IntrospectionResponse(active=False)
            mock_rt.return_value = None

            result = await introspect_token(
                token="some_token",
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                token_service=token_svc,
                pat_service=AsyncMock(),
                authorization=_basic_auth("test_client_id", "my_secret"),
                client_id=None,
                client_secret=None,
                token_type_hint=None,
            )

        assert result.active is False
        oauth2_svc.verify_client_secret.assert_called_once_with(client, "my_secret")


# ---------------------------------------------------------------------------
# _introspect_access_token
# ---------------------------------------------------------------------------


class TestIntrospectAccessToken:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.jwt")
    async def test_invalid_jwt_returns_inactive(self, mock_jwt):
        import jwt as real_jwt
        from auth.api.routes.oauth2.introspect import _introspect_access_token

        mock_jwt.decode = MagicMock(side_effect=real_jwt.DecodeError("bad"))
        mock_jwt.DecodeError = real_jwt.DecodeError

        result = await _introspect_access_token(AsyncMock(), AsyncMock(), "not.a.jwt")
        assert result.active is False

    @pytest.mark.asyncio
    @patch(f"{MODULE}.jwt")
    async def test_no_jti_returns_inactive(self, mock_jwt):
        import jwt as real_jwt
        from auth.api.routes.oauth2.introspect import _introspect_access_token

        mock_jwt.decode = MagicMock(return_value={"sub": "user1"})
        mock_jwt.DecodeError = real_jwt.DecodeError

        result = await _introspect_access_token(AsyncMock(), AsyncMock(), "valid.but.no.jti")
        assert result.active is False

    @pytest.mark.asyncio
    @patch(f"{MODULE}.jwt")
    async def test_token_not_in_db_returns_inactive(self, mock_jwt):
        import jwt as real_jwt
        from auth.api.routes.oauth2.introspect import _introspect_access_token

        mock_jwt.decode = MagicMock(return_value={"jti": "jti-123"})
        mock_jwt.DecodeError = real_jwt.DecodeError

        token_svc = AsyncMock()
        token_svc.get_access_token_by_jti = AsyncMock(return_value=None)

        result = await _introspect_access_token(AsyncMock(), token_svc, "token_with_jti")
        assert result.active is False

    @pytest.mark.asyncio
    @patch(f"{MODULE}.jwt")
    async def test_revoked_token_returns_inactive(self, mock_jwt):
        import jwt as real_jwt
        from auth.api.routes.oauth2.introspect import _introspect_access_token

        mock_jwt.decode = MagicMock(return_value={"jti": "jti-123"})
        mock_jwt.DecodeError = real_jwt.DecodeError

        at = make_access_token(jti="jti-123", revoked_at=datetime.now(UTC))
        token_svc = AsyncMock()
        token_svc.get_access_token_by_jti = AsyncMock(return_value=at)

        result = await _introspect_access_token(AsyncMock(), token_svc, "revoked_token")
        assert result.active is False

    @pytest.mark.asyncio
    @patch(f"{MODULE}.jwt")
    async def test_expired_token_returns_inactive(self, mock_jwt):
        import jwt as real_jwt
        from auth.api.routes.oauth2.introspect import _introspect_access_token

        mock_jwt.decode = MagicMock(return_value={"jti": "jti-123"})
        mock_jwt.DecodeError = real_jwt.DecodeError

        at = make_access_token(
            jti="jti-123",
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        at.revoked_at = None
        token_svc = AsyncMock()
        token_svc.get_access_token_by_jti = AsyncMock(return_value=at)

        result = await _introspect_access_token(AsyncMock(), token_svc, "expired_token")
        assert result.active is False

    @pytest.mark.asyncio
    @patch(f"{MODULE}.jwt")
    async def test_active_token_returns_claims(self, mock_jwt):
        import jwt as real_jwt
        from auth.api.routes.oauth2.introspect import _introspect_access_token

        claims = {
            "jti": "jti-123",
            "scope": "openid profile",
            "client_id": "c1",
            "sub": "user-1",
            "aud": "https://api.example.com",
            "iss": "https://auth.example.com",
            "exp": 9999999999,
            "iat": 1000000000,
            "nbf": 1000000000,
        }
        mock_jwt.decode = MagicMock(return_value=claims)
        mock_jwt.DecodeError = real_jwt.DecodeError

        at = make_access_token(
            jti="jti-123",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        at.revoked_at = None
        token_svc = AsyncMock()
        token_svc.get_access_token_by_jti = AsyncMock(return_value=at)

        result = await _introspect_access_token(AsyncMock(), token_svc, "active_token")
        assert result.active is True
        assert result.scope == "openid profile"
        assert result.client_id == "c1"
        assert result.sub == "user-1"
        assert result.token_type == "Bearer"
        assert result.jti == "jti-123"


# ---------------------------------------------------------------------------
# _introspect_refresh_token
# ---------------------------------------------------------------------------


class TestIntrospectRefreshToken:
    @pytest.mark.asyncio
    async def test_not_found_returns_none(self):
        from auth.api.routes.oauth2.introspect import _introspect_refresh_token

        token_svc = AsyncMock()
        token_svc.get_refresh_token = AsyncMock(return_value=None)

        result = await _introspect_refresh_token(AsyncMock(), token_svc, "bad_rt")
        assert result is None

    @pytest.mark.asyncio
    @patch(f"{MODULE}.PairwiseSubjectService")
    async def test_active_refresh_token(self, mock_pairwise_cls):
        from auth.api.routes.oauth2.introspect import _introspect_refresh_token

        client_id = uuid.uuid4()
        user_id = uuid.uuid4()
        pairwise_sub = str(uuid.uuid4())
        rt = make_refresh_token(
            client_id=client_id,
            user_id=user_id,
            scopes=["openid", "profile"],
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
        rt.created_at = datetime.now(UTC)

        token_svc = AsyncMock()
        token_svc.get_refresh_token = AsyncMock(return_value=rt)

        # Mock PairwiseSubjectService instance
        mock_pairwise = AsyncMock()
        mock_pairwise.get_sub_for_client = AsyncMock(return_value=pairwise_sub)
        mock_pairwise_cls.return_value = mock_pairwise

        # Mock db.execute for the OAuth2Client lookup
        mock_client = make_oauth2_client()
        mock_client.id = client_id
        client_result = MagicMock()
        client_result.scalar_one_or_none.return_value = mock_client
        db = AsyncMock()
        db.execute = AsyncMock(return_value=client_result)

        result = await _introspect_refresh_token(db, token_svc, "valid_rt")
        assert result is not None
        assert result.active is True
        assert result.token_type == "refresh_token"
        assert result.scope == "openid profile"
        assert result.client_id == str(client_id)
        assert result.sub == pairwise_sub


# ---------------------------------------------------------------------------
# _introspect_pat
# ---------------------------------------------------------------------------


def _make_user_email(email="user@example.com", is_primary=True):
    """Create a mock UserEmail."""
    ue = MagicMock()
    ue.email = email
    ue.is_primary = is_primary
    return ue


class TestIntrospectPat:
    @pytest.mark.asyncio
    async def test_invalid_pat_returns_inactive(self):
        from auth.api.routes.oauth2.introspect import _introspect_pat

        pat_svc = AsyncMock()
        pat_svc.validate_token = AsyncMock(return_value=None)

        db = AsyncMock()
        result = await _introspect_pat(db, pat_svc, "gab_pat_invalid")
        assert result.active is False

    @pytest.mark.asyncio
    async def test_valid_pat_returns_active(self):
        from auth.api.routes.oauth2.introspect import _introspect_pat

        user_id = uuid.uuid4()
        target_client_id = uuid.uuid4()
        pat = make_personal_access_token(
            user_id=user_id,
            scopes=["read:api", "write:api"],
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
        pat.target_client_id = target_client_id
        pat.user.emails = [_make_user_email("user@example.com", is_primary=True)]

        pat_svc = AsyncMock()
        pat_svc.validate_token = AsyncMock(return_value=pat)

        db = AsyncMock()
        with patch(
            "auth.api.routes.oauth2.introspect.UserService.get_by_id",
            new_callable=AsyncMock,
            return_value=pat.user,
        ):
            result = await _introspect_pat(db, pat_svc, "gab_pat_valid")
        assert result.active is True
        assert result.token_type == "pat"
        assert result.scope == "read:api write:api"
        assert result.client_id == str(target_client_id)
        assert result.username == "user@example.com"
        assert result.sub == str(user_id)
        assert result.jti == str(pat.id)
        assert result.exp is not None
        assert result.iat is not None

    @pytest.mark.asyncio
    async def test_valid_pat_no_expiration(self):
        from auth.api.routes.oauth2.introspect import _introspect_pat

        pat = make_personal_access_token(
            scopes=["openid"],
            expires_at=None,
        )
        pat.target_client_id = None
        pat.user.emails = [_make_user_email("user@example.com", is_primary=True)]

        pat_svc = AsyncMock()
        pat_svc.validate_token = AsyncMock(return_value=pat)

        db = AsyncMock()
        with patch(
            "auth.api.routes.oauth2.introspect.UserService.get_by_id",
            new_callable=AsyncMock,
            return_value=pat.user,
        ):
            result = await _introspect_pat(db, pat_svc, "gab_pat_noexp")
        assert result.active is True
        assert result.exp is None
        assert result.client_id is None


# ---------------------------------------------------------------------------
# introspect_token endpoint – PAT routing
# ---------------------------------------------------------------------------


class TestIntrospectTokenPat:
    @pytest.mark.asyncio
    @patch(f"{MODULE}._introspect_pat")
    async def test_pat_prefix_routes_to_pat_introspection(self, mock_introspect_pat):
        from auth.api.routes.oauth2.introspect import IntrospectionResponse, introspect_token

        client = make_oauth2_client(is_confidential=False, allowed_scopes=["introspect"])
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)

        mock_introspect_pat.return_value = IntrospectionResponse(
            active=True,
            token_type="pat",
            scope="read:api",
        )

        result = await introspect_token(
            token="gab_pat_abcdef1234567890",
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            token_service=AsyncMock(),
            pat_service=AsyncMock(),
            authorization=None,
            client_id="test_client_id",
            client_secret=None,
            token_type_hint=None,
        )

        assert result.active is True
        assert result.token_type == "pat"
        mock_introspect_pat.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(f"{MODULE}._introspect_pat")
    async def test_pat_prefix_inactive_returns_inactive(self, mock_introspect_pat):
        from auth.api.routes.oauth2.introspect import IntrospectionResponse, introspect_token

        client = make_oauth2_client(is_confidential=False, allowed_scopes=["introspect"])
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)

        mock_introspect_pat.return_value = IntrospectionResponse(active=False)

        result = await introspect_token(
            token="gab_pat_expired_or_revoked",
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            token_service=AsyncMock(),
            pat_service=AsyncMock(),
            authorization=None,
            client_id="test_client_id",
            client_secret=None,
            token_type_hint=None,
        )

        assert result.active is False
        mock_introspect_pat.assert_awaited_once()


class TestIntrospectRefreshTokenSubResolution:
    @pytest.mark.asyncio
    async def test_client_credentials_token_has_no_sub(self):
        """A refresh token with no user never triggers a pairwise lookup."""
        from auth.api.routes.oauth2.introspect import _introspect_refresh_token

        rt = make_refresh_token(
            client_id=uuid.uuid4(),
            scopes=["api"],
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
        rt.created_at = datetime.now(UTC)
        rt.user_id = None

        token_svc = AsyncMock()
        token_svc.get_refresh_token = AsyncMock(return_value=rt)

        db = AsyncMock()
        result = await _introspect_refresh_token(db, token_svc, "valid_rt")

        assert result.active is True
        assert result.sub is None
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_client_falls_back_to_raw_user_id(self):
        from auth.api.routes.oauth2.introspect import _introspect_refresh_token

        user_id = uuid.uuid4()
        rt = make_refresh_token(
            client_id=uuid.uuid4(),
            user_id=user_id,
            scopes=["openid"],
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
        rt.created_at = datetime.now(UTC)

        token_svc = AsyncMock()
        token_svc.get_refresh_token = AsyncMock(return_value=rt)

        client_result = MagicMock()
        client_result.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.execute = AsyncMock(return_value=client_result)

        result = await _introspect_refresh_token(db, token_svc, "valid_rt")

        assert result.sub == str(user_id)


class TestIntrospectPatSubAndUsername:
    @pytest.mark.asyncio
    async def test_user_without_emails_has_no_username(self):
        from auth.api.routes.oauth2.introspect import _introspect_pat

        pat = make_personal_access_token(user_id=uuid.uuid4(), scopes=["openid"], expires_at=None)
        pat.tenant_id = None
        user = MagicMock()
        user.emails = []

        pat_svc = AsyncMock()
        pat_svc.validate_token = AsyncMock(return_value=pat)

        with patch(
            "auth.api.routes.oauth2.introspect.UserService.get_by_id",
            new_callable=AsyncMock,
            return_value=user,
        ):
            result = await _introspect_pat(AsyncMock(), pat_svc, "gab_pat_valid")

        assert result.active is True
        assert result.username is None

    @pytest.mark.asyncio
    async def test_falls_back_to_first_email_when_none_primary(self):
        from auth.api.routes.oauth2.introspect import _introspect_pat

        pat = make_personal_access_token(user_id=uuid.uuid4(), scopes=["openid"], expires_at=None)
        pat.tenant_id = None
        user = MagicMock()
        user.emails = [_make_user_email("secondary@example.com", is_primary=False)]

        pat_svc = AsyncMock()
        pat_svc.validate_token = AsyncMock(return_value=pat)

        with patch(
            "auth.api.routes.oauth2.introspect.UserService.get_by_id",
            new_callable=AsyncMock,
            return_value=user,
        ):
            result = await _introspect_pat(AsyncMock(), pat_svc, "gab_pat_valid")

        assert result.username == "secondary@example.com"

    @pytest.mark.asyncio
    async def test_tenant_scoped_pat_uses_pairwise_sub(self):
        from auth.api.routes.oauth2.introspect import _introspect_pat

        user_id = uuid.uuid4()
        tenant = MagicMock()
        tenant.id = uuid.uuid4()
        pairwise_sub = str(uuid.uuid4())

        pat = make_personal_access_token(user_id=user_id, scopes=["openid"], expires_at=None)
        pat.tenant_id = tenant.id
        user = MagicMock()
        user.emails = []

        pat_svc = AsyncMock()
        pat_svc.validate_token = AsyncMock(return_value=pat)

        pairwise = AsyncMock()
        pairwise.get_or_create_sub = AsyncMock(return_value=pairwise_sub)

        with (
            patch(
                "auth.api.routes.oauth2.introspect.UserService.get_by_id",
                new_callable=AsyncMock,
                return_value=user,
            ),
            patch(
                "auth.api.routes.oauth2.introspect.TenantService.get_by_id",
                new_callable=AsyncMock,
                return_value=tenant,
            ),
            patch(f"{MODULE}.PairwiseSubjectService", return_value=pairwise),
        ):
            result = await _introspect_pat(AsyncMock(), pat_svc, "gab_pat_valid")

        assert result.sub == pairwise_sub

    @pytest.mark.asyncio
    async def test_unknown_tenant_keeps_raw_user_id(self):
        from auth.api.routes.oauth2.introspect import _introspect_pat

        user_id = uuid.uuid4()
        pat = make_personal_access_token(user_id=user_id, scopes=["openid"], expires_at=None)
        pat.tenant_id = uuid.uuid4()
        pat.user_id = user_id
        user = MagicMock()
        user.emails = []

        pat_svc = AsyncMock()
        pat_svc.validate_token = AsyncMock(return_value=pat)

        with (
            patch(
                "auth.api.routes.oauth2.introspect.UserService.get_by_id",
                new_callable=AsyncMock,
                return_value=user,
            ),
            patch(
                "auth.api.routes.oauth2.introspect.TenantService.get_by_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await _introspect_pat(AsyncMock(), pat_svc, "gab_pat_valid")

        assert result.sub == str(user_id)

    @pytest.mark.asyncio
    async def test_pat_without_user_skips_username_lookup(self):
        from auth.api.routes.oauth2.introspect import _introspect_pat

        pat = make_personal_access_token(scopes=["openid"], expires_at=None)
        pat.user_id = None
        pat.tenant_id = None

        pat_svc = AsyncMock()
        pat_svc.validate_token = AsyncMock(return_value=pat)

        with patch(
            "auth.api.routes.oauth2.introspect.UserService.get_by_id", new_callable=AsyncMock
        ) as get_user:
            result = await _introspect_pat(AsyncMock(), pat_svc, "gab_pat_valid")

        assert result.username is None
        get_user.assert_not_awaited()
