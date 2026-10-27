# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.bootstrap — the idempotent bootstrap of a deployment."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from auth.config import Settings
from auth.db.models.oauth2 import OAuth2Client
from auth.db.models.rbac import ADMIN_SCOPES, DEFAULT_ROLES
from auth.db.models.tenant import Tenant, TenantBranding, TenantTrustMode
from auth.services.bootstrap import (
    BRANDING_FIELDS,
    BootstrapError,
    BootstrapOptions,
    bootstrap,
)

from tests.fakes_catalog import FakeCatalogRepository


class FakeBootstrapRepository:
    """Same interface as ``BootstrapRepository``, over attributes."""

    def __init__(self):
        self.tenants: list[Tenant] = []
        self.branding: dict[uuid.UUID, TenantBranding] = {}
        self.roles: dict[tuple[uuid.UUID, str], SimpleNamespace] = {}
        self.clients: dict[str, OAuth2Client] = {}
        self.orphans = 0
        self.open_sources = 0
        self.missing_members = 0
        self.added_members: list[tuple[uuid.UUID, uuid.UUID]] = []

    async def find_platform_tenant(self, db):
        return next((t for t in self.tenants if t.is_platform), None)

    async def find_tenant_by_slug(self, db, slug):
        return next((t for t in self.tenants if t.slug == slug), None)

    async def find_branding(self, db, tenant_id):
        return self.branding.get(tenant_id)

    async def find_role(self, db, tenant_id, name):
        return self.roles.get((tenant_id, name))

    async def find_client(self, db, client_id):
        return self.clients.get(client_id)

    async def add(self, db, instance):
        if isinstance(instance, Tenant):
            self.tenants.append(instance)
        elif isinstance(instance, TenantBranding):
            self.branding[instance.tenant_id] = instance
        elif isinstance(instance, OAuth2Client):
            self.clients[instance.client_id] = instance

    async def register_orphan_users(self, db, tenant_id):
        count, self.orphans = self.orphans, 0
        return count

    async def trust_platform_in_open_sources(self, db, tenant_id):
        count, self.open_sources = self.open_sources, 0
        return count

    async def add_missing_members(self, db, tenant_id, role_id):
        count, self.missing_members = self.missing_members, 0
        self.added_members.append((tenant_id, role_id))
        return count


@pytest.fixture
def repo():
    return FakeBootstrapRepository()


@pytest.fixture
def roles_service():
    """The default roles of a new tenant are created by the tenant role service."""
    service = AsyncMock()
    with patch("auth.services.bootstrap.tenant_role_service", service):
        yield service


@pytest.fixture(autouse=True)
def builtin_repository():
    """The built-in scopes and roles go through the catalog repository."""
    catalog_repo = FakeCatalogRepository()
    with patch("auth.services.catalog.CatalogRepository", return_value=catalog_repo):
        yield catalog_repo


def options(**kwargs):
    base = {"slug": "main", "display_name": "Main"}
    return BootstrapOptions(**{**base, **kwargs})


async def run(repo, **kwargs):
    return await bootstrap(AsyncMock(), options(**kwargs), repo)


class TestOptions:
    def settings(self, **env):
        with patch.dict("os.environ", env, clear=True):
            return Settings(_env_file=None)

    def test_defaults_are_neutral(self):
        parsed = BootstrapOptions.from_settings(self.settings())
        assert parsed.slug == "platform" and parsed.display_name == "Platform"
        assert parsed.tenant_id is None and parsed.branding == {}
        assert parsed.swagger_client_id == "swagger-ui"
        assert parsed.swagger_scopes == ("openid", "profile", "email")
        assert parsed.swagger_redirect_uris == ("/docs/oauth2-redirect",)

    def test_read_from_the_environment(self):
        tenant_id = str(uuid.uuid4())
        parsed = BootstrapOptions.from_settings(
            self.settings(
                PLATFORM_TENANT_SLUG="main-site",
                PLATFORM_TENANT_DISPLAY_NAME=" Example ",
                PLATFORM_TENANT_ID=tenant_id,
                PLATFORM_TENANT_BRANDING='{"primary_color": "#112233"}',
                SWAGGER_CLIENT_ID="docs",
                SWAGGER_SCOPES="openid *",
                SWAGGER_REDIRECT_URIS='["https://auth.example.test/docs/oauth2-redirect"]',
            )
        )
        assert parsed.slug == "main-site" and parsed.display_name == "Example"
        assert parsed.tenant_id == uuid.UUID(tenant_id)
        assert parsed.branding == {"primary_color": "#112233"}
        assert parsed.swagger_client_id == "docs"
        assert parsed.swagger_scopes == ("openid", "*")
        assert parsed.swagger_redirect_uris == ("https://auth.example.test/docs/oauth2-redirect",)

    @pytest.mark.parametrize(
        ("env", "message"),
        [
            ({"PLATFORM_TENANT_SLUG": "Not A Slug"}, "not a valid slug"),
            ({"PLATFORM_TENANT_SLUG": "-bad"}, "not a valid slug"),
            ({"PLATFORM_TENANT_DISPLAY_NAME": "  "}, "DISPLAY_NAME is empty"),
            ({"PLATFORM_TENANT_ID": "nope"}, "not a UUID"),
            ({"PLATFORM_TENANT_BRANDING": '{"colour": "red"}'}, "unknown keys: colour"),
            ({"SWAGGER_CLIENT_ID": ""}, "SWAGGER_CLIENT_ID is empty"),
        ],
    )
    def test_invalid_settings(self, env, message):
        with pytest.raises(BootstrapError, match=message):
            BootstrapOptions.from_settings(self.settings(**env))

    def test_branding_keys_are_the_branding_columns(self):
        assert {"logo_url", "primary_color", "favicon_url"} <= BRANDING_FIELDS
        assert not BRANDING_FIELDS & {"id", "tenant_id", "created_at"}


class TestBuiltin:
    async def test_creates_the_built_in_scopes_and_roles(
        self, repo, roles_service, builtin_repository
    ):
        report = await run(repo)
        assert len(builtin_repository.scopes) == len(ADMIN_SCOPES)
        assert set(builtin_repository.roles) == set(DEFAULT_ROLES)
        assert f"scope {next(iter(ADMIN_SCOPES))}" in report.created[0]


class TestPlatformTenant:
    async def test_created_from_the_settings(self, repo, roles_service):
        tenant_id = uuid.uuid4()
        report = await run(repo, slug="main", display_name="Main", tenant_id=tenant_id)
        tenant = repo.tenants[0]
        assert (tenant.id, tenant.slug, tenant.display_name) == (tenant_id, "main", "Main")
        assert tenant.is_platform is True and tenant.is_active is True
        assert tenant.trust_mode == TenantTrustMode.ALL
        roles_service.create_default_roles.assert_awaited_once()
        assert "platform tenant main" in report.created

    async def test_id_is_generated_when_not_configured(self, repo, roles_service):
        await run(repo)
        assert isinstance(repo.tenants[0].id, uuid.UUID)

    async def test_an_existing_platform_tenant_is_adopted_and_left_alone(self, repo, roles_service):
        existing = Tenant(id=uuid.uuid4(), slug="legacy", display_name="Legacy", is_platform=True)
        repo.tenants.append(existing)
        report = await run(repo, slug="main", display_name="Main")
        assert repo.tenants == [existing]
        assert (existing.slug, existing.display_name) == ("legacy", "Legacy")
        roles_service.create_default_roles.assert_not_awaited()
        assert not any(item.startswith("platform tenant") for item in report.created)
        assert any("platform tenant slug" in item for item in report.skipped)

    async def test_the_same_slug_is_not_reported(self, repo, roles_service):
        repo.tenants.append(
            Tenant(id=uuid.uuid4(), slug="main", display_name="M", is_platform=True)
        )
        report = await run(repo, slug="main")
        assert not any("platform tenant slug" in item for item in report.skipped)

    async def test_slug_taken_by_another_tenant(self, repo, roles_service):
        repo.tenants.append(Tenant(id=uuid.uuid4(), slug="main", display_name="Other"))
        with pytest.raises(BootstrapError, match="not the platform tenant"):
            await run(repo, slug="main")

    async def test_second_run_creates_nothing(self, repo, roles_service):
        await run(repo)
        report = await run(repo)
        assert len(repo.tenants) == 1
        assert "platform tenant" not in " ".join(report.created)


class TestBranding:
    async def test_created_once(self, repo, roles_service):
        report = await run(repo, branding={"primary_color": "#112233"})
        tenant = repo.tenants[0]
        assert repo.branding[tenant.id].primary_color == "#112233"
        assert any(item.startswith("branding") for item in report.created)
        report = await run(repo, branding={"primary_color": "#445566"})
        assert repo.branding[tenant.id].primary_color == "#112233"
        assert not any(item.startswith("branding") for item in report.created)

    async def test_none_without_settings(self, repo, roles_service):
        await run(repo)
        assert repo.branding == {}


class TestExistingUsers:
    async def test_orphans_trusted_sources_and_members_are_fixed(self, repo, roles_service):
        existing = Tenant(id=uuid.uuid4(), slug="main", display_name="M", is_platform=True)
        repo.tenants.append(existing)
        repo.roles[(existing.id, "member")] = SimpleNamespace(id=uuid.uuid4())
        repo.orphans, repo.open_sources, repo.missing_members = 4, 2, 6
        report = await run(repo)
        assert "4 user(s) registered on the platform tenant" in report.updated
        assert "2 trusted source(s) pointed at the platform tenant" in report.updated
        assert "6 user(s) made member of the platform tenant" in report.updated
        report = await run(repo)
        assert not any("user(s)" in item for item in report.updated)

    async def test_no_member_role_means_no_memberships(self, repo, roles_service):
        repo.tenants.append(
            Tenant(id=uuid.uuid4(), slug="main", display_name="M", is_platform=True)
        )
        report = await run(repo)
        assert repo.added_members == []
        assert any("no 'member' role" in item for item in report.skipped)


class TestSwaggerClient:
    async def test_created_public_with_pkce(self, repo, roles_service):
        report = await run(
            repo,
            swagger_client_id="docs",
            swagger_scopes=("openid", "email"),
            swagger_redirect_uris=("https://auth.example.test/docs/oauth2-redirect",),
        )
        client = repo.clients["docs"]
        assert client.redirect_uris == ["https://auth.example.test/docs/oauth2-redirect"]
        assert client.allowed_scopes == ["openid", "email"]
        assert client.allowed_grant_types == ["authorization_code"]
        assert client.token_endpoint_auth_method == "none"
        assert (client.is_confidential, client.require_pkce, client.require_consent) == (
            False,
            True,
            False,
        )
        assert "client docs" in report.created

    async def test_existing_client_follows_the_settings(self, repo, roles_service):
        repo.clients["swagger-ui"] = OAuth2Client(
            client_id="swagger-ui",
            name="Swagger UI",
            redirect_uris=["/old"],
            allowed_scopes=["openid"],
            allowed_grant_types=["authorization_code"],
        )
        report = await run(repo, swagger_redirect_uris=("/new",), swagger_scopes=("openid", "*"))
        client = repo.clients["swagger-ui"]
        assert client.redirect_uris == ["/new"] and client.allowed_scopes == ["openid", "*"]
        assert "client swagger-ui (redirect URIs, scopes)" in report.updated
        report = await run(repo, swagger_redirect_uris=("/new",), swagger_scopes=("openid", "*"))
        assert not any(item.startswith("client") for item in report.updated)
