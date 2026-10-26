# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.federation — FederationService."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.services.federation import (
    FederatedUserInfo,
    FederationService,
    FederationState,
    OIDCDiscoveryDocument,
    federation_service,
)

from tests.conftest import make_execute_result


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def service():
    return FederationService()


def _make_idp(**kwargs):
    idp = MagicMock()
    idp.id = kwargs.get("id", uuid.uuid4())
    idp.name = kwargs.get("name", "Test IdP")
    idp.provider_type = kwargs.get("provider_type", MagicMock())
    idp.client_id = kwargs.get("client_id", "idp_client_id")
    idp.client_secret_encrypted = kwargs.get("client_secret_encrypted")
    idp.scopes = kwargs.get("scopes")
    idp.authorization_endpoint = kwargs.get("authorization_endpoint")
    idp.token_endpoint = kwargs.get("token_endpoint")
    idp.userinfo_endpoint = kwargs.get("userinfo_endpoint")
    idp.discovery_url = kwargs.get("discovery_url")
    idp.attribute_mapping = kwargs.get("attribute_mapping")
    idp.auto_provision = kwargs.get("auto_provision", True)
    idp.allow_linking = kwargs.get("allow_linking", True)
    return idp


# ── dataclasses ─────────────────────────────────────────────────────────────


class TestDataclasses:
    def test_oidc_discovery_document(self):
        doc = OIDCDiscoveryDocument(
            issuer="https://issuer.example.com",
            authorization_endpoint="https://auth.example.com/authorize",
            token_endpoint="https://auth.example.com/token",
            userinfo_endpoint="https://auth.example.com/userinfo",
            jwks_uri="https://auth.example.com/.well-known/jwks.json",
        )
        assert doc.issuer == "https://issuer.example.com"
        assert doc.scopes_supported is None

    def test_federation_state(self):
        state = FederationState(
            tenant_slug="test",
            idp_id="idp-1",
            original_state="state",
            redirect_uri="https://app.example.com/callback",
            nonce="nonce",
            code_verifier="verifier",
        )
        assert state.tenant_slug == "test"
        assert state.code_verifier == "verifier"

    def test_federated_user_info(self):
        info = FederatedUserInfo(
            subject="123",
            email="test@example.com",
            email_verified=True,
            name="Test User",
            given_name="Test",
            family_name="User",
            picture="https://example.com/pic.jpg",
            username="testuser",
            raw_claims={"sub": "123"},
        )
        assert info.subject == "123"
        assert info.email_verified is True


# ── get_tenant_identity_providers ───────────────────────────────────────────


class TestGetTenantIdentityProviders:
    @pytest.mark.asyncio
    async def test_returns_providers(self, db, service):
        idp1 = MagicMock()
        idp2 = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=[idp1, idp2]))
        result = await service.get_tenant_identity_providers(db, "test-tenant")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_empty(self, db, service):
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=[]))
        result = await service.get_tenant_identity_providers(db, "test-tenant")
        assert result == []


# ── get_identity_provider ───────────────────────────────────────────────────


class TestGetIdentityProvider:
    @pytest.mark.asyncio
    async def test_found(self, db, service):
        idp = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=idp))
        result = await service.get_identity_provider(db, "idp-1")
        assert result is idp

    @pytest.mark.asyncio
    async def test_not_found(self, db, service):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        result = await service.get_identity_provider(db, "missing")
        assert result is None


# ── fetch_oidc_discovery ────────────────────────────────────────────────────


class TestFetchOidcDiscovery:
    @pytest.mark.asyncio
    async def test_success(self, service):
        data = {
            "issuer": "https://issuer.example.com",
            "authorization_endpoint": "https://auth/authorize",
            "token_endpoint": "https://auth/token",
            "userinfo_endpoint": "https://auth/userinfo",
            "jwks_uri": "https://auth/jwks",
            "scopes_supported": ["openid"],
        }
        mock_response = MagicMock()
        mock_response.json.return_value = data
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get.return_value = mock_response

        with patch("auth.services.federation.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await service.fetch_oidc_discovery(
                "https://issuer/.well-known/openid-configuration"
            )

        assert isinstance(result, OIDCDiscoveryDocument)
        assert result.issuer == "https://issuer.example.com"


# ── get_authorization_url ───────────────────────────────────────────────────


class TestGetAuthorizationUrl:
    @pytest.mark.asyncio
    async def test_basic(self, service):
        from auth.db.models.tenant import IdentityProviderType

        idp = _make_idp(
            provider_type=IdentityProviderType.GOOGLE,
            scopes=["openid", "profile"],
        )
        service._get_authorization_endpoint = AsyncMock(
            return_value="https://accounts.google.com/o/oauth2/auth"
        )
        url = await service.get_authorization_url(
            idp, "https://app.example.com/callback", "state123", "nonce456"
        )
        assert "client_id=idp_client_id" in url
        assert "state=state123" in url
        assert "nonce=nonce456" in url

    @pytest.mark.asyncio
    async def test_github_no_nonce(self, service):
        from auth.db.models.tenant import IdentityProviderType

        idp = _make_idp(provider_type=IdentityProviderType.GITHUB)
        service._get_authorization_endpoint = AsyncMock(
            return_value="https://github.com/login/oauth/authorize"
        )
        url = await service.get_authorization_url(
            idp, "https://app.example.com/callback", "state", "nonce"
        )
        assert "nonce" not in url

    @pytest.mark.asyncio
    async def test_with_pkce(self, service):
        from auth.db.models.tenant import IdentityProviderType

        idp = _make_idp(provider_type=IdentityProviderType.GOOGLE)
        service._get_authorization_endpoint = AsyncMock(return_value="https://auth/authorize")
        url = await service.get_authorization_url(
            idp, "https://callback", "state", "nonce", code_verifier="verifier123"
        )
        assert "code_challenge=" in url
        assert "code_challenge_method=S256" in url

    @pytest.mark.asyncio
    async def test_default_scopes(self, service):
        from auth.db.models.tenant import IdentityProviderType

        idp = _make_idp(provider_type=IdentityProviderType.GOOGLE, scopes=None)
        service._get_authorization_endpoint = AsyncMock(return_value="https://auth/authorize")
        url = await service.get_authorization_url(idp, "https://cb", "s", "n")
        assert "openid" in url


# ── exchange_code_for_tokens ────────────────────────────────────────────────


class TestExchangeCodeForTokens:
    @pytest.mark.asyncio
    async def test_success(self, service):
        from auth.db.models.tenant import IdentityProviderType

        idp = _make_idp(
            provider_type=IdentityProviderType.GOOGLE,
            client_secret_encrypted=b"encrypted",
        )
        service._get_token_endpoint = AsyncMock(return_value="https://auth/token")

        token_data = {"access_token": "at", "id_token": "idt"}
        mock_response = MagicMock()
        mock_response.json.return_value = token_data
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response

        with (
            patch("auth.services.federation.httpx.AsyncClient") as MockClient,
            patch("auth.services.federation.decrypt_value", return_value="secret"),
        ):
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await service.exchange_code_for_tokens(
                idp, "code123", "https://callback", code_verifier="verifier"
            )
        assert result["access_token"] == "at"

    @pytest.mark.asyncio
    async def test_no_secret(self, service):
        from auth.db.models.tenant import IdentityProviderType

        idp = _make_idp(
            provider_type=IdentityProviderType.GITHUB,
            client_secret_encrypted=None,
        )
        service._get_token_endpoint = AsyncMock(return_value="https://auth/token")

        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": "at"}
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response

        with patch("auth.services.federation.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await service.exchange_code_for_tokens(idp, "code", "https://callback")
        assert result["access_token"] == "at"


# ── get_user_info ───────────────────────────────────────────────────────────


class TestGetUserInfo:
    @pytest.mark.asyncio
    async def test_oidc_with_id_token(self, service):
        from auth.db.models.tenant import IdentityProviderType

        idp = _make_idp(provider_type=IdentityProviderType.GOOGLE)
        service._get_userinfo_endpoint = AsyncMock(return_value=None)

        with patch(
            "auth.services.federation.jwt.decode",
            return_value={
                "sub": "user-123",
                "email": "test@example.com",
                "email_verified": True,
                "name": "Test",
            },
        ):
            result = await service.get_user_info(idp, "access_token", id_token="idt")
        assert result.subject == "user-123"
        assert result.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_oidc_with_userinfo(self, service):
        from auth.db.models.tenant import IdentityProviderType

        idp = _make_idp(provider_type=IdentityProviderType.GOOGLE, attribute_mapping=None)
        service._get_userinfo_endpoint = AsyncMock(return_value="https://auth/userinfo")

        userinfo_response = MagicMock()
        userinfo_response.status_code = 200
        userinfo_response.json.return_value = {
            "sub": "user-456",
            "email": "user@example.com",
            "name": "User",
        }

        mock_http = AsyncMock()
        mock_http.get.return_value = userinfo_response

        with (
            patch("auth.services.federation.jwt.decode", return_value={}),
            patch("auth.services.federation.httpx.AsyncClient") as MockClient,
        ):
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await service.get_user_info(idp, "access_token", id_token="idt")
        assert result.subject == "user-456"

    @pytest.mark.asyncio
    async def test_github_provider(self, service):
        from auth.db.models.tenant import IdentityProviderType

        idp = _make_idp(provider_type=IdentityProviderType.GITHUB)
        service._get_userinfo_endpoint = AsyncMock(return_value=None)
        service._get_github_user_info = AsyncMock(
            return_value=FederatedUserInfo(
                subject="gh-123",
                email="gh@example.com",
                email_verified=True,
                name="GH User",
                given_name="GH",
                family_name="User",
                picture=None,
                username="ghuser",
                raw_claims={},
            )
        )
        result = await service.get_user_info(idp, "access_token")
        assert result.subject == "gh-123"


# ── find_or_create_user ─────────────────────────────────────────────────────


class TestFindOrCreateUser:
    @pytest.mark.asyncio
    async def test_existing_federated_identity(self, db, service):
        fed_id = MagicMock()
        fed_id.user_id = uuid.uuid4()
        user = MagicMock()

        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=fed_id),  # find fed identity
                make_execute_result(scalar_value=user),  # find user by id
            ]
        )

        user_info = FederatedUserInfo(
            subject="ext-123",
            email="test@example.com",
            email_verified=True,
            name="Test",
            given_name="T",
            family_name="U",
            picture=None,
            username="tu",
            raw_claims={},
        )
        idp = _make_idp()
        result_user, result_fed, is_new = await service.find_or_create_user(
            db, idp, user_info, "test-tenant"
        )
        assert result_user is user
        assert is_new is False

    @pytest.mark.asyncio
    async def test_auto_provision_disabled(self, db, service):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        idp = _make_idp(auto_provision=False)
        user_info = FederatedUserInfo(
            subject="ext-1",
            email="t@e.com",
            email_verified=True,
            name="T",
            given_name="T",
            family_name="U",
            picture=None,
            username="t",
            raw_claims={},
        )
        with pytest.raises(ValueError, match="Auto-provisioning is disabled"):
            await service.find_or_create_user(db, idp, user_info, "test")


# ── _get_authorization_endpoint ─────────────────────────────────────────────


class TestGetAuthorizationEndpoint:
    @pytest.mark.asyncio
    async def test_explicit_endpoint(self, service):
        idp = _make_idp(authorization_endpoint="https://auth/authorize")
        result = await service._get_authorization_endpoint(idp)
        assert result == "https://auth/authorize"

    @pytest.mark.asyncio
    async def test_from_discovery_url(self, service):
        idp = _make_idp(discovery_url="https://issuer/.well-known/openid-configuration")
        doc = OIDCDiscoveryDocument(
            issuer="https://issuer",
            authorization_endpoint="https://issuer/authorize",
            token_endpoint="https://issuer/token",
            userinfo_endpoint=None,
            jwks_uri="https://issuer/jwks",
        )
        service.fetch_oidc_discovery = AsyncMock(return_value=doc)
        result = await service._get_authorization_endpoint(idp)
        assert result == "https://issuer/authorize"

    @pytest.mark.asyncio
    async def test_from_provider_config_discovery(self, service):
        from auth.db.models.tenant import IdentityProviderType

        idp = _make_idp(provider_type=IdentityProviderType.GOOGLE)
        doc = OIDCDiscoveryDocument(
            issuer="https://google",
            authorization_endpoint="https://google/authorize",
            token_endpoint="https://google/token",
            userinfo_endpoint=None,
            jwks_uri="https://google/jwks",
        )
        service.fetch_oidc_discovery = AsyncMock(return_value=doc)
        result = await service._get_authorization_endpoint(idp)
        assert result == "https://google/authorize"

    @pytest.mark.asyncio
    async def test_from_provider_config_static(self, service):
        from auth.db.models.tenant import IdentityProviderType

        idp = _make_idp(provider_type=IdentityProviderType.GITHUB)
        result = await service._get_authorization_endpoint(idp)
        assert "github.com" in result

    @pytest.mark.asyncio
    async def test_no_endpoint_raises(self, service):
        idp = _make_idp(provider_type=MagicMock())
        with pytest.raises(ValueError, match="Cannot determine authorization"):
            await service._get_authorization_endpoint(idp)


# ── _get_token_endpoint ─────────────────────────────────────────────────────


class TestGetTokenEndpoint:
    @pytest.mark.asyncio
    async def test_explicit(self, service):
        idp = _make_idp(token_endpoint="https://auth/token")
        result = await service._get_token_endpoint(idp)
        assert result == "https://auth/token"

    @pytest.mark.asyncio
    async def test_from_provider_config_static(self, service):
        from auth.db.models.tenant import IdentityProviderType

        idp = _make_idp(provider_type=IdentityProviderType.GITHUB)
        result = await service._get_token_endpoint(idp)
        assert "github.com" in result

    @pytest.mark.asyncio
    async def test_no_endpoint_raises(self, service):
        idp = _make_idp(provider_type=MagicMock())
        with pytest.raises(ValueError, match="Cannot determine token"):
            await service._get_token_endpoint(idp)


# ── _get_userinfo_endpoint ──────────────────────────────────────────────────


class TestGetUserinfoEndpoint:
    @pytest.mark.asyncio
    async def test_explicit(self, service):
        idp = _make_idp(userinfo_endpoint="https://auth/userinfo")
        result = await service._get_userinfo_endpoint(idp)
        assert result == "https://auth/userinfo"

    @pytest.mark.asyncio
    async def test_none(self, service):
        idp = _make_idp(provider_type=MagicMock())
        result = await service._get_userinfo_endpoint(idp)
        assert result is None


# ── _apply_attribute_mapping ────────────────────────────────────────────────


class TestApplyAttributeMapping:
    def test_no_mapping(self, service):
        claims = {"sub": "1", "mail": "test@example.com"}
        result = service._apply_attribute_mapping(claims, None)
        assert result == claims

    def test_mapping(self, service):
        claims = {"sub": "1", "mail": "test@example.com", "displayName": "Test"}
        mapping = {"mail": "email", "displayName": "name"}
        result = service._apply_attribute_mapping(claims, mapping)
        assert result["email"] == "test@example.com"
        assert result["name"] == "Test"

    def test_no_override_existing(self, service):
        claims = {"sub": "1", "email": "existing@example.com", "mail": "other@example.com"}
        mapping = {"mail": "email"}
        result = service._apply_attribute_mapping(claims, mapping)
        assert result["email"] == "existing@example.com"


# ── _generate_code_challenge ────────────────────────────────────────────────


class TestGenerateCodeChallenge:
    def test_s256(self, service):
        challenge = service._generate_code_challenge("test_verifier")
        assert isinstance(challenge, str)
        assert len(challenge) > 0


# ── static helpers ──────────────────────────────────────────────────────────


class TestStaticHelpers:
    def test_generate_state(self):
        state = FederationService.generate_state()
        assert isinstance(state, str)
        assert len(state) > 20

    def test_generate_nonce(self):
        nonce = FederationService.generate_nonce()
        assert isinstance(nonce, str)

    def test_generate_code_verifier(self):
        verifier = FederationService.generate_code_verifier()
        assert isinstance(verifier, str)
        assert len(verifier) > 40


# ── singleton ───────────────────────────────────────────────────────────────


class TestSingleton:
    def test_federation_service_is_instance(self):
        assert isinstance(federation_service, FederationService)


# ── list_federated_identities_for_user_in_tenant ────────────────────────────


class TestListFederatedIdentitiesForUserInTenant:
    @pytest.mark.asyncio
    async def test_delegates_to_repository(self, db, service):
        identities = [MagicMock(), MagicMock()]
        service._repo.list_identities_for_user_in_tenant = AsyncMock(return_value=identities)

        user_id, tenant_id = uuid.uuid4(), uuid.uuid4()
        result = await service.list_federated_identities_for_user_in_tenant(db, user_id, tenant_id)

        assert result == identities
        service._repo.list_identities_for_user_in_tenant.assert_awaited_once_with(
            db, user_id, tenant_id
        )


# ── get_user_info: non-200 userinfo response ────────────────────────────────


class TestGetUserInfoUserinfoFails:
    @pytest.mark.asyncio
    async def test_non_200_userinfo_keeps_id_token_claims(self, service):
        idp = _make_idp(attribute_mapping=None)
        service._get_userinfo_endpoint = AsyncMock(return_value="https://idp/userinfo")

        response = MagicMock()
        response.status_code = 403
        client = MagicMock()
        client.get = AsyncMock(return_value=response)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        id_token_claims = {"sub": "ext-1", "email": "a@b.test"}
        with (
            patch("auth.services.federation.httpx.AsyncClient", return_value=client),
            patch("auth.services.federation.jwt.decode", return_value=id_token_claims),
        ):
            result = await service.get_user_info(idp, "access_token", id_token="id.token")

        assert result.subject == "ext-1"
        assert result.email == "a@b.test"


# ── find_or_create_user: JIT provisioning ───────────────────────────────────


def _user_info(email="new@example.com", email_verified=True):
    return FederatedUserInfo(
        subject="ext-new",
        email=email,
        email_verified=email_verified,
        name="New User",
        given_name="New",
        family_name="User",
        picture="https://cdn/pic.png",
        username="newuser",
        raw_claims={"sub": "ext-new"},
    )


class TestFindOrCreateUserDanglingIdentity:
    @pytest.mark.asyncio
    async def test_missing_user_raises(self, db, service):
        fed_id = MagicMock()
        fed_id.user_id = uuid.uuid4()
        service._repo.find_identity_by_subject = AsyncMock(return_value=fed_id)
        service._repo.find_user_by_id = AsyncMock(return_value=None)

        with pytest.raises(RuntimeError, match="references missing user"):
            await service.find_or_create_user(db, _make_idp(), _user_info(), "acme")


class TestFindOrCreateUserJitProvisioning:
    """The full just-in-time provisioning path (no pre-existing federated identity)."""

    def _prime(self, service, *, existing_user=None, tenant=None, membership=None):
        service._repo.find_identity_by_subject = AsyncMock(return_value=None)
        service._repo.find_user_by_email = AsyncMock(return_value=existing_user)
        service._repo.add = AsyncMock()
        service._repo.find_tenant_by_slug = AsyncMock(return_value=tenant)
        service._repo.find_tenant_membership = AsyncMock(return_value=membership)
        service._user_repo.add = AsyncMock()
        service._user_repo.add_email = AsyncMock()
        service._user_repo.add_profile = AsyncMock()
        service._tenant_repo.add_member = AsyncMock()

    @pytest.mark.asyncio
    async def test_links_to_existing_user_by_email(self, db, service):
        existing = MagicMock()
        self._prime(service, existing_user=existing)

        user, fed, is_new = await service.find_or_create_user(db, _make_idp(), _user_info(), "acme")

        assert user is existing
        assert is_new is False
        service._user_repo.add.assert_not_awaited()
        service._repo.add.assert_awaited_once_with(db, fed)
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_creates_user_email_and_profile(self, db, service):
        self._prime(service)

        user, _fed, is_new = await service.find_or_create_user(
            db, _make_idp(), _user_info(), "acme"
        )

        assert is_new is True
        service._user_repo.add.assert_awaited_once()
        service._user_repo.add_email.assert_awaited_once()
        added_email = service._user_repo.add_email.await_args[0][1]
        assert added_email.email == "new@example.com"
        assert added_email.is_verified is True
        assert added_email.verified_at is not None
        service._user_repo.add_profile.assert_awaited_once()
        assert user is not None

    @pytest.mark.asyncio
    async def test_unverified_email_has_no_verified_at(self, db, service):
        self._prime(service)

        await service.find_or_create_user(db, _make_idp(), _user_info(email_verified=False), "acme")

        added_email = service._user_repo.add_email.await_args[0][1]
        assert added_email.is_verified is False
        assert added_email.verified_at is None

    @pytest.mark.asyncio
    async def test_no_email_skips_email_row(self, db, service):
        self._prime(service)

        await service.find_or_create_user(db, _make_idp(), _user_info(email=None), "acme")

        service._user_repo.add_email.assert_not_awaited()
        service._user_repo.add_profile.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_linking_disabled_skips_email_lookup(self, db, service):
        self._prime(service, existing_user=MagicMock())

        _user, _fed, is_new = await service.find_or_create_user(
            db, _make_idp(allow_linking=False), _user_info(), "acme"
        )

        assert is_new is True
        service._repo.find_user_by_email.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_adds_membership_with_default_role(self, db, service):
        tenant = MagicMock()
        tenant.id = uuid.uuid4()
        self._prime(service, tenant=tenant)

        default_role = MagicMock()
        default_role.id = uuid.uuid4()
        default_role.name = "member"

        with (
            patch(
                "auth.services.federation.tenant_role_service.resolve_default_registration_role",
                AsyncMock(return_value=default_role),
            ),
            patch("auth.services.federation.dispatch_webhook_event", AsyncMock()) as mock_dispatch,
        ):
            await service.find_or_create_user(db, _make_idp(), _user_info(), "acme")

        service._tenant_repo.add_member.assert_awaited_once()
        mock_dispatch.assert_awaited_once()
        from auth.db.models.tenant import WebhookEvent

        assert mock_dispatch.await_args.kwargs["event"] == WebhookEvent.MEMBER_ADDED

    @pytest.mark.asyncio
    async def test_no_default_role_skips_membership(self, db, service):
        tenant = MagicMock()
        tenant.id = uuid.uuid4()
        self._prime(service, tenant=tenant)

        with patch(
            "auth.services.federation.tenant_role_service.resolve_default_registration_role",
            AsyncMock(return_value=None),
        ):
            await service.find_or_create_user(db, _make_idp(), _user_info(), "acme")

        service._tenant_repo.add_member.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_existing_membership_is_left_alone(self, db, service):
        tenant = MagicMock()
        tenant.id = uuid.uuid4()
        self._prime(service, tenant=tenant, membership=MagicMock())

        await service.find_or_create_user(db, _make_idp(), _user_info(), "acme")

        service._tenant_repo.add_member.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_tenant_skips_membership(self, db, service):
        self._prime(service, tenant=None)

        await service.find_or_create_user(db, _make_idp(), _user_info(), "unknown")

        service._repo.find_tenant_membership.assert_not_awaited()
        service._tenant_repo.add_member.assert_not_awaited()


# ── endpoint resolution via discovery ───────────────────────────────────────


class TestEndpointResolutionViaDiscovery:
    def _discovery(self):
        return OIDCDiscoveryDocument(
            issuer="https://idp",
            authorization_endpoint="https://idp/authorize",
            token_endpoint="https://idp/token",
            userinfo_endpoint="https://idp/userinfo",
            jwks_uri="https://idp/jwks",
        )

    @pytest.mark.asyncio
    async def test_token_endpoint_from_discovery_url(self, service):
        idp = _make_idp(discovery_url="https://idp/.well-known/openid-configuration")
        service.fetch_oidc_discovery = AsyncMock(return_value=self._discovery())

        assert await service._get_token_endpoint(idp) == "https://idp/token"

    @pytest.mark.asyncio
    async def test_token_endpoint_from_provider_config_discovery(self, service):
        from auth.db.models.tenant import IdentityProviderType

        idp = _make_idp(provider_type=IdentityProviderType.GOOGLE)
        service.fetch_oidc_discovery = AsyncMock(return_value=self._discovery())

        assert await service._get_token_endpoint(idp) == "https://idp/token"

    @pytest.mark.asyncio
    async def test_userinfo_endpoint_from_discovery_url(self, service):
        idp = _make_idp(discovery_url="https://idp/.well-known/openid-configuration")
        service.fetch_oidc_discovery = AsyncMock(return_value=self._discovery())

        assert await service._get_userinfo_endpoint(idp) == "https://idp/userinfo"

    @pytest.mark.asyncio
    async def test_userinfo_endpoint_from_provider_config_discovery(self, service):
        from auth.db.models.tenant import IdentityProviderType

        idp = _make_idp(provider_type=IdentityProviderType.GOOGLE)
        service.fetch_oidc_discovery = AsyncMock(return_value=self._discovery())

        assert await service._get_userinfo_endpoint(idp) == "https://idp/userinfo"


# ── _get_github_user_info ───────────────────────────────────────────────────


class TestGetGithubUserInfo:
    def _client(self, user_data, emails, emails_status=200):
        user_response = MagicMock()
        user_response.json.return_value = user_data
        user_response.raise_for_status = MagicMock()

        email_response = MagicMock()
        email_response.status_code = emails_status
        email_response.json.return_value = emails

        client = MagicMock()
        client.get = AsyncMock(side_effect=[user_response, email_response])
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        return client

    @pytest.mark.asyncio
    async def test_full_profile(self, service):
        client = self._client(
            {"id": 42, "name": "Ada Lovelace", "login": "ada", "avatar_url": "https://a/v.png"},
            [
                {"email": "other@example.com", "primary": False, "verified": True},
                {"email": "ada@example.com", "primary": True, "verified": True},
            ],
        )

        with patch("auth.services.federation.httpx.AsyncClient", return_value=client):
            info = await service._get_github_user_info("gho_token", {})

        assert info.subject == "42"
        assert info.email == "ada@example.com"
        assert info.email_verified is True
        assert info.given_name == "Ada"
        assert info.family_name == "Lovelace"
        assert info.username == "ada"

    @pytest.mark.asyncio
    async def test_single_word_name_has_no_family_name(self, service):
        client = self._client({"id": 7, "name": "Ada", "login": "ada"}, [])

        with patch("auth.services.federation.httpx.AsyncClient", return_value=client):
            info = await service._get_github_user_info("gho_token", {})

        assert info.given_name == "Ada"
        assert info.family_name is None
        assert info.email is None
        assert info.email_verified is False

    @pytest.mark.asyncio
    async def test_missing_name_and_failed_email_lookup(self, service):
        client = self._client({"id": 9, "login": "anon"}, [], emails_status=403)

        with patch("auth.services.federation.httpx.AsyncClient", return_value=client):
            info = await service._get_github_user_info("gho_token", {})

        assert info.subject == "9"
        assert info.email is None
