# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.issuer — issuer resolution for multi-tenant OAuth2."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.services.issuer import (
    get_issuer_from_context,
    get_tenant_by_id,
    get_tenant_issuer,
    validate_issuer_for_tenant,
)

from tests.conftest import make_execute_result


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


# ── get_tenant_by_id ──────────────────────────────────────────────────────────


class TestGetTenantById:
    @pytest.mark.asyncio
    async def test_found(self, db):
        tenant = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))
        result = await get_tenant_by_id(db, "550e8400-e29b-41d4-a716-446655440000")
        assert result is tenant

    @pytest.mark.asyncio
    async def test_not_found(self, db):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        result = await get_tenant_by_id(db, "550e8400-e29b-41d4-a716-446655440000")
        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_uuid(self, db):
        result = await get_tenant_by_id(db, "not-a-uuid")
        assert result is None

    @pytest.mark.asyncio
    async def test_db_exception(self, db):
        db.execute = AsyncMock(side_effect=Exception("db error"))
        result = await get_tenant_by_id(db, "550e8400-e29b-41d4-a716-446655440000")
        assert result is None


# ── get_tenant_issuer ─────────────────────────────────────────────────────────


class TestGetTenantIssuer:
    @pytest.mark.asyncio
    async def test_custom_domain_active(self, db):
        from auth.db.models.tenant import CustomDomainStatus

        tenant = MagicMock()
        tenant.custom_domain = "auth.example.com"
        tenant.custom_domain_status = CustomDomainStatus.ACTIVE
        result = await get_tenant_issuer(db, tenant)
        assert result == "https://auth.example.com"

    @pytest.mark.asyncio
    async def test_subdomain_tenant(self, db):
        tenant = MagicMock()
        tenant.custom_domain = None
        tenant.is_platform = False
        tenant.slug = "acme"
        with patch("auth.services.issuer.settings") as mock_settings:
            mock_settings.tenant_base_domain = "auth.example.com"
            result = await get_tenant_issuer(db, tenant)
        assert result == "https://acme.auth.example.com"

    @pytest.mark.asyncio
    async def test_platform_tenant(self, db):
        tenant = MagicMock()
        tenant.custom_domain = None
        tenant.is_platform = True
        tenant.slug = "platform"
        with patch("auth.services.issuer.settings") as mock_settings:
            mock_settings.tenant_base_domain = "auth.example.com"
            result = await get_tenant_issuer(db, tenant)
        assert result == "https://auth.example.com"

    @pytest.mark.asyncio
    async def test_fallback_issuer_setting(self, db):
        tenant = MagicMock()
        tenant.custom_domain = None
        tenant.is_platform = True
        with patch("auth.services.issuer.settings") as mock_settings:
            mock_settings.tenant_base_domain = None
            mock_settings.issuer = "https://fallback.example.com"
            result = await get_tenant_issuer(db, tenant)
        assert result == "https://fallback.example.com"

    @pytest.mark.asyncio
    async def test_fallback_localhost(self, db):
        tenant = MagicMock()
        tenant.custom_domain = None
        tenant.is_platform = True
        with patch("auth.services.issuer.settings") as mock_settings:
            mock_settings.tenant_base_domain = None
            mock_settings.issuer = None
            result = await get_tenant_issuer(db, tenant)
        assert result == "http://localhost:8000"

    @pytest.mark.asyncio
    async def test_no_tenant_uses_context(self, db):
        with (
            patch("auth.services.issuer.get_tenant_context") as mock_ctx,
            patch("auth.services.issuer.get_tenant_by_id", new_callable=AsyncMock) as mock_get,
            patch("auth.services.issuer.settings") as mock_settings,
        ):
            tenant = MagicMock()
            tenant.custom_domain = None
            tenant.is_platform = True
            mock_ctx.return_value = MagicMock(tenant_id="some-id")
            mock_get.return_value = tenant
            mock_settings.tenant_base_domain = "auth.example.com"
            result = await get_tenant_issuer(db, tenant=None)
        assert result == "https://auth.example.com"

    @pytest.mark.asyncio
    async def test_no_tenant_no_context(self, db):
        with (
            patch("auth.services.issuer.get_tenant_context") as mock_ctx,
            patch("auth.services.issuer.settings") as mock_settings,
        ):
            mock_ctx.return_value = None
            mock_settings.issuer = "https://default.example.com"
            mock_settings.tenant_base_domain = "auth.example.com"
            result = await get_tenant_issuer(db, tenant=None)
        assert result == "https://default.example.com"

    @pytest.mark.asyncio
    async def test_no_tenant_context_no_tenant_id(self, db):
        with (
            patch("auth.services.issuer.get_tenant_context") as mock_ctx,
            patch("auth.services.issuer.settings") as mock_settings,
        ):
            mock_ctx.return_value = MagicMock(tenant_id=None)
            mock_settings.issuer = None
            mock_settings.tenant_base_domain = "auth.example.com"
            result = await get_tenant_issuer(db, tenant=None)
        assert result == "https://auth.example.com"


# ── get_issuer_from_context ──────────────────────────────────────────────────


class TestGetIssuerFromContext:
    @pytest.mark.asyncio
    async def test_delegates(self, db):
        with patch("auth.services.issuer.get_tenant_issuer", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = "https://test.example.com"
            result = await get_issuer_from_context(db)
        assert result == "https://test.example.com"
        mock_get.assert_called_once_with(db, tenant=None)


# ── validate_issuer_for_tenant ───────────────────────────────────────────────


class TestValidateIssuerForTenant:
    def test_custom_domain_match(self):
        from auth.db.models.tenant import CustomDomainStatus

        tenant = MagicMock()
        tenant.custom_domain = "custom.example.com"
        tenant.custom_domain_status = CustomDomainStatus.ACTIVE
        assert validate_issuer_for_tenant("https://custom.example.com", tenant) is True

    def test_custom_domain_mismatch(self):
        from auth.db.models.tenant import CustomDomainStatus

        tenant = MagicMock()
        tenant.custom_domain = "custom.example.com"
        tenant.custom_domain_status = CustomDomainStatus.ACTIVE
        tenant.is_platform = False
        with patch("auth.services.issuer.settings") as mock_settings:
            mock_settings.tenant_base_domain = None
            result = validate_issuer_for_tenant("https://wrong.example.com", tenant)
        assert result is False

    def test_subdomain_match(self):
        tenant = MagicMock()
        tenant.custom_domain = None
        tenant.is_platform = False
        tenant.slug = "acme"
        with patch("auth.services.issuer.settings") as mock_settings:
            mock_settings.tenant_base_domain = "auth.example.com"
            result = validate_issuer_for_tenant("https://acme.auth.example.com", tenant)
        assert result is True

    def test_platform_base_domain_match(self):
        tenant = MagicMock()
        tenant.custom_domain = None
        tenant.is_platform = True
        with patch("auth.services.issuer.settings") as mock_settings:
            mock_settings.tenant_base_domain = "auth.example.com"
            mock_settings.issuer = None
            result = validate_issuer_for_tenant("https://auth.example.com", tenant)
        assert result is True

    def test_platform_settings_issuer_match(self):
        tenant = MagicMock()
        tenant.custom_domain = None
        tenant.is_platform = True
        with patch("auth.services.issuer.settings") as mock_settings:
            mock_settings.tenant_base_domain = None
            mock_settings.issuer = "https://myissuer.com"
            result = validate_issuer_for_tenant("https://myissuer.com", tenant)
        assert result is True

    def test_no_match(self):
        tenant = MagicMock()
        tenant.custom_domain = None
        tenant.is_platform = False
        with patch("auth.services.issuer.settings") as mock_settings:
            mock_settings.tenant_base_domain = None
            result = validate_issuer_for_tenant("https://unknown.com", tenant)
        assert result is False


class TestValidateIssuerForTenantBranches:
    """Branch coverage for the subdomain / platform issuer comparisons."""

    def _tenant(self, **kwargs):
        tenant = MagicMock()
        tenant.custom_domain = kwargs.get("custom_domain")
        tenant.custom_domain_status = kwargs.get("custom_domain_status")
        tenant.is_platform = kwargs.get("is_platform", False)
        tenant.slug = kwargs.get("slug", "acme")
        return tenant

    def test_subdomain_issuer_mismatch_falls_through(self):
        from auth.services.issuer import validate_issuer_for_tenant

        with patch("auth.services.issuer.settings") as s:
            s.tenant_base_domain = "auth.example.com"
            s.issuer = None
            assert validate_issuer_for_tenant("https://other.example.com", self._tenant()) is False

    def test_platform_base_domain_mismatch_falls_through_to_settings_issuer(self):
        from auth.services.issuer import validate_issuer_for_tenant

        with patch("auth.services.issuer.settings") as s:
            s.tenant_base_domain = "auth.example.com"
            s.issuer = "https://issuer.example.com"
            tenant = self._tenant(is_platform=True)

            assert validate_issuer_for_tenant("https://issuer.example.com", tenant) is True

    def test_platform_base_domain_match(self):
        from auth.services.issuer import validate_issuer_for_tenant

        with patch("auth.services.issuer.settings") as s:
            s.tenant_base_domain = "auth.example.com"
            s.issuer = None
            tenant = self._tenant(is_platform=True)

            assert validate_issuer_for_tenant("https://auth.example.com", tenant) is True

    def test_platform_without_base_domain_uses_settings_issuer(self):
        from auth.services.issuer import validate_issuer_for_tenant

        with patch("auth.services.issuer.settings") as s:
            s.tenant_base_domain = None
            s.issuer = "https://issuer.example.com"
            tenant = self._tenant(is_platform=True)

            assert validate_issuer_for_tenant("https://issuer.example.com", tenant) is True

    def test_platform_no_match_returns_false(self):
        from auth.services.issuer import validate_issuer_for_tenant

        with patch("auth.services.issuer.settings") as s:
            s.tenant_base_domain = "auth.example.com"
            s.issuer = "https://issuer.example.com"
            tenant = self._tenant(is_platform=True)

            assert validate_issuer_for_tenant("https://evil.example.com", tenant) is False
