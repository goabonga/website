# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.token_exchange — TokenExchangeService (RFC 8693)."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.services.token_exchange import (
    SUPPORTED_REQUESTED_TOKEN_TYPES,
    SUPPORTED_SUBJECT_TOKEN_TYPES,
    TOKEN_EXCHANGE_GRANT_TYPE,
    TOKEN_TYPE_ACCESS_TOKEN,
    TOKEN_TYPE_ID_TOKEN,
    TOKEN_TYPE_JWT,
    TokenExchangeError,
    TokenExchangeService,
)

from tests.conftest import make_oauth2_client


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def token_repo():
    """Fully mocked TokenRepository."""
    repo = MagicMock()
    repo.find_active_access_token_by_jti = AsyncMock()
    return repo


@pytest.fixture
def role_repo():
    """Fully mocked RoleRepository."""
    repo = MagicMock()
    repo.list_user_role_assignments_with_scopes = AsyncMock()
    return repo


@pytest.fixture
def service(token_repo, role_repo):
    return TokenExchangeService(repository=token_repo, role_repository=role_repo)


# ── TokenExchangeError ──────────────────────────────────────────────────────


class TestTokenExchangeError:
    def test_attributes(self):
        err = TokenExchangeError("invalid_request", "bad token")
        assert err.error == "invalid_request"
        assert err.description == "bad token"
        assert str(err) == "bad token"


# ── constants ───────────────────────────────────────────────────────────────


class TestConstants:
    def test_token_types(self):
        assert TOKEN_TYPE_ACCESS_TOKEN in SUPPORTED_SUBJECT_TOKEN_TYPES
        assert TOKEN_TYPE_JWT in SUPPORTED_SUBJECT_TOKEN_TYPES
        assert TOKEN_TYPE_ID_TOKEN not in SUPPORTED_SUBJECT_TOKEN_TYPES

    def test_requested_types(self):
        assert TOKEN_TYPE_ACCESS_TOKEN in SUPPORTED_REQUESTED_TOKEN_TYPES

    def test_grant_type(self):
        assert "token-exchange" in TOKEN_EXCHANGE_GRANT_TYPE


# ── validate_subject_token ──────────────────────────────────────────────────


class TestValidateSubjectToken:
    @pytest.mark.asyncio
    async def test_unsupported_type_raises(self, db, service):
        client = make_oauth2_client()
        with pytest.raises(TokenExchangeError, match="Unsupported subject_token_type"):
            await service.validate_subject_token(db, "token", TOKEN_TYPE_ID_TOKEN, client)

    @pytest.mark.asyncio
    async def test_access_token_success(self, db, service, token_repo):
        client = make_oauth2_client()
        user_id = uuid.uuid4()
        token_record = MagicMock()
        token_record.user_id = user_id
        token_record.scopes = ["openid", "profile"]
        token_record.expires_at = datetime.now(UTC) + timedelta(hours=1)

        token_repo.find_active_access_token_by_jti.return_value = token_record

        with patch("jwt.decode", return_value={"jti": "test-jti"}):
            record, uid, scopes = await service.validate_subject_token(
                db, "fake_jwt", TOKEN_TYPE_ACCESS_TOKEN, client
            )
        assert record is token_record
        assert uid == user_id
        assert scopes == ["openid", "profile"]

    @pytest.mark.asyncio
    async def test_access_token_no_jti(self, db, service):
        client = make_oauth2_client()
        with (
            patch("jwt.decode", return_value={}),
            pytest.raises(TokenExchangeError, match="missing jti"),
        ):
            await service.validate_subject_token(db, "fake_jwt", TOKEN_TYPE_ACCESS_TOKEN, client)

    @pytest.mark.asyncio
    async def test_access_token_not_found(self, db, service, token_repo):
        client = make_oauth2_client()
        token_repo.find_active_access_token_by_jti.return_value = None
        with (
            patch("jwt.decode", return_value={"jti": "test-jti"}),
            pytest.raises(TokenExchangeError, match="not found or revoked"),
        ):
            await service.validate_subject_token(db, "fake_jwt", TOKEN_TYPE_ACCESS_TOKEN, client)

    @pytest.mark.asyncio
    async def test_access_token_expired(self, db, service, token_repo):
        client = make_oauth2_client()
        token_record = MagicMock()
        token_record.expires_at = datetime.now(UTC) - timedelta(hours=1)
        token_repo.find_active_access_token_by_jti.return_value = token_record

        with (
            patch("jwt.decode", return_value={"jti": "test-jti"}),
            pytest.raises(TokenExchangeError, match="expired"),
        ):
            await service.validate_subject_token(db, "fake_jwt", TOKEN_TYPE_ACCESS_TOKEN, client)

    @pytest.mark.asyncio
    async def test_access_token_decode_error(self, db, service):
        import jwt

        client = make_oauth2_client()
        with (
            patch("jwt.decode", side_effect=jwt.DecodeError("bad")),
            pytest.raises(TokenExchangeError, match="Failed to decode"),
        ):
            await service.validate_subject_token(db, "bad_jwt", TOKEN_TYPE_ACCESS_TOKEN, client)

    @pytest.mark.asyncio
    async def test_jwt_type_success(self, db, service):
        client = make_oauth2_client()
        uid = uuid.uuid4()
        with patch(
            "jwt.decode",
            return_value={"sub": str(uid), "scope": "openid profile"},
        ):
            record, user_id, scopes = await service.validate_subject_token(
                db, "fake_jwt", TOKEN_TYPE_JWT, client
            )
        assert record is None
        assert user_id == uid
        assert scopes == ["openid", "profile"]

    @pytest.mark.asyncio
    async def test_jwt_type_no_sub(self, db, service):
        client = make_oauth2_client()
        with patch("jwt.decode", return_value={}):
            record, user_id, scopes = await service.validate_subject_token(
                db, "fake_jwt", TOKEN_TYPE_JWT, client
            )
        assert user_id is None
        assert scopes == []

    @pytest.mark.asyncio
    async def test_jwt_type_non_uuid_sub(self, db, service):
        client = make_oauth2_client()
        with patch(
            "jwt.decode",
            return_value={"sub": "not-a-uuid", "scope": "openid"},
        ):
            record, user_id, scopes = await service.validate_subject_token(
                db, "fake_jwt", TOKEN_TYPE_JWT, client
            )
        assert user_id is None
        assert scopes == ["openid"]

    @pytest.mark.asyncio
    async def test_jwt_type_decode_error(self, db, service):
        import jwt

        client = make_oauth2_client()
        with (
            patch("jwt.decode", side_effect=jwt.DecodeError("bad")),
            pytest.raises(TokenExchangeError, match="Failed to decode"),
        ):
            await service.validate_subject_token(db, "bad_jwt", TOKEN_TYPE_JWT, client)


# ── validate_actor_token ────────────────────────────────────────────────────


class TestValidateActorToken:
    def test_none_token(self, service):
        result = service.validate_actor_token(None, None)
        assert result is None

    def test_no_type_raises(self, service):
        with pytest.raises(TokenExchangeError, match="actor_token_type is required"):
            service.validate_actor_token("token", None)

    def test_success(self, service):
        with patch(
            "jwt.decode",
            return_value={"sub": "user-1", "client_id": "client-1"},
        ):
            result = service.validate_actor_token("token", TOKEN_TYPE_ACCESS_TOKEN)
        assert result["sub"] == "user-1"
        assert result["client_id"] == "client-1"

    def test_azp_fallback(self, service):
        with patch(
            "jwt.decode",
            return_value={"sub": "user-1", "azp": "azp-client"},
        ):
            result = service.validate_actor_token("token", TOKEN_TYPE_ACCESS_TOKEN)
        assert result["client_id"] == "azp-client"

    def test_decode_error(self, service):
        import jwt

        with (
            patch("jwt.decode", side_effect=jwt.DecodeError("bad")),
            pytest.raises(TokenExchangeError, match="Failed to decode actor"),
        ):
            service.validate_actor_token("token", TOKEN_TYPE_ACCESS_TOKEN)


# ── get_user_scopes_from_roles ──────────────────────────────────────────────


class TestGetUserScopesFromRoles:
    @pytest.mark.asyncio
    async def test_returns_non_expired_roles(self, db, service, role_repo):
        role1 = MagicMock()
        role2 = MagicMock()
        ur1 = MagicMock()
        ur1.is_expired = False
        ur1.role = role1
        ur2 = MagicMock()
        ur2.is_expired = True
        ur2.role = role2

        role_repo.list_user_role_assignments_with_scopes.return_value = [ur1, ur2]
        roles = await service.get_user_scopes_from_roles(db, uuid.uuid4())
        assert roles == [role1]

    @pytest.mark.asyncio
    async def test_empty_roles(self, db, service, role_repo):
        role_repo.list_user_role_assignments_with_scopes.return_value = []
        roles = await service.get_user_scopes_from_roles(db, uuid.uuid4())
        assert roles == []


# ── user_has_scope ──────────────────────────────────────────────────────────


class TestUserHasScope:
    def test_has_scope(self, service):
        role = MagicMock()
        role.has_scope.return_value = True
        assert service.user_has_scope([role], "users:read") is True

    def test_no_scope(self, service):
        role = MagicMock()
        role.has_scope.return_value = False
        assert service.user_has_scope([role], "users:read") is False

    def test_empty_roles(self, service):
        assert service.user_has_scope([], "users:read") is False


# ── scope_matches_allowed ───────────────────────────────────────────────────


class TestScopeMatchesAllowed:
    def test_global_wildcard(self, service):
        assert service.scope_matches_allowed("users:read", ["*"]) is True

    def test_exact_match(self, service):
        assert service.scope_matches_allowed("users:read", ["users:read"]) is True

    def test_resource_wildcard(self, service):
        assert service.scope_matches_allowed("users:read", ["users:*"]) is True

    def test_no_match(self, service):
        assert service.scope_matches_allowed("users:read", ["admin:*"]) is False

    def test_group_scope_of_the_settings(self, service):
        groups = {"suite:*": ["notes", "tasks"]}
        with patch("auth.services.token_exchange.settings.scope_groups", groups):
            assert service.scope_matches_allowed("notes:read", ["suite:*"]) is True
            assert service.scope_matches_allowed("tasks:write", ["suite:*"]) is True
            assert service.scope_matches_allowed("tasks", ["suite:*"]) is True

    def test_group_scope_does_not_match_other_resources(self, service):
        with patch("auth.services.token_exchange.settings.scope_groups", {"suite:*": ["notes"]}):
            assert service.scope_matches_allowed("users:read", ["suite:*"]) is False

    def test_no_group_scope_by_default(self, service):
        with patch("auth.services.token_exchange.settings.scope_groups", {}):
            assert service.scope_matches_allowed("notes:read", ["suite:*"]) is False

    def test_scope_without_colon(self, service):
        assert service.scope_matches_allowed("openid", ["openid"]) is True
        assert service.scope_matches_allowed("openid", ["other"]) is False


# ── determine_scopes ────────────────────────────────────────────────────────


class TestDetermineScopes:
    @pytest.mark.asyncio
    async def test_default_to_subject_scopes(self, db, service):
        client = make_oauth2_client(allowed_scopes=["openid", "profile"])
        service.get_user_scopes_from_roles = AsyncMock(return_value=[])
        result = await service.determine_scopes(
            db, None, ["openid", "profile"], client, uuid.uuid4()
        )
        assert "openid" in result

    @pytest.mark.asyncio
    async def test_requested_scopes(self, db, service):
        client = make_oauth2_client(allowed_scopes=["openid", "profile"])
        service.get_user_scopes_from_roles = AsyncMock(return_value=[])
        result = await service.determine_scopes(
            db, "openid", ["openid", "profile"], client, uuid.uuid4()
        )
        assert result == ["openid"]

    @pytest.mark.asyncio
    async def test_scope_not_allowed_raises(self, db, service):
        client = make_oauth2_client(allowed_scopes=["openid"])
        with pytest.raises(TokenExchangeError, match="not allowed"):
            await service.determine_scopes(db, "admin:write", ["openid"], client, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_no_user_id_only_subject_scopes(self, db, service):
        client = make_oauth2_client(allowed_scopes=["openid"])
        result = await service.determine_scopes(db, "openid", ["openid"], client, user_id=None)
        assert result == ["openid"]

    @pytest.mark.asyncio
    async def test_no_user_id_escalation_fails(self, db, service):
        client = make_oauth2_client(allowed_scopes=["openid", "admin:read"])
        with pytest.raises(TokenExchangeError, match="Cannot escalate"):
            await service.determine_scopes(db, "admin:read", [], client, user_id=None)

    @pytest.mark.asyncio
    async def test_rbac_escalation(self, db, service):
        client = make_oauth2_client(allowed_scopes=["*"])
        role = MagicMock()
        role.has_scope.return_value = True
        service.get_user_scopes_from_roles = AsyncMock(return_value=[role])

        result = await service.determine_scopes(db, "admin:write", ["openid"], client, uuid.uuid4())
        assert "admin:write" in result

    @pytest.mark.asyncio
    async def test_rbac_denied(self, db, service):
        client = make_oauth2_client(allowed_scopes=["*"])
        role = MagicMock()
        role.has_scope.return_value = False
        service.get_user_scopes_from_roles = AsyncMock(return_value=[role])

        with pytest.raises(TokenExchangeError, match="does not have permission"):
            await service.determine_scopes(db, "admin:write", [], client, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_mixed_granted_and_denied(self, db, service):
        client = make_oauth2_client(allowed_scopes=["*"])
        role = MagicMock()

        def has_scope_fn(scope):
            return scope == "admin:read"

        role.has_scope = has_scope_fn
        service.get_user_scopes_from_roles = AsyncMock(return_value=[role])

        result = await service.determine_scopes(
            db, "openid admin:read", ["openid"], client, uuid.uuid4()
        )
        assert "openid" in result
        assert "admin:read" in result


# ── validate_audience ───────────────────────────────────────────────────────


class TestValidateAudience:
    def test_audience_returned(self, service):
        assert service.validate_audience("aud", None) == "aud"

    def test_resource_fallback(self, service):
        assert (
            service.validate_audience(None, "https://api.example.com") == "https://api.example.com"
        )

    def test_both_none(self, service):
        assert service.validate_audience(None, None) is None

    def test_audience_takes_precedence(self, service):
        assert service.validate_audience("aud", "resource") == "aud"


class TestValidateSubjectTokenUnhandledSupportedType:
    """The defensive tail: a type declared supported but with no handler branch."""

    @pytest.mark.asyncio
    async def test_supported_but_unhandled_type_is_rejected(self, db, service):
        unhandled = "urn:ietf:params:oauth:token-type:saml2"

        with (
            patch(
                "auth.services.token_exchange.SUPPORTED_SUBJECT_TOKEN_TYPES",
                [unhandled],
            ),
            pytest.raises(TokenExchangeError) as exc_info,
        ):
            await service.validate_subject_token(
                db,
                subject_token="opaque",
                subject_token_type=unhandled,
                client=make_oauth2_client(),
            )

        assert exc_info.value.error == "invalid_request"
        assert "Unable to validate subject token" in exc_info.value.description
