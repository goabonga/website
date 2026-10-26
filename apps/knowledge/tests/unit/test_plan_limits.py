# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for knowledge/services/plan_limits.py: where the limits of a plan come from."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge.config import Settings
from knowledge.services import plan_limits
from knowledge.services.billing import BillingAPIError, Plan


def _plan(slug="pro", limits=None):
    return Plan(
        id=slug,
        slug=slug,
        name=slug.title(),
        description=None,
        features=[],
        limits=limits,
        prices=[],
        is_recommended=False,
        sort_order=0,
    )


@pytest.fixture
def billing():
    """A configured billing client whose plans can be chosen by each test."""
    client = MagicMock()
    client.is_configured = True
    client.app_slug = "my-app"
    client.get_plan_by_slug = AsyncMock(return_value=_plan(limits={"max_collections": 50}))
    plan_limits.reset_billing_backoff()
    with patch.object(plan_limits, "get_billing_client", return_value=client):
        yield client
    plan_limits.reset_billing_backoff()


@pytest.fixture
def settings(monkeypatch):
    configured = Settings(
        _env_file=None,
        billing_failure_backoff=30,
        quota_fallback_limits={
            "pro": {"max_collections": 1},
            "*": {"max_collections": 0, "max_seats": 2},
        },
    )
    monkeypatch.setattr(plan_limits, "get_settings", lambda: configured)
    return configured


async def test_billing_limits_win(billing, settings):
    assert await plan_limits.get_plan_limits("pro") == {"max_collections": 50}
    billing.get_plan_by_slug.assert_awaited_once_with("pro")


async def test_limits_keep_any_name_and_unlimited(billing, settings):
    billing.get_plan_by_slug.return_value = _plan(limits={"max_seats": -1, "emails": 10})
    assert await plan_limits.get_plan_limits("pro") == {"max_seats": -1, "emails": 10}


async def test_billing_unreachable_applies_the_fail_safe(billing, settings, caplog):
    billing.get_plan_by_slug.side_effect = BillingAPIError("down")
    with caplog.at_level("WARNING"):
        assert await plan_limits.get_plan_limits("pro") == {"max_collections": 1}
    assert "down" in caplog.text


async def test_fail_safe_of_another_plan_uses_the_wildcard(billing, settings):
    billing.get_plan_by_slug.side_effect = BillingAPIError("down")
    assert await plan_limits.get_plan_limits("team") == {"max_collections": 0, "max_seats": 2}


async def test_billing_is_not_asked_again_right_after_a_failure(billing, settings):
    billing.get_plan_by_slug.side_effect = BillingAPIError("down")
    await plan_limits.get_plan_limits("pro")
    await plan_limits.get_plan_limits("pro")
    await plan_limits.get_plan_limits("free")
    assert billing.get_plan_by_slug.await_count == 1


async def test_billing_is_asked_again_once_the_backoff_is_over(billing, settings):
    billing.get_plan_by_slug.side_effect = BillingAPIError("down")
    await plan_limits.get_plan_limits("pro")
    billing.get_plan_by_slug.side_effect = None
    with patch.object(
        plan_limits.time, "monotonic", return_value=plan_limits.time.monotonic() + 31
    ):
        assert await plan_limits.get_plan_limits("pro") == {"max_collections": 50}


async def test_unknown_plan_in_billing_applies_the_fail_safe(billing, settings):
    billing.get_plan_by_slug.return_value = None
    assert await plan_limits.get_plan_limits("pro") == {"max_collections": 1}


async def test_plan_without_limits_in_billing_applies_the_fail_safe(billing, settings):
    billing.get_plan_by_slug.return_value = _plan(limits=None)
    assert await plan_limits.get_plan_limits("pro") == {"max_collections": 1}


async def test_plan_with_empty_limits_in_billing_means_nothing_is_allowed(billing, settings):
    billing.get_plan_by_slug.return_value = _plan(limits={})
    assert await plan_limits.get_plan_limits("pro") == {}


@pytest.mark.parametrize("configured", [False])
async def test_billing_not_configured_uses_the_fail_safe(billing, settings, configured):
    billing.is_configured = configured
    assert await plan_limits.get_plan_limits("pro") == {"max_collections": 1}
    billing.get_plan_by_slug.assert_not_called()


async def test_billing_without_app_slug_uses_the_fail_safe(billing, settings):
    billing.app_slug = ""
    assert await plan_limits.get_plan_limits("pro") == {"max_collections": 1}
    billing.get_plan_by_slug.assert_not_called()


async def test_nothing_configured_allows_nothing(billing, settings):
    billing.is_configured = False
    settings.quota_fallback_limits = {}
    assert await plan_limits.get_plan_limits("pro") == {}


async def test_quota_service_enforces_the_billing_limit(billing, settings):
    from knowledge.models.enums import PlanType
    from knowledge.services.quotas import QuotaService

    service = QuotaService(MagicMock())
    assert await service.get_limit(PlanType.PRO, "max_collections") == 50
    billing.get_plan_by_slug.side_effect = BillingAPIError("down")
    plan_limits.reset_billing_backoff()
    assert await service.get_limit(PlanType.PRO, "max_collections") == 1
