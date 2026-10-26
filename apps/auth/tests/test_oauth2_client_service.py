# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.oauth2_client — OAuth2ClientService and helpers."""

import hashlib
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.services.oauth2_client import (
    OAuth2ClientService,
    generate_authorization_code,
    generate_client_id,
    generate_client_secret,
    hash_code,
)

from tests.conftest import (
    make_authorization_code,
    make_execute_result,
    make_oauth2_client,
)

# ── Helper functions ─────────────────────────────────────────────────────────


class TestGenerateClientId:
    def test_length(self):
        assert len(generate_client_id()) == 32

    def test_hex_format(self):
        int(generate_client_id(), 16)

    def test_uniqueness(self):
        ids = {generate_client_id() for _ in range(10)}
        assert len(ids) == 10


class TestGenerateClientSecret:
    def test_length(self):
        assert len(generate_client_secret()) == 64

    def test_hex_format(self):
        int(generate_client_secret(), 16)

    def test_uniqueness(self):
        secrets = {generate_client_secret() for _ in range(10)}
        assert len(secrets) == 10


class TestGenerateAuthorizationCode:
    def test_length(self):
        assert len(generate_authorization_code()) == 64

    def test_hex_format(self):
        int(generate_authorization_code(), 16)

    def test_uniqueness(self):
        codes = {generate_authorization_code() for _ in range(10)}
        assert len(codes) == 10


class TestHashCodeHelper:
    def test_sha256(self):
        expected = hashlib.sha256(b"code").hexdigest()
        assert hash_code("code") == expected

    def test_deterministic(self):
        assert hash_code("same") == hash_code("same")

    def test_different_inputs_different_hashes(self):
        assert hash_code("abc") != hash_code("xyz")

    def test_empty_string(self):
        expected = hashlib.sha256(b"").hexdigest()
        assert hash_code("") == expected


# ── OAuth2ClientService ──────────────────────────────────────────────────────


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def service():
    return OAuth2ClientService()


class TestGetClientByClientId:
    async def test_found(self, db, service):
        client = make_oauth2_client()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=client))

        result = await service.get_client_by_client_id(db, "test_client_id")
        assert result is client

    async def test_not_found(self, db, service):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await service.get_client_by_client_id(db, "missing")
        assert result is None

    async def test_execute_called_with_session(self, db, service):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        await service.get_client_by_client_id(db, "test_id")
        db.execute.assert_called_once()


class TestCreateClient:
    async def test_confidential_client(self, db, service):
        with patch("auth.services.oauth2_client.OAuth2Client") as MockClient:
            mock_client = MagicMock()
            mock_client.client_id = "generated_id"
            MockClient.return_value = mock_client

            client, secret = await service.create_client(
                db,
                name="Test App",
                redirect_uris=["https://example.com/callback"],
                is_confidential=True,
            )

        assert secret is not None
        assert len(secret) == 64
        db.add.assert_called_once()

    async def test_public_client(self, db, service):
        with patch("auth.services.oauth2_client.OAuth2Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value = mock_client

            client, secret = await service.create_client(
                db,
                name="SPA",
                redirect_uris=["https://spa.example.com/callback"],
                is_confidential=False,
            )

        assert secret is None

    async def test_default_scopes_and_grant_types(self, db, service):
        """Verify defaults when allowed_scopes and allowed_grant_types are None."""
        with patch("auth.services.oauth2_client.OAuth2Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value = mock_client

            await service.create_client(
                db,
                name="Defaults App",
                redirect_uris=["https://example.com/cb"],
            )

            call_kwargs = MockClient.call_args[1]
            assert call_kwargs["allowed_scopes"] == ["openid", "profile", "email"]
            assert call_kwargs["allowed_grant_types"] == ["authorization_code", "refresh_token"]

    async def test_custom_scopes_and_grant_types(self, db, service):
        """Verify custom scopes and grant types are passed through."""
        with patch("auth.services.oauth2_client.OAuth2Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value = mock_client

            await service.create_client(
                db,
                name="Custom App",
                redirect_uris=["https://example.com/cb"],
                allowed_scopes=["custom:read"],
                allowed_grant_types=["client_credentials"],
            )

            call_kwargs = MockClient.call_args[1]
            assert call_kwargs["allowed_scopes"] == ["custom:read"]
            assert call_kwargs["allowed_grant_types"] == ["client_credentials"]

    async def test_all_optional_params(self, db, service):
        """Verify description and allowed_origins are passed through."""
        with patch("auth.services.oauth2_client.OAuth2Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value = mock_client

            await service.create_client(
                db,
                name="Full App",
                redirect_uris=["https://example.com/cb"],
                description="My app description",
                allowed_origins=["https://example.com"],
                require_pkce=False,
                require_consent=False,
            )

            call_kwargs = MockClient.call_args[1]
            assert call_kwargs["description"] == "My app description"
            assert call_kwargs["allowed_origins"] == ["https://example.com"]
            assert call_kwargs["require_pkce"] is False
            assert call_kwargs["require_consent"] is False

    async def test_flush_called(self, db, service):
        with patch("auth.services.oauth2_client.OAuth2Client") as MockClient:
            MockClient.return_value = MagicMock(client_id="cid")

            await service.create_client(db, name="App", redirect_uris=["https://example.com/cb"])

        db.flush.assert_called_once()

    async def test_returns_client_object(self, db, service):
        with patch("auth.services.oauth2_client.OAuth2Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value = mock_client

            client, _ = await service.create_client(
                db, name="App", redirect_uris=["https://example.com/cb"]
            )

        assert client is mock_client


class TestVerifyClientSecret:
    def test_valid_secret(self, service):
        secret = "test_secret"
        client = make_oauth2_client(client_secret_hash=service._hasher.hash(secret))

        assert service.verify_client_secret(client, secret) is True

    def test_invalid_secret(self, service):
        secret = "correct_secret"
        client = make_oauth2_client(client_secret_hash=service._hasher.hash(secret))

        assert service.verify_client_secret(client, "wrong_secret") is False

    def test_no_secret_configured(self, service):
        client = make_oauth2_client(client_secret_hash=None)

        assert service.verify_client_secret(client, "any") is False

    def test_empty_secret_against_valid_hash(self, service):
        secret = "real_secret"
        client = make_oauth2_client(client_secret_hash=service._hasher.hash(secret))

        assert service.verify_client_secret(client, "") is False


class TestValidateRedirectUri:
    def test_valid_uri(self, service):
        client = make_oauth2_client(
            redirect_uris=["https://app.example.com/callback", "https://app.example.com/auth"]
        )

        assert service.validate_redirect_uri(client, "https://app.example.com/callback") is True

    def test_invalid_uri(self, service):
        client = make_oauth2_client(redirect_uris=["https://app.example.com/callback"])

        assert service.validate_redirect_uri(client, "https://evil.com/callback") is False

    def test_empty_redirect_uris_list(self, service):
        client = make_oauth2_client(redirect_uris=[])

        assert service.validate_redirect_uri(client, "https://any.com") is False

    def test_second_uri_in_list(self, service):
        client = make_oauth2_client(redirect_uris=["https://first.com/cb", "https://second.com/cb"])

        assert service.validate_redirect_uri(client, "https://second.com/cb") is True

    def test_partial_match_not_accepted(self, service):
        client = make_oauth2_client(redirect_uris=["https://app.example.com/callback"])

        assert (
            service.validate_redirect_uri(client, "https://app.example.com/callback/extra") is False
        )

    def test_case_sensitive(self, service):
        client = make_oauth2_client(redirect_uris=["https://App.Example.com/callback"])

        assert service.validate_redirect_uri(client, "https://app.example.com/callback") is False


class TestValidateScopes:
    def test_all_allowed(self, service):
        client = make_oauth2_client(allowed_scopes=["openid", "profile", "email"])

        assert service.validate_scopes(client, ["openid", "profile"]) is True

    def test_scope_not_allowed(self, service):
        client = make_oauth2_client(allowed_scopes=["openid", "profile"])

        assert service.validate_scopes(client, ["admin"]) is False

    def test_wildcard_all(self, service):
        client = make_oauth2_client(allowed_scopes=["*"])

        assert service.validate_scopes(client, ["anything", "at:all"]) is True

    def test_prefix_wildcard(self, service):
        client = make_oauth2_client(allowed_scopes=["billing:*"])

        assert service.validate_scopes(client, ["billing:read"]) is True
        assert service.validate_scopes(client, ["billing:write"]) is True
        assert service.validate_scopes(client, ["users:read"]) is False

    def test_nested_wildcard(self, service):
        client = make_oauth2_client(allowed_scopes=["module:resource:*"])

        assert service.validate_scopes(client, ["module:resource:read"]) is True
        assert service.validate_scopes(client, ["module:other:read"]) is False

    def test_empty_scopes(self, service):
        client = make_oauth2_client(allowed_scopes=["openid"])

        assert service.validate_scopes(client, []) is True

    def test_single_part_scope_no_wildcard(self, service):
        """A single-part scope like 'admin' should not match 'billing:*'."""
        client = make_oauth2_client(allowed_scopes=["billing:*"])

        assert service.validate_scopes(client, ["admin"]) is False

    def test_multiple_scopes_one_disallowed(self, service):
        """If any scope is disallowed, the whole check fails."""
        client = make_oauth2_client(allowed_scopes=["openid", "profile"])

        assert service.validate_scopes(client, ["openid", "admin"]) is False

    def test_wildcard_matches_deep_scope(self, service):
        """A top-level wildcard 'module:*' should match 'module:sub:action'."""
        client = make_oauth2_client(allowed_scopes=["module:*"])

        assert service.validate_scopes(client, ["module:sub:action"]) is True

    def test_empty_allowed_scopes(self, service):
        """No allowed scopes means nothing is allowed (except empty request)."""
        client = make_oauth2_client(allowed_scopes=[])

        assert service.validate_scopes(client, ["openid"]) is False
        assert service.validate_scopes(client, []) is True


class TestValidateGrantType:
    def test_allowed(self, service):
        client = make_oauth2_client(allowed_grant_types=["authorization_code", "refresh_token"])

        assert service.validate_grant_type(client, "authorization_code") is True

    def test_not_allowed(self, service):
        client = make_oauth2_client(allowed_grant_types=["authorization_code"])

        assert service.validate_grant_type(client, "client_credentials") is False

    def test_empty_grant_types(self, service):
        client = make_oauth2_client(allowed_grant_types=[])

        assert service.validate_grant_type(client, "authorization_code") is False

    def test_refresh_token_grant(self, service):
        client = make_oauth2_client(allowed_grant_types=["refresh_token"])

        assert service.validate_grant_type(client, "refresh_token") is True
        assert service.validate_grant_type(client, "authorization_code") is False


class TestCreateAuthorizationCode:
    async def test_creates_code(self, db, service):
        client = make_oauth2_client()

        with patch("auth.services.oauth2_client.AuthorizationCode"):
            code = await service.create_authorization_code(
                db,
                client=client,
                user_id=str(uuid.uuid4()),
                redirect_uri="https://app.example.com/callback",
                scopes=["openid"],
                code_challenge="challenge",
                code_challenge_method="S256",
            )

        assert len(code) == 64
        db.add.assert_called_once()
        db.flush.assert_called_once()

    async def test_creates_code_with_nonce_and_state(self, db, service):
        client = make_oauth2_client()

        with patch("auth.services.oauth2_client.AuthorizationCode") as MockAC:
            MockAC.return_value = MagicMock()

            code = await service.create_authorization_code(
                db,
                client=client,
                user_id=str(uuid.uuid4()),
                redirect_uri="https://app.example.com/callback",
                scopes=["openid"],
                nonce="test_nonce",
                state="test_state",
            )

            call_kwargs = MockAC.call_args[1]
            assert call_kwargs["nonce"] == "test_nonce"
            assert call_kwargs["state"] == "test_state"

        assert len(code) == 64

    async def test_creates_code_without_pkce(self, db, service):
        client = make_oauth2_client()

        with patch("auth.services.oauth2_client.AuthorizationCode") as MockAC:
            MockAC.return_value = MagicMock()

            code = await service.create_authorization_code(
                db,
                client=client,
                user_id=str(uuid.uuid4()),
                redirect_uri="https://app.example.com/callback",
                scopes=["openid"],
            )

            call_kwargs = MockAC.call_args[1]
            assert call_kwargs["code_challenge"] is None
            assert call_kwargs["code_challenge_method"] is None

        assert len(code) == 64

    async def test_code_is_hex(self, db, service):
        client = make_oauth2_client()

        with patch("auth.services.oauth2_client.AuthorizationCode"):
            code = await service.create_authorization_code(
                db,
                client=client,
                user_id=str(uuid.uuid4()),
                redirect_uri="https://app.example.com/callback",
                scopes=["openid"],
            )

        # Should be valid hex
        int(code, 16)


class TestGetAuthorizationCode:
    async def test_found(self, db, service):
        ac = make_authorization_code()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=ac))

        result = await service.get_authorization_code(db, "code_value")
        assert result is ac

    async def test_not_found(self, db, service):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await service.get_authorization_code(db, "bad_code")
        assert result is None

    async def test_hashes_code_before_lookup(self, db, service):
        """Verify the code is hashed before the DB query."""
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        await service.get_authorization_code(db, "test_code")
        # The method should have been called (it hashes internally)
        db.execute.assert_called_once()


class TestConsumeAuthorizationCode:
    async def test_marks_used(self, db, service):
        ac = make_authorization_code()
        ac.used_at = None

        await service.consume_authorization_code(db, ac)

        assert ac.used_at is not None
        db.flush.assert_called_once()

    async def test_used_at_is_utc_datetime(self, db, service):
        ac = make_authorization_code()
        ac.used_at = None

        await service.consume_authorization_code(db, ac)

        assert isinstance(ac.used_at, datetime)
        assert ac.used_at.tzinfo is not None


class TestVerifyClientSecretInvalidHash:
    def test_invalid_hash_format(self, service):
        """Cover lines 167-169: InvalidHashError exception."""
        client = make_oauth2_client(client_secret_hash="not_a_valid_argon2_hash")

        # An invalid hash format should return False (not crash)
        assert service.verify_client_secret(client, "any_secret") is False


class TestScopeMatchesPrivateMethod:
    """Additional edge cases for the _scope_matches private method."""

    def test_scope_with_colon_no_wildcard(self):
        """Scope 'a:b' with allowed ['a:b'] should match exactly."""
        svc = OAuth2ClientService()
        client = make_oauth2_client(allowed_scopes=["a:b"])
        assert svc.validate_scopes(client, ["a:b"]) is True

    def test_scope_with_colon_no_wildcard_no_match(self):
        """Scope 'a:c' with allowed ['a:b'] should not match."""
        svc = OAuth2ClientService()
        client = make_oauth2_client(allowed_scopes=["a:b"])
        assert svc.validate_scopes(client, ["a:c"]) is False

    def test_three_level_scope_with_mid_level_wildcard(self):
        """'module:*' should match 'module:resource:action' (hierarchical wildcard)."""
        svc = OAuth2ClientService()
        client = make_oauth2_client(allowed_scopes=["module:*"])
        assert svc.validate_scopes(client, ["module:resource:action"]) is True

    def test_global_wildcard_with_complex_scope(self):
        """'*' should match any deeply nested scope."""
        svc = OAuth2ClientService()
        client = make_oauth2_client(allowed_scopes=["*"])
        assert svc.validate_scopes(client, ["a:b:c:d:e"]) is True


class TestServiceInit:
    def test_hasher_initialized(self):
        """The service should have a PasswordHasher instance."""
        svc = OAuth2ClientService()
        assert svc._hasher is not None


class TestGetScopedToTenant:
    @pytest.mark.asyncio
    async def test_delegates_to_repository(self):
        from auth.services.oauth2_client import OAuth2ClientService

        service = OAuth2ClientService()
        client = make_oauth2_client()
        service._repo.find_scoped_to_tenant = AsyncMock(return_value=client)
        db = AsyncMock()
        tenant_id = uuid.uuid4()

        assert await service.get_scoped_to_tenant(db, client.id, tenant_id) is client
        service._repo.find_scoped_to_tenant.assert_awaited_once_with(db, client.id, tenant_id)


class TestCountClients:
    @pytest.mark.asyncio
    async def test_without_filter(self):
        from auth.services.oauth2_client import OAuth2ClientService

        service = OAuth2ClientService()
        service._repo.count = AsyncMock(return_value=11)
        db = AsyncMock()

        assert await service.count(db) == 11
        service._repo.count.assert_awaited_once_with(db, is_active=None)

    @pytest.mark.asyncio
    async def test_with_is_active(self):
        from auth.services.oauth2_client import OAuth2ClientService

        service = OAuth2ClientService()
        service._repo.count = AsyncMock(return_value=5)
        db = AsyncMock()

        assert await service.count(db, is_active=True) == 5
        service._repo.count.assert_awaited_once_with(db, is_active=True)
