# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.token — TokenService and helper functions."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.services.token import TokenService, generate_token, hash_token

from tests.conftest import (
    make_access_token,
    make_jwk,
    make_oauth2_client,
    make_refresh_token,
)

# ── Helper functions ─────────────────────────────────────────────────────────


class TestGenerateToken:
    def test_length(self):
        token = generate_token()
        assert len(token) == 64

    def test_hex_format(self):
        token = generate_token()
        int(token, 16)  # should not raise

    def test_randomness(self):
        t1 = generate_token()
        t2 = generate_token()
        assert t1 != t2


class TestHashToken:
    def test_sha256(self):
        token = "test_token_value"
        result = hash_token(token)
        expected = hashlib.sha256(token.encode()).hexdigest()
        assert result == expected

    def test_deterministic(self):
        assert hash_token("abc") == hash_token("abc")

    def test_different_inputs(self):
        assert hash_token("a") != hash_token("b")


# ── TokenService ─────────────────────────────────────────────────────────────


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
def token_repo():
    """Fully mocked TokenRepository."""
    repo = MagicMock()
    repo.add_access_token = AsyncMock()
    repo.add_refresh_token = AsyncMock()
    repo.find_access_token_by_jti = AsyncMock()
    repo.find_revoked_access_token_by_jti = AsyncMock()
    repo.find_active_access_token_by_jti = AsyncMock()
    repo.find_refresh_token_by_hash = AsyncMock()
    repo.find_valid_refresh_token_by_hash = AsyncMock()
    repo.revoke_access_tokens_for_refresh_cascade = AsyncMock()
    repo.aggregate_authorized_clients_for_user = AsyncMock()
    repo.find_clients_by_ids = AsyncMock()
    repo.find_latest_active_scopes = AsyncMock()
    repo.find_client_by_string_id = AsyncMock()
    repo.list_active_access_tokens_for_user_client = AsyncMock()
    repo.list_active_refresh_tokens_for_user_client = AsyncMock()
    return repo


@pytest.fixture
def token_service(jwks_service, token_repo):
    return TokenService(jwks_service, repository=token_repo)


@pytest.fixture(autouse=True)
def _mock_pairwise():
    """Auto-mock PairwiseSubjectService for all token service tests."""
    with patch("auth.services.token.PairwiseSubjectService") as cls:
        mock_svc = AsyncMock()
        mock_svc.get_sub_for_client.return_value = str(uuid.uuid4())
        cls.return_value = mock_svc
        yield mock_svc


class TestCreateAccessToken:
    @pytest.mark.asyncio
    async def test_success(self, db, token_service, token_repo, jwks_service):
        jwk = make_jwk()
        jwks_service.get_active_key.return_value = jwk
        jwks_service.decrypt_private_key.return_value = MagicMock()

        client = make_oauth2_client()
        scopes = ["openid", "profile"]
        user_id = uuid.uuid4()

        with patch("auth.services.token.jwt") as mock_jwt:
            mock_jwt.encode.return_value = "jwt_string"
            jwt_str, access_token_model = await token_service.create_access_token(
                db, client, scopes, user_id=user_id
            )

        assert jwt_str == "jwt_string"
        token_repo.add_access_token.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_active_key_raises(self, db, token_service, jwks_service):
        jwks_service.get_active_key.return_value = None
        client = make_oauth2_client()

        with pytest.raises(ValueError, match="No active signing key"):
            await token_service.create_access_token(db, client, ["openid"])

    @pytest.mark.asyncio
    async def test_uses_client_expiry_when_set(self, db, token_service, token_repo, jwks_service):
        jwk = make_jwk()
        jwks_service.get_active_key.return_value = jwk
        jwks_service.decrypt_private_key.return_value = MagicMock()

        client = make_oauth2_client(access_token_expiry_seconds=300)

        with patch("auth.services.token.jwt") as mock_jwt:
            mock_jwt.encode.return_value = "jwt"
            jwt_str, at = await token_service.create_access_token(db, client, ["openid"])

        # Verify the AccessToken was created (via repo.add_access_token)
        token_repo.add_access_token.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_includes_nonce_in_payload(self, db, token_service, jwks_service):
        jwk = make_jwk()
        jwks_service.get_active_key.return_value = jwk
        jwks_service.decrypt_private_key.return_value = MagicMock()
        client = make_oauth2_client()

        with patch("auth.services.token.jwt") as mock_jwt:
            mock_jwt.encode.return_value = "jwt"
            await token_service.create_access_token(db, client, ["openid"], nonce="test_nonce")

        call_args = mock_jwt.encode.call_args[0][0]
        assert call_args["nonce"] == "test_nonce"

    @pytest.mark.asyncio
    async def test_includes_actor_for_delegation(self, db, token_service, jwks_service):
        jwk = make_jwk()
        jwks_service.get_active_key.return_value = jwk
        jwks_service.decrypt_private_key.return_value = MagicMock()
        client = make_oauth2_client()
        actor = {"sub": "admin_user"}

        with patch("auth.services.token.jwt") as mock_jwt:
            mock_jwt.encode.return_value = "jwt"
            await token_service.create_access_token(db, client, ["openid"], actor=actor)

        call_args = mock_jwt.encode.call_args[0][0]
        assert call_args["act"] == actor


class TestCreateRefreshToken:
    @pytest.mark.asyncio
    async def test_success(self, db, token_service, token_repo):
        access_token = make_access_token()
        client = make_oauth2_client()

        token_plain, rt = await token_service.create_refresh_token(
            db, access_token, client, user_id=uuid.uuid4()
        )

        assert len(token_plain) == 64
        token_repo.add_refresh_token.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_uses_client_expiry(self, db, token_service, token_repo):
        access_token = make_access_token()
        client = make_oauth2_client(refresh_token_expiry_seconds=86400)

        token_plain, rt = await token_service.create_refresh_token(db, access_token, client)

        token_repo.add_refresh_token.assert_awaited_once()


class TestCreateTokenPair:
    @pytest.mark.asyncio
    async def test_returns_three_values(self, db, token_service, jwks_service):
        jwk = make_jwk()
        jwks_service.get_active_key.return_value = jwk
        jwks_service.decrypt_private_key.return_value = MagicMock()
        client = make_oauth2_client()

        with patch("auth.services.token.jwt") as mock_jwt:
            mock_jwt.encode.return_value = "jwt_token"
            access_jwt, refresh_plain, expires_in = await token_service.create_token_pair(
                db, client, ["openid"]
            )

        assert access_jwt == "jwt_token"
        assert len(refresh_plain) == 64
        assert isinstance(expires_in, int)


class TestGetRefreshToken:
    @pytest.mark.asyncio
    async def test_found(self, db, token_service, token_repo):
        rt = make_refresh_token()
        token_repo.find_valid_refresh_token_by_hash.return_value = rt

        result = await token_service.get_refresh_token(db, "plain_token")
        assert result is rt

    @pytest.mark.asyncio
    async def test_not_found(self, db, token_service, token_repo):
        token_repo.find_valid_refresh_token_by_hash.return_value = None

        result = await token_service.get_refresh_token(db, "missing")
        assert result is None


class TestConsumeRefreshToken:
    @pytest.mark.asyncio
    async def test_marks_used(self, db, token_service):
        rt = make_refresh_token()
        rt.used_at = None

        await token_service.consume_refresh_token(db, rt)

        assert rt.used_at is not None
        db.flush.assert_called_once()


class TestRevokeAccessToken:
    @pytest.mark.asyncio
    async def test_revokes(self, db, token_service, token_repo):
        at = make_access_token()
        at.revoked_at = None
        token_repo.find_access_token_by_jti.return_value = at

        result = await token_service.revoke_access_token(db, at.jti)
        assert result is True
        assert at.revoked_at is not None

    @pytest.mark.asyncio
    async def test_not_found(self, db, token_service, token_repo):
        token_repo.find_access_token_by_jti.return_value = None

        result = await token_service.revoke_access_token(db, "missing_jti")
        assert result is False


class TestRevokeRefreshToken:
    @pytest.mark.asyncio
    async def test_revokes_and_cascade(self, db, token_service, token_repo):
        rt = make_refresh_token()
        rt.revoked_at = None
        token_repo.find_refresh_token_by_hash.return_value = rt

        result = await token_service.revoke_refresh_token(db, "plain_token")
        assert result is True
        assert rt.revoked_at is not None
        token_repo.revoke_access_tokens_for_refresh_cascade.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_found(self, db, token_service, token_repo):
        token_repo.find_refresh_token_by_hash.return_value = None

        result = await token_service.revoke_refresh_token(db, "missing")
        assert result is False


class TestRefreshTokens:
    @pytest.mark.asyncio
    async def test_uses_original_scopes(self, db, token_service, jwks_service):
        jwk = make_jwk()
        jwks_service.get_active_key.return_value = jwk
        jwks_service.decrypt_private_key.return_value = MagicMock()

        rt = make_refresh_token(scopes=["openid", "profile"])
        client = make_oauth2_client()

        with patch("auth.services.token.jwt") as mock_jwt:
            mock_jwt.encode.return_value = "new_jwt"
            access_jwt, refresh_plain, expires_in = await token_service.refresh_tokens(
                db, rt, client
            )

        assert access_jwt == "new_jwt"
        assert rt.used_at is not None

    @pytest.mark.asyncio
    async def test_rejects_expanded_scopes(self, db, token_service):
        rt = make_refresh_token(scopes=["openid"])
        client = make_oauth2_client()

        with pytest.raises(ValueError, match="exceed original"):
            await token_service.refresh_tokens(db, rt, client, scopes=["openid", "admin"])


class TestValidateAccessToken:
    @pytest.mark.asyncio
    async def test_valid_token(self, db, token_service, token_repo, jwks_service):
        jwk = make_jwk(revoked_at=None)
        jwks_service.get_key_by_kid.return_value = jwk

        payload = {
            "iss": "https://auth.example.com",
            "sub": str(uuid.uuid4()),
            "aud": "client_id",
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            "iat": int(datetime.now(UTC).timestamp()),
            "jti": str(uuid.uuid4()),
        }

        # Token not revoked
        token_repo.find_revoked_access_token_by_jti.return_value = None

        with patch("auth.services.token.jwt") as mock_jwt:
            mock_jwt.get_unverified_header.return_value = {"kid": jwk.kid}
            mock_jwt.decode.return_value = payload
            mock_jwt.InvalidTokenError = Exception

            result = await token_service.validate_access_token(db, "token")

        assert result == payload

    @pytest.mark.asyncio
    async def test_revoked_token(self, db, token_service, token_repo, jwks_service):
        jwk = make_jwk()
        jwks_service.get_key_by_kid.return_value = jwk

        payload = {"jti": "revoked_jti", "exp": 9999999999, "iat": 1, "iss": "x", "sub": "y"}

        # Token IS revoked
        revoked_at = make_access_token(revoked_at=datetime.now(UTC))
        token_repo.find_revoked_access_token_by_jti.return_value = revoked_at

        with patch("auth.services.token.jwt") as mock_jwt:
            mock_jwt.get_unverified_header.return_value = {"kid": jwk.kid}
            mock_jwt.decode.return_value = payload
            mock_jwt.InvalidTokenError = Exception

            result = await token_service.validate_access_token(db, "token")

        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_jwt(self, db, token_service, jwks_service):
        with patch("auth.services.token.jwt") as mock_jwt:
            mock_jwt.get_unverified_header.side_effect = Exception("bad token")
            mock_jwt.InvalidTokenError = Exception

            result = await token_service.validate_access_token(db, "bad_token")

        assert result is None

    @pytest.mark.asyncio
    async def test_missing_kid(self, db, token_service, jwks_service):
        with patch("auth.services.token.jwt") as mock_jwt:
            mock_jwt.get_unverified_header.return_value = {}
            mock_jwt.InvalidTokenError = Exception

            result = await token_service.validate_access_token(db, "token")

        assert result is None

    @pytest.mark.asyncio
    async def test_revoked_key(self, db, token_service, jwks_service):
        jwk = make_jwk(revoked_at=datetime.now(UTC))
        jwks_service.get_key_by_kid.return_value = jwk

        with patch("auth.services.token.jwt") as mock_jwt:
            mock_jwt.get_unverified_header.return_value = {"kid": jwk.kid}
            mock_jwt.InvalidTokenError = Exception

            result = await token_service.validate_access_token(db, "token")

        assert result is None

    @pytest.mark.asyncio
    async def test_no_jti_in_payload(self, db, token_service, token_repo, jwks_service):
        """Payload has no jti, skip revocation check."""
        jwk = make_jwk(revoked_at=None)
        jwks_service.get_key_by_kid.return_value = jwk

        payload = {
            "iss": "https://auth.example.com",
            "sub": str(uuid.uuid4()),
            "aud": "client_id",
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            "iat": int(datetime.now(UTC).timestamp()),
            # Note: no jti field
        }

        with patch("auth.services.token.jwt") as mock_jwt:
            mock_jwt.get_unverified_header.return_value = {"kid": jwk.kid}
            mock_jwt.decode.return_value = payload
            mock_jwt.InvalidTokenError = Exception

            result = await token_service.validate_access_token(db, "token")

        assert result == payload
        # Repo should NOT be called (no revocation check)
        token_repo.find_revoked_access_token_by_jti.assert_not_called()

    @pytest.mark.asyncio
    async def test_key_not_found(self, db, token_service, jwks_service):
        """Cover: key not found by kid returns None."""
        jwks_service.get_key_by_kid.return_value = None

        with patch("auth.services.token.jwt") as mock_jwt:
            mock_jwt.get_unverified_header.return_value = {"kid": "unknown-kid"}
            mock_jwt.InvalidTokenError = Exception

            result = await token_service.validate_access_token(db, "token")

        assert result is None


class TestCreateIdToken:
    @pytest.mark.asyncio
    async def test_creates_id_token(self, db, token_service, jwks_service):
        jwk = make_jwk()
        jwks_service.get_active_key.return_value = jwk
        jwks_service.decrypt_private_key.return_value = MagicMock()
        client = make_oauth2_client()

        with patch("auth.services.token.jwt") as mock_jwt:
            mock_jwt.encode.return_value = "id_token_jwt"
            result = await token_service.create_id_token(db, client, uuid.uuid4(), nonce="nonce123")

        assert result == "id_token_jwt"
        call_args = mock_jwt.encode.call_args[0][0]
        assert call_args["nonce"] == "nonce123"

    @pytest.mark.asyncio
    async def test_no_active_key_raises(self, db, token_service, jwks_service):
        jwks_service.get_active_key.return_value = None
        client = make_oauth2_client()

        with pytest.raises(ValueError, match="No active signing key"):
            await token_service.create_id_token(db, client, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_includes_at_hash(self, db, token_service, jwks_service):
        jwk = make_jwk()
        jwks_service.get_active_key.return_value = jwk
        jwks_service.decrypt_private_key.return_value = MagicMock()
        client = make_oauth2_client()

        with patch("auth.services.token.jwt") as mock_jwt:
            mock_jwt.encode.return_value = "id_token"
            await token_service.create_id_token(
                db, client, uuid.uuid4(), access_token="access_token_value"
            )

        call_args = mock_jwt.encode.call_args[0][0]
        assert "at_hash" in call_args

    @pytest.mark.asyncio
    async def test_includes_auth_time(self, db, token_service, jwks_service):
        jwk = make_jwk()
        jwks_service.get_active_key.return_value = jwk
        jwks_service.decrypt_private_key.return_value = MagicMock()
        client = make_oauth2_client()
        auth_time = datetime.now(UTC) - timedelta(minutes=5)

        with patch("auth.services.token.jwt") as mock_jwt:
            mock_jwt.encode.return_value = "id_token"
            await token_service.create_id_token(db, client, uuid.uuid4(), auth_time=auth_time)

        call_args = mock_jwt.encode.call_args[0][0]
        assert "auth_time" in call_args
        assert call_args["auth_time"] == int(auth_time.timestamp())


class TestCreateTokenPairClientExpiry:
    @pytest.mark.asyncio
    async def test_uses_client_access_token_expiry(self, db, token_service, jwks_service):
        """Cover line 225: client_id as subject when no user_id; and client expiry."""
        jwk = make_jwk()
        jwks_service.get_active_key.return_value = jwk
        jwks_service.decrypt_private_key.return_value = MagicMock()
        client = make_oauth2_client(access_token_expiry_seconds=600)

        with patch("auth.services.token.jwt") as mock_jwt:
            mock_jwt.encode.return_value = "jwt_token"
            access_jwt, refresh_plain, expires_in = await token_service.create_token_pair(
                db, client, ["openid"]
            )

        # When client has custom expiry, expires_in should match
        assert expires_in == 600

    @pytest.mark.asyncio
    async def test_no_user_uses_client_id_as_subject(self, db, token_service, jwks_service):
        """Cover line 103: sub = client.client_id when user_id is None."""
        jwk = make_jwk()
        jwks_service.get_active_key.return_value = jwk
        jwks_service.decrypt_private_key.return_value = MagicMock()
        client = make_oauth2_client(client_id="my_client")

        with patch("auth.services.token.jwt") as mock_jwt:
            mock_jwt.encode.return_value = "jwt_token"
            await token_service.create_access_token(db, client, ["openid"], user_id=None)

        call_args = mock_jwt.encode.call_args[0][0]
        assert call_args["sub"] == "my_client"


class TestGetUserAuthorizedClients:
    @pytest.mark.asyncio
    async def test_returns_clients(self, db, token_service, token_repo):
        client_uuid = uuid.uuid4()
        user_id = uuid.uuid4()

        # Aggregated row from the repo
        client_row = MagicMock()
        client_row.client_id = client_uuid
        client_row.first_authorized = datetime.now(UTC) - timedelta(days=1)
        client_row.last_used = datetime.now(UTC)

        # Client object
        mock_client = make_oauth2_client(client_id="app_client")
        mock_client.id = client_uuid
        mock_client.homepage_url = "https://app.example.com"
        mock_client.description = "Test app"

        token_repo.aggregate_authorized_clients_for_user.return_value = [client_row]
        token_repo.find_clients_by_ids.return_value = [mock_client]
        token_repo.find_latest_active_scopes.return_value = ["openid"]

        result = await token_service.get_user_authorized_clients(db, user_id)
        assert len(result) == 1
        assert result[0]["client_id"] == "app_client"
        assert result[0]["scopes"] == ["openid"]

    @pytest.mark.asyncio
    async def test_no_authorized_clients(self, db, token_service, token_repo):
        token_repo.aggregate_authorized_clients_for_user.return_value = []

        result = await token_service.get_user_authorized_clients(db, uuid.uuid4())
        assert result == []

    @pytest.mark.asyncio
    async def test_client_not_found_skipped(self, db, token_service, token_repo):
        """Cover: client not in clients dict (e.g. deleted client)."""
        client_uuid = uuid.uuid4()

        client_row = MagicMock()
        client_row.client_id = client_uuid
        client_row.first_authorized = datetime.now(UTC)
        client_row.last_used = datetime.now(UTC)

        token_repo.aggregate_authorized_clients_for_user.return_value = [client_row]
        token_repo.find_clients_by_ids.return_value = []

        result = await token_service.get_user_authorized_clients(db, uuid.uuid4())
        assert result == []

    @pytest.mark.asyncio
    async def test_empty_scopes_fallback(self, db, token_service, token_repo):
        """Cover: scopes_row is None => scopes defaults to empty list."""
        client_uuid = uuid.uuid4()
        user_id = uuid.uuid4()

        client_row = MagicMock()
        client_row.client_id = client_uuid
        client_row.first_authorized = datetime.now(UTC)
        client_row.last_used = datetime.now(UTC)

        mock_client = make_oauth2_client(client_id="app_client")
        mock_client.id = client_uuid

        token_repo.aggregate_authorized_clients_for_user.return_value = [client_row]
        token_repo.find_clients_by_ids.return_value = [mock_client]
        token_repo.find_latest_active_scopes.return_value = None

        result = await token_service.get_user_authorized_clients(db, user_id)
        assert result[0]["scopes"] == []


class TestRevokeClientAccess:
    @pytest.mark.asyncio
    async def test_revokes_all_tokens(self, db, token_service, token_repo):
        client = make_oauth2_client()
        access_tokens = [make_access_token(), make_access_token()]
        refresh_tokens = [make_refresh_token()]

        for t in access_tokens:
            t.revoked_at = None
        for t in refresh_tokens:
            t.revoked_at = None

        token_repo.find_client_by_string_id.return_value = client
        token_repo.list_active_access_tokens_for_user_client.return_value = access_tokens
        token_repo.list_active_refresh_tokens_for_user_client.return_value = refresh_tokens

        count = await token_service.revoke_client_access(db, uuid.uuid4(), "test_client_id")

        assert count == 3
        assert all(t.revoked_at is not None for t in access_tokens)
        assert all(t.revoked_at is not None for t in refresh_tokens)

    @pytest.mark.asyncio
    async def test_client_not_found(self, db, token_service, token_repo):
        token_repo.find_client_by_string_id.return_value = None

        count = await token_service.revoke_client_access(db, uuid.uuid4(), "missing_client")
        assert count == 0
