# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for QuotaService: dataclass logic, plan limits, and quota enforcement."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from knowledge.config import Settings
from knowledge.models.enums import OwnerType, PlanType
from knowledge.services import plan_limits
from knowledge.services.quotas import (
    QuotaExceededError,
    QuotaService,
    QuotaStatus,
    format_bytes,
)

# Limits of the plans used by these tests (the code has none of its own).
MB = 1024 * 1024
TEST_LIMITS = {
    "free": {
        "max_collections": 3,
        "max_documents_per_collection": 100,
        "max_total_documents": 200,
        "max_api_calls_per_month": 1000,
        "max_storage_bytes": 50 * MB,
    },
    "starter": {"max_collections": 10, "max_total_documents": 5000},
    "pro": {"max_collections": 50, "max_total_documents": 100000},
    "enterprise": {
        "max_collections": -1,
        "max_documents_per_collection": -1,
        "max_total_documents": -1,
        "max_api_calls_per_month": -1,
        "max_storage_bytes": -1,
    },
}


@pytest.fixture(autouse=True)
def configured_limits(monkeypatch):
    """Configure the limits of the plans through the settings, like a deployment does."""
    settings = Settings(_env_file=None, quota_fallback_limits=TEST_LIMITS)
    monkeypatch.setattr(plan_limits, "get_settings", lambda: settings)
    return settings


# ============================================================
# QuotaStatus dataclass (pure logic, no DB)
# ============================================================


class TestQuotaStatusRemaining:
    def test_normal(self):
        qs = QuotaStatus(quota_type="test", current=3, limit=10)
        assert qs.remaining == 7

    def test_exceeded(self):
        qs = QuotaStatus(quota_type="test", current=12, limit=10)
        assert qs.remaining == 0

    def test_unlimited(self):
        qs = QuotaStatus(quota_type="test", current=5, limit=-1, is_unlimited=True)
        assert qs.remaining == -1


class TestQuotaStatusPercentageUsed:
    def test_normal(self):
        qs = QuotaStatus(quota_type="test", current=50, limit=200)
        assert qs.percentage_used == 25.0

    def test_capped_at_100(self):
        qs = QuotaStatus(quota_type="test", current=150, limit=100)
        assert qs.percentage_used == 100.0

    def test_unlimited(self):
        qs = QuotaStatus(quota_type="test", current=100, limit=-1, is_unlimited=True)
        assert qs.percentage_used == 0.0

    def test_zero_limit(self):
        qs = QuotaStatus(quota_type="test", current=0, limit=0)
        assert qs.percentage_used == 0.0


class TestQuotaStatusIsExceeded:
    def test_below_limit(self):
        qs = QuotaStatus(quota_type="test", current=5, limit=10)
        assert qs.is_exceeded is False

    def test_at_limit(self):
        qs = QuotaStatus(quota_type="test", current=10, limit=10)
        assert qs.is_exceeded is True

    def test_over_limit(self):
        qs = QuotaStatus(quota_type="test", current=15, limit=10)
        assert qs.is_exceeded is True

    def test_unlimited(self):
        qs = QuotaStatus(quota_type="test", current=999, limit=-1, is_unlimited=True)
        assert qs.is_exceeded is False


class TestQuotaStatusIsNearLimit:
    def test_below_80_percent(self):
        qs = QuotaStatus(quota_type="test", current=7, limit=10)
        assert qs.is_near_limit is False

    def test_at_80_percent(self):
        qs = QuotaStatus(quota_type="test", current=80, limit=100)
        assert qs.is_near_limit is True

    def test_above_80_percent(self):
        qs = QuotaStatus(quota_type="test", current=9, limit=10)
        assert qs.is_near_limit is True


# ============================================================
# format_bytes (pure function)
# ============================================================


class TestFormatBytes:
    def test_bytes(self):
        assert format_bytes(500) == "500.0 B"

    def test_kilobytes(self):
        assert format_bytes(1536) == "1.5 KB"

    def test_megabytes(self):
        assert format_bytes(50 * 1024 * 1024) == "50.0 MB"

    def test_gigabytes(self):
        assert format_bytes(5 * 1024**3) == "5.0 GB"

    def test_zero(self):
        assert format_bytes(0) == "0.0 B"


# ============================================================
# Plan limits (from the settings)
# ============================================================


class TestPlanLimits:
    async def test_free_plan_limits(self):
        service = QuotaService(MagicMock())
        limits = await service.get_plan_limits(PlanType.FREE)
        assert limits["max_collections"] == 3
        assert limits["max_total_documents"] == 200

    async def test_enterprise_unlimited(self):
        service = QuotaService(MagicMock())
        limits = await service.get_plan_limits(PlanType.ENTERPRISE)
        assert limits["max_collections"] == plan_limits.UNLIMITED
        assert limits["max_total_documents"] == plan_limits.UNLIMITED

    async def test_pro_plan_limits(self):
        service = QuotaService(MagicMock())
        assert await service.get_limit(PlanType.PRO, "max_collections") == 50

    async def test_unknown_key_returns_zero(self):
        service = QuotaService(MagicMock())
        assert await service.get_limit(PlanType.PRO, "nonexistent") == 0

    async def test_plan_without_entry_uses_the_wildcard(self, configured_limits):
        configured_limits.quota_fallback_limits = {"*": {"max_collections": 1}}
        service = QuotaService(MagicMock())
        assert await service.get_limit(PlanType.PRO, "max_collections") == 1

    async def test_nothing_configured_allows_nothing(self, configured_limits):
        configured_limits.quota_fallback_limits = {}
        service = QuotaService(MagicMock())
        assert await service.get_plan_limits(PlanType.FREE) == {}
        assert await service.get_limit(PlanType.FREE, "max_collections") == 0

    def test_limits_are_a_copy(self):
        limits = plan_limits.fallback_limits("free")
        limits["max_collections"] = 99
        assert plan_limits.fallback_limits("free")["max_collections"] == 3

    def test_limits_come_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("QUOTA_FALLBACK_LIMITS", '{"team": {"max_seats": 7}}')
        settings = Settings(_env_file=None)
        assert settings.quota_fallback_limits == {"team": {"max_seats": 7}}


# ============================================================
# Async methods (mock DB)
# ============================================================


class TestGetOwnerPlan:
    async def test_user_with_plan(self, mock_db, make_result, user_id):
        mock_user_plan = MagicMock()
        mock_user_plan.plan = PlanType.PRO
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=mock_user_plan))

        service = QuotaService(mock_db)
        plan = await service.get_owner_plan(OwnerType.USER, user_id)
        assert plan == PlanType.PRO

    async def test_user_no_plan_defaults_to_free(self, mock_db, user_id):
        service = QuotaService(mock_db)
        plan = await service.get_owner_plan(OwnerType.USER, user_id)
        assert plan == PlanType.FREE

    async def test_org_with_plan(self, mock_db, make_result, org_id):
        mock_org = MagicMock()
        mock_org.plan = PlanType.ENTERPRISE
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=mock_org))

        service = QuotaService(mock_db)
        plan = await service.get_owner_plan(OwnerType.ORGANIZATION, org_id)
        assert plan == PlanType.ENTERPRISE

    async def test_org_not_found_defaults_to_free(self, mock_db, org_id):
        service = QuotaService(mock_db)
        plan = await service.get_owner_plan(OwnerType.ORGANIZATION, org_id)
        assert plan == PlanType.FREE


class TestEnforceQuota:
    async def test_exceeded_raises(self, mock_db, make_result, user_id):
        # First call: get_owner_plan -> FREE (3 collections max)
        # Second call: get_collection_count -> 5
        mock_user_plan = MagicMock()
        mock_user_plan.plan = PlanType.FREE
        mock_db.execute = AsyncMock(
            side_effect=[
                make_result(scalar_one_or_none=mock_user_plan),
                make_result(scalar=5),
            ]
        )

        service = QuotaService(mock_db)
        with pytest.raises(QuotaExceededError) as exc_info:
            await service.enforce_quota_for_owner(OwnerType.USER, user_id, "max_collections")
        assert exc_info.value.current == 5
        assert exc_info.value.limit == 3

    async def test_within_limit_no_exception(self, mock_db, make_result, user_id):
        mock_user_plan = MagicMock()
        mock_user_plan.plan = PlanType.FREE
        mock_db.execute = AsyncMock(
            side_effect=[
                make_result(scalar_one_or_none=mock_user_plan),
                make_result(scalar=1),
            ]
        )

        service = QuotaService(mock_db)
        # Should not raise
        await service.enforce_quota_for_owner(OwnerType.USER, user_id, "max_collections")

    async def test_unlimited_no_exception(self, mock_db, make_result, org_id):
        mock_org = MagicMock()
        mock_org.plan = PlanType.ENTERPRISE
        mock_db.execute = AsyncMock(
            side_effect=[
                make_result(scalar_one_or_none=mock_org),
                make_result(scalar=9999),
            ]
        )

        service = QuotaService(mock_db)
        # Enterprise is unlimited, should not raise
        await service.enforce_quota_for_owner(OwnerType.ORGANIZATION, org_id, "max_collections")


class TestIncrementUsage:
    async def test_existing_record_increments(self, mock_db, make_result, tenant_id):
        existing_record = MagicMock()
        existing_record.value = 10
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=existing_record))

        service = QuotaService(mock_db)
        await service.increment_usage(tenant_id, "api_calls", 1)

        assert existing_record.value == 11
        mock_db.add.assert_not_called()

    async def test_new_record_created(self, mock_db, tenant_id):
        service = QuotaService(mock_db)
        await service.increment_usage(tenant_id, "api_calls", 1)

        mock_db.add.assert_called_once()


class TestLegacyEnforceQuota:
    async def test_enforce_collection_quota_exceeded(self, mock_db, make_result, mock_free_tenant):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=5))

        service = QuotaService(mock_db)
        with pytest.raises(QuotaExceededError):
            await service.enforce_collection_quota(mock_free_tenant)

    async def test_enforce_collection_quota_ok(self, mock_db, make_result, mock_free_tenant):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=1))

        service = QuotaService(mock_db)
        await service.enforce_collection_quota(mock_free_tenant)


# ============================================================
# get_document_count_for_owner (lines 185-193)
# ============================================================


class TestGetDocumentCountForOwner:
    async def test_returns_count(self, mock_db, make_result, user_id):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=42))
        service = QuotaService(mock_db)
        count = await service.get_document_count_for_owner(OwnerType.USER, user_id)
        assert count == 42

    async def test_returns_zero(self, mock_db, user_id):
        service = QuotaService(mock_db)
        count = await service.get_document_count_for_owner(OwnerType.USER, user_id)
        assert count == 0


# ============================================================
# get_storage_bytes_for_owner (lines 205-213)
# ============================================================


class TestGetStorageBytesForOwner:
    async def test_returns_bytes(self, mock_db, make_result, user_id):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=1048576))
        service = QuotaService(mock_db)
        bytes_used = await service.get_storage_bytes_for_owner(OwnerType.USER, user_id)
        assert bytes_used == 1048576

    async def test_returns_zero(self, mock_db, user_id):
        service = QuotaService(mock_db)
        bytes_used = await service.get_storage_bytes_for_owner(OwnerType.USER, user_id)
        assert bytes_used == 0


class TestContentLengthExpr:
    def test_uses_octet_length_for_postgresql(self, mock_db):
        bind = MagicMock()
        bind.dialect.name = "postgresql"
        mock_db.get_bind = MagicMock(return_value=bind)
        service = QuotaService(mock_db)
        expr = str(service._content_length_expr())
        assert "octet_length" in expr

    def test_uses_length_for_non_postgresql(self, mock_db):
        bind = MagicMock()
        bind.dialect.name = "sqlite"
        mock_db.get_bind = MagicMock(return_value=bind)
        service = QuotaService(mock_db)
        expr = str(service._content_length_expr())
        assert "length" in expr


# ============================================================
# check_quota_for_owner branches (lines 234-239)
# ============================================================


class TestCheckQuotaForOwner:
    async def test_collections_quota(self, mock_db, make_result, user_id):
        mock_user_plan = MagicMock()
        mock_user_plan.plan = PlanType.FREE
        mock_db.execute = AsyncMock(
            side_effect=[
                make_result(scalar_one_or_none=mock_user_plan),  # get_owner_plan
                make_result(scalar=2),  # get_collection_count_for_owner
            ]
        )
        service = QuotaService(mock_db)
        status = await service.check_quota_for_owner(OwnerType.USER, user_id, "max_collections")
        assert status.current == 2
        assert status.limit == 3

    async def test_total_documents_quota(self, mock_db, make_result, user_id):
        mock_user_plan = MagicMock()
        mock_user_plan.plan = PlanType.FREE
        mock_db.execute = AsyncMock(
            side_effect=[
                make_result(scalar_one_or_none=mock_user_plan),  # get_owner_plan
                make_result(scalar=100),  # get_document_count_for_owner
            ]
        )
        service = QuotaService(mock_db)
        status = await service.check_quota_for_owner(OwnerType.USER, user_id, "max_total_documents")
        assert status.current == 100
        assert status.limit == 200

    async def test_storage_bytes_quota(self, mock_db, make_result, user_id):
        mock_user_plan = MagicMock()
        mock_user_plan.plan = PlanType.FREE
        mock_db.execute = AsyncMock(
            side_effect=[
                make_result(scalar_one_or_none=mock_user_plan),  # get_owner_plan
                make_result(scalar=1024),  # get_storage_bytes_for_owner
            ]
        )
        service = QuotaService(mock_db)
        status = await service.check_quota_for_owner(OwnerType.USER, user_id, "max_storage_bytes")
        assert status.current == 1024

    async def test_unknown_quota_type_returns_zero(self, mock_db, make_result, user_id):
        mock_user_plan = MagicMock()
        mock_user_plan.plan = PlanType.FREE
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=mock_user_plan))
        service = QuotaService(mock_db)
        status = await service.check_quota_for_owner(OwnerType.USER, user_id, "nonexistent")
        assert status.current == 0

    async def test_unlimited_quota(self, mock_db, make_result, org_id):
        mock_org = MagicMock()
        mock_org.plan = PlanType.ENTERPRISE
        mock_db.execute = AsyncMock(
            side_effect=[
                make_result(scalar_one_or_none=mock_org),
                make_result(scalar=999),
            ]
        )
        service = QuotaService(mock_db)
        status = await service.check_quota_for_owner(
            OwnerType.ORGANIZATION, org_id, "max_collections"
        )
        assert status.is_unlimited is True
        assert status.is_exceeded is False


# ============================================================
# enforce_collection_quota_for_owner (line 281)
# ============================================================


class TestEnforceCollectionQuotaForOwner:
    async def test_delegates_to_enforce_quota(self, mock_db, make_result, user_id):
        mock_user_plan = MagicMock()
        mock_user_plan.plan = PlanType.FREE
        mock_db.execute = AsyncMock(
            side_effect=[
                make_result(scalar_one_or_none=mock_user_plan),
                make_result(scalar=5),
            ]
        )
        service = QuotaService(mock_db)
        with pytest.raises(QuotaExceededError):
            await service.enforce_collection_quota_for_owner(OwnerType.USER, user_id)

    async def test_within_limit_ok(self, mock_db, make_result, user_id):
        mock_user_plan = MagicMock()
        mock_user_plan.plan = PlanType.FREE
        mock_db.execute = AsyncMock(
            side_effect=[
                make_result(scalar_one_or_none=mock_user_plan),
                make_result(scalar=1),
            ]
        )
        service = QuotaService(mock_db)
        await service.enforce_collection_quota_for_owner(OwnerType.USER, user_id)


# ============================================================
# get_usage_for_owner (lines 293-307)
# ============================================================


class TestGetUsageForOwner:
    async def test_returns_usage_stats(self, mock_db, make_result, user_id):
        mock_user_plan = MagicMock()
        mock_user_plan.plan = PlanType.FREE
        # Calls:
        # 1. get_owner_plan
        # 2. check_quota (collections) -> get_owner_plan, get_collection_count
        # 3. check_quota (documents) -> get_owner_plan, get_document_count
        # 4. check_quota (storage) -> get_owner_plan, get_storage_bytes
        mock_db.execute = AsyncMock(
            side_effect=[
                make_result(scalar_one_or_none=mock_user_plan),  # get_owner_plan (main)
                make_result(scalar_one_or_none=mock_user_plan),  # get_owner_plan (collections)
                make_result(scalar=2),  # get_collection_count
                make_result(scalar_one_or_none=mock_user_plan),  # get_owner_plan (documents)
                make_result(scalar=50),  # get_document_count
                make_result(scalar_one_or_none=mock_user_plan),  # get_owner_plan (storage)
                make_result(scalar=1024),  # get_storage_bytes
            ]
        )
        service = QuotaService(mock_db)
        stats = await service.get_usage_for_owner(OwnerType.USER, user_id)

        assert stats.plan == PlanType.FREE
        assert stats.collections.current == 2
        assert stats.documents_total.current == 50
        assert stats.storage_bytes.current == 1024
        assert stats.api_calls_month.current == 0


# ============================================================
# Legacy: get_tenant (line 319-322)
# ============================================================


class TestGetTenant:
    async def test_found(self, mock_db, make_result, mock_tenant, tenant_id):
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=mock_tenant))
        service = QuotaService(mock_db)
        result = await service.get_tenant(tenant_id)
        assert result is mock_tenant

    async def test_not_found(self, mock_db, tenant_id):
        service = QuotaService(mock_db)
        result = await service.get_tenant(tenant_id)
        assert result is None


# ============================================================
# Legacy: get_collection_document_count (line 332-337)
# ============================================================


class TestGetCollectionDocumentCount:
    async def test_returns_count(self, mock_db, make_result, collection_id):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=15))
        service = QuotaService(mock_db)
        count = await service.get_collection_document_count(collection_id)
        assert count == 15

    async def test_returns_zero(self, mock_db, collection_id):
        service = QuotaService(mock_db)
        count = await service.get_collection_document_count(collection_id)
        assert count == 0


# ============================================================
# Legacy: get_api_calls_month (lines 343-353)
# ============================================================


class TestGetApiCallsMonth:
    async def test_returns_count(self, mock_db, make_result, tenant_id):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=500))
        service = QuotaService(mock_db)
        count = await service.get_api_calls_month(tenant_id)
        assert count == 500

    async def test_returns_zero(self, mock_db, tenant_id):
        service = QuotaService(mock_db)
        count = await service.get_api_calls_month(tenant_id)
        assert count == 0


# ============================================================
# Legacy: check_quota branches (lines 355-376)
# ============================================================


class TestCheckQuotaLegacy:
    async def test_max_collections(self, mock_db, make_result, mock_free_tenant):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=2))
        service = QuotaService(mock_db)
        status = await service.check_quota(mock_free_tenant, "max_collections")
        assert status.current == 2
        assert status.limit == 3

    async def test_max_total_documents(self, mock_db, make_result, mock_free_tenant):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=50))
        service = QuotaService(mock_db)
        status = await service.check_quota(mock_free_tenant, "max_total_documents")
        assert status.current == 50

    async def test_max_api_calls_per_month(self, mock_db, make_result, mock_free_tenant):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=100))
        service = QuotaService(mock_db)
        status = await service.check_quota(mock_free_tenant, "max_api_calls_per_month")
        assert status.current == 100

    async def test_max_storage_bytes(self, mock_db, make_result, mock_free_tenant):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=1024))
        service = QuotaService(mock_db)
        status = await service.check_quota(mock_free_tenant, "max_storage_bytes")
        assert status.current == 1024

    async def test_unknown_returns_zero(self, mock_db, mock_free_tenant):
        service = QuotaService(mock_db)
        status = await service.check_quota(mock_free_tenant, "nonexistent")
        assert status.current == 0

    async def test_enterprise_unlimited(self, mock_db, make_result, mock_tenant):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=999))
        service = QuotaService(mock_db)
        status = await service.check_quota(mock_tenant, "max_collections")
        assert status.is_unlimited is True


# ============================================================
# Legacy: check_collection_document_quota (lines 378-391)
# ============================================================


class TestCheckCollectionDocumentQuota:
    async def test_returns_status(self, mock_db, make_result, mock_free_tenant, collection_id):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=50))
        service = QuotaService(mock_db)
        status = await service.check_collection_document_quota(mock_free_tenant, collection_id)
        assert status.quota_type == "max_documents_per_collection"
        assert status.current == 50
        assert status.limit == 100  # FREE plan limit

    async def test_enterprise_unlimited(self, mock_db, make_result, mock_tenant, collection_id):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=9999))
        service = QuotaService(mock_db)
        status = await service.check_collection_document_quota(mock_tenant, collection_id)
        assert status.is_unlimited is True


# ============================================================
# Legacy: get_usage (lines 393-410)
# ============================================================


class TestGetUsageLegacy:
    async def test_returns_none_if_tenant_not_found(self, mock_db, tenant_id):
        service = QuotaService(mock_db)
        result = await service.get_usage(tenant_id)
        assert result is None

    async def test_returns_usage_stats(self, mock_db, make_result, mock_free_tenant, tenant_id):
        mock_db.execute = AsyncMock(
            side_effect=[
                make_result(scalar_one_or_none=mock_free_tenant),  # get_tenant
                make_result(scalar=2),  # collections count
                make_result(scalar=50),  # documents count
                make_result(scalar=100),  # api calls
                make_result(scalar=1024),  # storage
            ]
        )
        service = QuotaService(mock_db)
        stats = await service.get_usage(tenant_id)

        assert stats is not None
        assert stats.plan == PlanType.FREE
        assert stats.collections.current == 2
        assert stats.documents_total.current == 50
        assert stats.api_calls_month.current == 100
        assert stats.storage_bytes.current == 1024


# ============================================================
# Legacy: enforce_quota (lines 412-420)
# ============================================================


class TestEnforceQuotaLegacy:
    async def test_exceeded_raises(self, mock_db, make_result, mock_free_tenant):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=5))
        service = QuotaService(mock_db)
        with pytest.raises(QuotaExceededError) as exc_info:
            await service.enforce_quota(mock_free_tenant, "max_collections")
        assert exc_info.value.current == 5
        assert exc_info.value.limit == 3

    async def test_within_limit_ok(self, mock_db, make_result, mock_free_tenant):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=1))
        service = QuotaService(mock_db)
        await service.enforce_quota(mock_free_tenant, "max_collections")


# ============================================================
# Legacy: enforce_document_quota (lines 426-438)
# ============================================================


class TestEnforceDocumentQuota:
    async def test_within_limits(self, mock_db, make_result, mock_free_tenant, collection_id):
        mock_db.execute = AsyncMock(
            side_effect=[
                make_result(scalar=10),  # total documents
                make_result(scalar=5),  # collection documents
            ]
        )
        service = QuotaService(mock_db)
        await service.enforce_document_quota(mock_free_tenant, collection_id)

    async def test_total_exceeded(self, mock_db, make_result, mock_free_tenant, collection_id):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=999))
        service = QuotaService(mock_db)
        with pytest.raises(QuotaExceededError):
            await service.enforce_document_quota(mock_free_tenant, collection_id)

    async def test_per_collection_exceeded(
        self, mock_db, make_result, mock_free_tenant, collection_id
    ):
        mock_db.execute = AsyncMock(
            side_effect=[
                make_result(scalar=10),  # total documents (OK)
                make_result(scalar=999),  # collection documents (exceeded)
            ]
        )
        service = QuotaService(mock_db)
        with pytest.raises(QuotaExceededError):
            await service.enforce_document_quota(mock_free_tenant, collection_id)


# ============================================================
# Legacy: enforce_storage_quota / enforce_api_quota (lines 440-446)
# ============================================================


class TestEnforceStorageQuota:
    async def test_within_limit(self, mock_db, make_result, mock_free_tenant):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=1024))
        service = QuotaService(mock_db)
        await service.enforce_storage_quota(mock_free_tenant)

    async def test_exceeded(self, mock_db, make_result, mock_free_tenant):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=999 * 1024 * 1024))
        service = QuotaService(mock_db)
        with pytest.raises(QuotaExceededError):
            await service.enforce_storage_quota(mock_free_tenant)


class TestEnforceApiQuota:
    async def test_within_limit(self, mock_db, make_result, mock_free_tenant):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=10))
        service = QuotaService(mock_db)
        await service.enforce_api_quota(mock_free_tenant)

    async def test_exceeded(self, mock_db, make_result, mock_free_tenant):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=9999))
        service = QuotaService(mock_db)
        with pytest.raises(QuotaExceededError):
            await service.enforce_api_quota(mock_free_tenant)


# ============================================================
# record_* convenience methods (lines 479-493)
# ============================================================


class TestRecordMethods:
    async def test_record_api_call(self, mock_db, make_result, tenant_id):
        existing = MagicMock()
        existing.value = 5
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=existing))
        service = QuotaService(mock_db)
        await service.record_api_call(tenant_id)
        assert existing.value == 6

    async def test_record_document_added(self, mock_db, make_result, tenant_id):
        existing = MagicMock()
        existing.value = 10
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=existing))
        service = QuotaService(mock_db)
        await service.record_document_added(tenant_id, count=3)
        assert existing.value == 13

    async def test_record_search(self, mock_db, make_result, tenant_id):
        existing = MagicMock()
        existing.value = 0
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=existing))
        service = QuotaService(mock_db)
        await service.record_search(tenant_id)
        assert existing.value == 1

    async def test_record_embedding(self, mock_db, make_result, tenant_id):
        existing = MagicMock()
        existing.value = 20
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=existing))
        service = QuotaService(mock_db)
        await service.record_embedding(tenant_id, count=5)
        assert existing.value == 25


# ============================================================
# format_bytes edge cases (TB, PB)
# ============================================================


class TestFormatBytesExtended:
    def test_terabytes(self):
        assert format_bytes(1024**4) == "1.0 TB"

    def test_petabytes(self):
        assert format_bytes(1024**5) == "1.0 PB"

    def test_negative_bytes(self):
        result = format_bytes(-500)
        assert "B" in result


# ============================================================
# Legacy: get_collection_count / get_document_count / get_storage_bytes (delegation)
# ============================================================


class TestLegacyDelegationMethods:
    async def test_get_collection_count(self, mock_db, make_result, tenant_id):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=3))
        service = QuotaService(mock_db)
        count = await service.get_collection_count(tenant_id)
        assert count == 3

    async def test_get_document_count(self, mock_db, make_result, tenant_id):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=100))
        service = QuotaService(mock_db)
        count = await service.get_document_count(tenant_id)
        assert count == 100

    async def test_get_storage_bytes(self, mock_db, make_result, tenant_id):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=2048))
        service = QuotaService(mock_db)
        bytes_used = await service.get_storage_bytes(tenant_id)
        assert bytes_used == 2048


# ============================================================
# QuotaExceededError (line 31)
# ============================================================


class TestQuotaExceededError:
    def test_message_format(self):
        err = QuotaExceededError("max_collections", current=5, limit=3)
        assert "max_collections" in str(err)
        assert "5/3" in str(err)
        assert err.quota_type == "max_collections"
        assert err.current == 5
        assert err.limit == 3
