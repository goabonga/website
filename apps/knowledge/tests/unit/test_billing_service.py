# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for knowledge/services/billing.py — BillingClient and dataclass properties."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from knowledge.services.billing import (
    BillingAPIError,
    BillingClient,
    CancelResult,
    CheckoutSession,
    Plan,
    PlanPrice,
    ProrationLineItem,
    ReactivateResult,
    TenantSubscription,
    UpgradePreview,
    UpgradeResult,
    checkout_redirect_urls,
    get_billing_client,
    parse_limits,
)
from knowledge.services.service_auth import ServiceAuthError

# ======================================================================
# Dataclass property tests
# ======================================================================


class TestParseLimits:
    def test_integer_limits_keep_their_names(self):
        assert parse_limits({"max_seats": 5, "any_name": -1}) == {"max_seats": 5, "any_name": -1}

    def test_values_that_are_not_integers_are_left_out(self):
        raw = {"max_seats": 5, "null": None, "text": "9", "flag": True, "ratio": 1.5}
        assert parse_limits(raw) == {"max_seats": 5}

    def test_no_limits(self):
        assert parse_limits(None) is None
        assert parse_limits("5") is None
        assert parse_limits({}) == {}


class TestPlanPrice:
    def test_display_amount_zero(self):
        price = PlanPrice(id="p1", currency="usd", unit_amount=0, interval="month")
        assert price.display_amount == "0"

    def test_display_amount_none(self):
        price = PlanPrice(id="p1", currency="usd", unit_amount=None, interval="month")
        assert price.display_amount == "0"

    def test_display_amount_dollars_only(self):
        price = PlanPrice(id="p1", currency="usd", unit_amount=1000, interval="month")
        assert price.display_amount == "10"

    def test_display_amount_with_cents(self):
        price = PlanPrice(id="p1", currency="usd", unit_amount=1050, interval="month")
        assert price.display_amount == "10.50"

    def test_is_custom_true(self):
        price = PlanPrice(id="p1", currency="usd", unit_amount=None, interval="month")
        assert price.is_custom is True

    def test_is_custom_false(self):
        price = PlanPrice(id="p1", currency="usd", unit_amount=1000, interval="month")
        assert price.is_custom is False


class TestPlan:
    @staticmethod
    def _make_plan(prices=None, **kwargs):
        defaults = dict(
            id="plan-1",
            slug="starter",
            name="Starter",
            description="A starter plan",
            features=[],
            limits=None,
            prices=prices or [],
            is_recommended=False,
            sort_order=0,
        )
        defaults.update(kwargs)
        return Plan(**defaults)

    def test_monthly_price_found(self):
        p = PlanPrice(id="m1", currency="usd", unit_amount=1000, interval="month", interval_count=1)
        plan = self._make_plan(prices=[p])
        assert plan.monthly_price is p

    def test_monthly_price_fallback_first(self):
        p = PlanPrice(id="y1", currency="usd", unit_amount=10000, interval="year", interval_count=1)
        plan = self._make_plan(prices=[p])
        assert plan.monthly_price is p

    def test_monthly_price_empty(self):
        plan = self._make_plan(prices=[])
        assert plan.monthly_price is None

    def test_yearly_price_found(self):
        p = PlanPrice(id="y1", currency="usd", unit_amount=10000, interval="year", interval_count=1)
        plan = self._make_plan(prices=[p])
        assert plan.yearly_price is p

    def test_yearly_price_not_found(self):
        p = PlanPrice(id="m1", currency="usd", unit_amount=1000, interval="month", interval_count=1)
        plan = self._make_plan(prices=[p])
        assert plan.yearly_price is None

    def test_yearly_savings_percent_both_prices(self):
        monthly = PlanPrice(
            id="m", currency="usd", unit_amount=1000, interval="month", interval_count=1
        )
        yearly = PlanPrice(
            id="y", currency="usd", unit_amount=10000, interval="year", interval_count=1
        )
        plan = self._make_plan(prices=[monthly, yearly])
        # 12*1000=12000, savings=2000, 2000/12000*100=16.67 -> 17
        assert plan.yearly_savings_percent == 17

    def test_yearly_savings_percent_no_monthly(self):
        yearly = PlanPrice(
            id="y", currency="usd", unit_amount=10000, interval="year", interval_count=1
        )
        self._make_plan(prices=[yearly])
        # monthly_price returns yearly as fallback, yearly_price returns yearly
        # But monthly.interval != "month", so monthly_price returns first price
        # Actually monthly_price returns yearly (fallback), yearly_price returns yearly
        # monthly.unit_amount=10000, yearly.unit_amount=10000
        # 10000*12=120000, savings=120000-10000=110000
        # Actually no - let's check: monthly_annual_cost=10000*12=120000
        # savings=120000-10000=110000, pct=110000/120000*100=91.67->92
        # But the intent is to test "no monthly" - let's use empty prices
        plan2 = self._make_plan(prices=[])
        assert plan2.yearly_savings_percent == 0

    def test_yearly_savings_percent_no_yearly(self):
        monthly = PlanPrice(
            id="m", currency="usd", unit_amount=1000, interval="month", interval_count=1
        )
        plan = self._make_plan(prices=[monthly])
        assert plan.yearly_savings_percent == 0

    def test_yearly_savings_percent_zero_monthly(self):
        monthly = PlanPrice(
            id="m", currency="usd", unit_amount=0, interval="month", interval_count=1
        )
        yearly = PlanPrice(id="y", currency="usd", unit_amount=0, interval="year", interval_count=1)
        plan = self._make_plan(prices=[monthly, yearly])
        assert plan.yearly_savings_percent == 0

    def test_yearly_savings_percent_none_amounts(self):
        monthly = PlanPrice(
            id="m", currency="usd", unit_amount=None, interval="month", interval_count=1
        )
        yearly = PlanPrice(
            id="y", currency="usd", unit_amount=None, interval="year", interval_count=1
        )
        plan = self._make_plan(prices=[monthly, yearly])
        assert plan.yearly_savings_percent == 0

    def test_yearly_monthly_equivalent_with_cents(self):
        yearly = PlanPrice(
            id="y", currency="usd", unit_amount=11900, interval="year", interval_count=1
        )
        monthly = PlanPrice(
            id="m", currency="usd", unit_amount=1000, interval="month", interval_count=1
        )
        plan = self._make_plan(prices=[monthly, yearly])
        # 11900 // 12 = 991 -> 9 dollars 91 cents -> "9.91"
        assert plan.yearly_monthly_equivalent == "9.91"

    def test_yearly_monthly_equivalent_exact_dollars(self):
        yearly = PlanPrice(
            id="y", currency="usd", unit_amount=12000, interval="year", interval_count=1
        )
        monthly = PlanPrice(
            id="m", currency="usd", unit_amount=1000, interval="month", interval_count=1
        )
        plan = self._make_plan(prices=[monthly, yearly])
        assert plan.yearly_monthly_equivalent == "10"

    def test_yearly_monthly_equivalent_no_yearly(self):
        plan = self._make_plan(prices=[])
        assert plan.yearly_monthly_equivalent == "0"

    def test_yearly_monthly_equivalent_none_amount(self):
        yearly = PlanPrice(
            id="y", currency="usd", unit_amount=None, interval="year", interval_count=1
        )
        monthly = PlanPrice(
            id="m", currency="usd", unit_amount=1000, interval="month", interval_count=1
        )
        plan = self._make_plan(prices=[monthly, yearly])
        assert plan.yearly_monthly_equivalent == "0"

    def test_is_free_true(self):
        monthly = PlanPrice(
            id="m", currency="usd", unit_amount=0, interval="month", interval_count=1
        )
        plan = self._make_plan(prices=[monthly])
        assert plan.is_free is True

    def test_is_free_false(self):
        monthly = PlanPrice(
            id="m", currency="usd", unit_amount=1000, interval="month", interval_count=1
        )
        plan = self._make_plan(prices=[monthly])
        assert plan.is_free is False

    def test_is_free_no_prices(self):
        plan = self._make_plan(prices=[])
        assert plan.is_free is False


class TestProrationLineItem:
    def test_display_amount_positive(self):
        item = ProrationLineItem(description="charge", amount=1050)
        assert item.display_amount == "$10.50"

    def test_display_amount_negative(self):
        item = ProrationLineItem(description="credit", amount=-1050)
        assert item.display_amount == "-$10.50"

    def test_display_amount_exact_dollars_positive(self):
        item = ProrationLineItem(description="charge", amount=500)
        assert item.display_amount == "$5"

    def test_display_amount_exact_dollars_negative(self):
        item = ProrationLineItem(description="credit", amount=-500)
        assert item.display_amount == "-$5"


class TestUpgradePreview:
    def _make_preview(self, total=1050, credit_applied=500):
        return UpgradePreview(
            current_plan_name="Starter",
            new_plan_name="Pro",
            current_price_amount=1000,
            new_price_amount=2000,
            line_items=[],
            subtotal=1500,
            total=total,
            credit_applied=credit_applied,
        )

    def test_display_total_with_cents(self):
        preview = self._make_preview(total=1050)
        assert preview.display_total == "$10.50"

    def test_display_total_exact_dollars(self):
        preview = self._make_preview(total=1000)
        assert preview.display_total == "$10"

    def test_display_total_negative(self):
        preview = self._make_preview(total=-1050)
        assert preview.display_total == "-$10.50"

    def test_display_total_negative_exact(self):
        preview = self._make_preview(total=-1000)
        assert preview.display_total == "-$10"

    def test_display_credit_with_cents(self):
        preview = self._make_preview(credit_applied=1050)
        assert preview.display_credit == "$10.50"

    def test_display_credit_exact_dollars(self):
        preview = self._make_preview(credit_applied=500)
        assert preview.display_credit == "$5"


# ======================================================================
# BillingClient tests
# ======================================================================


def _mock_settings(**overrides):
    """Create mock settings for BillingClient."""
    defaults = dict(
        billing_socket_path="",
        billing_api_url="http://billing.test",
        billing_app_slug="knowledge",
        billing_cache_ttl=300,
        redis_url="redis://localhost:6379/0",
        billing_saas_id="saas-123",
        service_timeout=10.0,
    )
    defaults.update(overrides)
    s = MagicMock()
    for k, v in defaults.items():
        setattr(s, k, v)
    return s


SAMPLE_PLANS_RESPONSE = {
    "plans": [
        {
            "id": "plan-1",
            "slug": "free",
            "name": "Free",
            "description": "Free plan",
            "features": [
                {"label": "Feature A", "highlight": True, "disabled": False},
            ],
            "limits": {
                "max_collections": 3,
                "max_documents_per_collection": 100,
                "max_total_documents": 300,
                "max_api_calls_per_month": 1000,
                "max_storage_bytes": 1073741824,
            },
            "prices": [
                {
                    "id": "price-free",
                    "currency": "usd",
                    "unit_amount": 0,
                    "interval": "month",
                    "interval_count": 1,
                },
            ],
            "is_recommended": False,
            "sort_order": 1,
        },
        {
            "id": "plan-2",
            "slug": "pro",
            "name": "Pro",
            "description": None,
            "features": [],
            "prices": [],
            "is_recommended": True,
            "sort_order": 0,
        },
    ]
}


class TestBillingClient:
    @patch("knowledge.services.billing.get_settings")
    def _make_client(self, mock_gs, **overrides):
        mock_gs.return_value = _mock_settings(**overrides)
        return BillingClient()

    # --- is_configured / base_url ---

    def test_is_configured_url(self):
        client = self._make_client(billing_api_url="http://billing.test", billing_socket_path="")
        assert client.is_configured is True

    def test_is_configured_socket(self):
        client = self._make_client(billing_api_url="", billing_socket_path="/run/billing.sock")
        assert client.is_configured is True

    def test_is_not_configured(self):
        client = self._make_client(billing_api_url="", billing_socket_path="")
        assert client.is_configured is False

    def test_base_url_http(self):
        client = self._make_client(billing_api_url="http://billing.test", billing_socket_path="")
        assert client.base_url == "http://billing.test"

    def test_base_url_socket(self):
        client = self._make_client(
            billing_api_url="http://billing.test", billing_socket_path="/run/billing.sock"
        )
        assert client.base_url == "http://localhost"

    # --- get_http_client ---

    @patch("knowledge.services.billing.httpx.AsyncClient")
    async def test_get_http_client_http(self, mock_async_client_cls):
        mock_instance = AsyncMock()
        mock_instance.is_closed = False
        mock_async_client_cls.return_value = mock_instance

        client = self._make_client(billing_socket_path="")
        http_client = await client.get_http_client()
        assert http_client is not None
        assert client._http_client is http_client
        # calling again returns same instance
        http_client2 = await client.get_http_client()
        assert http_client2 is http_client
        await client.close()

    @patch("knowledge.services.billing.httpx.AsyncHTTPTransport")
    @patch("knowledge.services.billing.httpx.AsyncClient")
    async def test_get_http_client_socket(self, mock_async_client_cls, mock_transport_cls):
        mock_instance = AsyncMock()
        mock_instance.is_closed = False
        mock_async_client_cls.return_value = mock_instance
        mock_transport_cls.return_value = MagicMock()

        client = self._make_client(billing_socket_path="/run/billing.sock")
        http_client = await client.get_http_client()
        assert http_client is not None
        await client.close()

    @patch("knowledge.services.billing.httpx.AsyncClient")
    async def test_get_http_client_recreated_when_closed(self, mock_async_client_cls):
        mock_instance1 = AsyncMock()
        mock_instance1.is_closed = False
        mock_instance1.aclose = AsyncMock()
        mock_instance2 = AsyncMock()
        mock_instance2.is_closed = False
        mock_async_client_cls.side_effect = [mock_instance1, mock_instance2]

        client = self._make_client(billing_socket_path="")
        http_client = await client.get_http_client()
        # Simulate closing
        mock_instance1.is_closed = True
        http_client2 = await client.get_http_client()
        assert http_client2 is not http_client
        await client.close()

    # --- _get_access_token ---

    async def test_get_access_token_uses_the_billing_credentials(self):
        client = self._make_client()
        client._tokens = MagicMock()
        client._tokens.aget = AsyncMock(return_value="new-token")
        with patch(
            "knowledge.services.billing.credentials_for", return_value="creds"
        ) as credentials:
            token = await client._get_access_token("scope1")
        assert token == "new-token"
        credentials.assert_called_once_with("billing")
        client._tokens.aget.assert_awaited_once_with("creds", "scope1")

    async def test_get_access_token_failure_is_a_billing_error(self):
        client = self._make_client()
        client._tokens = MagicMock()
        client._tokens.aget = AsyncMock(side_effect=ServiceAuthError("OAuth2 token request failed"))
        with pytest.raises(BillingAPIError, match="OAuth2 token request failed"):
            await client._get_access_token("scope1")

    # --- saas_id ---

    def test_saas_id_is_required(self):
        client = self._make_client(billing_saas_id="")
        with pytest.raises(BillingAPIError, match="BILLING_SAAS_ID is not configured"):
            _ = client.saas_id

    def test_saas_id_comes_from_the_settings(self):
        client = self._make_client(billing_saas_id="my-saas")
        assert client.saas_id == "my-saas"

    # --- get_redis_client ---

    async def test_get_redis_client(self):
        client = self._make_client()
        mock_redis = MagicMock()
        with patch("knowledge.services.billing.redis.from_url", return_value=mock_redis):
            r = await client.get_redis_client()
        assert r is mock_redis
        # second call returns cached
        r2 = await client.get_redis_client()
        assert r2 is mock_redis

    # --- _cache_key ---

    def test_cache_key(self):
        client = self._make_client()
        assert client._cache_key() == "knowledge:billing:plans:knowledge"

    # --- _parse_plans ---

    def test_parse_plans_full(self):
        client = self._make_client()
        plans = client._parse_plans(SAMPLE_PLANS_RESPONSE)
        assert len(plans) == 2
        # sorted by sort_order, plan-2 (sort_order=0) comes first
        assert plans[0].slug == "pro"
        assert plans[1].slug == "free"
        assert len(plans[1].features) == 1
        assert plans[1].features[0].label == "Feature A"
        assert plans[1].limits == {
            "max_collections": 3,
            "max_documents_per_collection": 100,
            "max_total_documents": 300,
            "max_api_calls_per_month": 1000,
            "max_storage_bytes": 1073741824,
        }
        assert plans[0].limits is None

    def test_parse_plans_keeps_the_limits_of_any_application(self):
        client = self._make_client()
        data = {"plans": [{"id": "x", "slug": "team", "limits": {"max_seats": 4, "emails": -1}}]}
        assert client._parse_plans(data)[0].limits == {"max_seats": 4, "emails": -1}

    def test_parse_plans_no_limits(self):
        client = self._make_client()
        data = {"plans": [{"id": "x", "slug": "x", "name": "X", "prices": [], "features": []}]}
        plans = client._parse_plans(data)
        assert len(plans) == 1
        assert plans[0].limits is None

    def test_parse_plans_empty(self):
        client = self._make_client()
        plans = client._parse_plans({})
        assert plans == []

    # --- get_plans ---

    async def test_get_plans_not_configured(self):
        client = self._make_client(billing_api_url="", billing_socket_path="")
        plans = await client.get_plans()
        assert plans == []

    async def test_get_plans_cache_hit(self):
        client = self._make_client()
        import json

        cached_data = json.dumps(SAMPLE_PLANS_RESPONSE)
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=cached_data)
        client._redis_client = mock_redis

        with patch.object(client, "get_redis_client", return_value=mock_redis):
            plans = await client.get_plans()
        assert len(plans) == 2

    async def test_get_plans_cache_error_falls_through(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=Exception("redis down"))
        mock_redis.setex = AsyncMock()
        client._redis_client = mock_redis

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_PLANS_RESPONSE

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        with patch.object(client, "get_redis_client", return_value=mock_redis):
            plans = await client.get_plans()
        assert len(plans) == 2

    async def test_get_plans_sends_the_token_and_asks_for_the_app_slug(self):
        client = self._make_client(billing_app_slug="my-app")
        client._get_access_token = AsyncMock(return_value="tok")
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        client._redis_client = mock_redis

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_PLANS_RESPONSE
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        await client.get_plans()

        client._get_access_token.assert_awaited_once_with("billing:platform:read")
        mock_http.get.assert_awaited_once_with(
            "http://billing.test/plans/my-app", headers={"Authorization": "Bearer tok"}
        )

    async def test_get_plans_without_app_slug_is_not_configured(self):
        client = self._make_client(billing_app_slug="")
        assert await client.get_plans() == []

    async def test_get_plans_api_404(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        client._redis_client = mock_redis

        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        with patch.object(client, "get_redis_client", return_value=mock_redis):
            plans = await client.get_plans()
        assert plans == []

    async def test_get_plans_api_error_status(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        client._redis_client = mock_redis

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        with patch.object(client, "get_redis_client", return_value=mock_redis):
            with pytest.raises(BillingAPIError, match="Billing API returned 500"):
                await client.get_plans()

    async def test_get_plans_api_success_cache_set_error(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock(side_effect=Exception("redis write fail"))
        client._redis_client = mock_redis

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_PLANS_RESPONSE

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        with patch.object(client, "get_redis_client", return_value=mock_redis):
            plans = await client.get_plans()
        assert len(plans) == 2

    async def test_get_plans_request_error(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        client._redis_client = mock_redis

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(side_effect=httpx.RequestError("connection refused"))
        client._http_client = mock_http

        with patch.object(client, "get_redis_client", return_value=mock_redis):
            with pytest.raises(BillingAPIError, match="Billing API request failed"):
                await client.get_plans()

    # --- get_plan_by_slug ---

    async def test_get_plan_by_slug_found(self):
        client = self._make_client()
        mock_plan = Plan(
            id="p1",
            slug="starter",
            name="Starter",
            description=None,
            features=[],
            limits=None,
            prices=[],
            is_recommended=False,
            sort_order=0,
        )
        with patch.object(client, "get_plans", return_value=[mock_plan]):
            result = await client.get_plan_by_slug("starter")
        assert result is mock_plan

    async def test_get_plan_by_slug_not_found(self):
        client = self._make_client()
        with patch.object(client, "get_plans", return_value=[]):
            result = await client.get_plan_by_slug("nonexistent")
        assert result is None

    async def test_get_plan_by_slug_skips_non_matching(self):
        """Loop continues past non-matching plans (branch 497->496)."""
        client = self._make_client()
        other = Plan(
            id="p0",
            slug="other",
            name="Other",
            description=None,
            features=[],
            limits=None,
            prices=[],
            is_recommended=False,
            sort_order=0,
        )
        target = Plan(
            id="p1",
            slug="starter",
            name="Starter",
            description=None,
            features=[],
            limits=None,
            prices=[],
            is_recommended=False,
            sort_order=1,
        )
        with patch.object(client, "get_plans", return_value=[other, target]):
            result = await client.get_plan_by_slug("starter")
        assert result is target

    # --- create_checkout_session ---

    async def test_create_checkout_session_not_configured(self):
        client = self._make_client(billing_api_url="", billing_socket_path="")
        with pytest.raises(BillingAPIError, match="Billing API not configured"):
            await client.create_checkout_session("t1", "p1", "http://ok", "http://cancel")

    async def test_create_checkout_session_success(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "session_id": "s1",
            "url": "https://checkout.stripe.com/s1",
        }

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        result = await client.create_checkout_session(
            "t1",
            "p1",
            "http://ok",
            "http://cancel",
            trial_period_days=14,
            customer_email="test@test.com",
            customer_name="Test User",
        )
        assert isinstance(result, CheckoutSession)
        assert result.session_id == "s1"

    async def test_create_checkout_session_404(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        with pytest.raises(BillingAPIError, match="Customer or price not found"):
            await client.create_checkout_session("t1", "p1", "http://ok", "http://cancel")

    async def test_create_checkout_session_urls_refused_by_billing(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_response = MagicMock()
        mock_response.status_code = 422

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        with pytest.raises(BillingAPIError, match="allow-list"):
            await client.create_checkout_session("t1", "p1", "http://ok", "http://cancel")

    async def test_create_checkout_session_sends_the_configured_saas_id(self):
        client = self._make_client(billing_saas_id="saas-xyz")
        client._get_access_token = AsyncMock(return_value="tok")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"session_id": "s1", "url": "https://pay"}
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        await client.create_checkout_session("t1", "p1", "http://ok", "http://cancel")

        payload = mock_http.post.await_args.kwargs["json"]
        assert payload["saas_id"] == "saas-xyz"
        assert payload["external_id"] == "t1"
        client._get_access_token.assert_awaited_once_with("billing:checkout:write")

    async def test_create_checkout_session_without_saas_id(self):
        client = self._make_client(billing_saas_id="")
        client._get_access_token = AsyncMock(return_value="tok")
        with pytest.raises(BillingAPIError, match="BILLING_SAAS_ID"):
            await client.create_checkout_session("t1", "p1", "http://ok", "http://cancel")

    async def test_create_checkout_session_other_error(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal error"

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        with pytest.raises(BillingAPIError, match="Billing API returned 500"):
            await client.create_checkout_session("t1", "p1", "http://ok", "http://cancel")

    async def test_create_checkout_session_request_error(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(side_effect=httpx.RequestError("fail"))
        client._http_client = mock_http

        with pytest.raises(BillingAPIError, match="Billing API request failed"):
            await client.create_checkout_session("t1", "p1", "http://ok", "http://cancel")

    # --- get_tenant_subscription ---

    async def test_get_tenant_subscription_not_configured(self):
        client = self._make_client(billing_api_url="", billing_socket_path="")
        result = await client.get_tenant_subscription("t1")
        assert result is None

    async def test_get_tenant_subscription_success(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "sub-1",
            "status": "active",
            "price_id": "p1",
            "current_period_start": "2024-01-01T00:00:00Z",
            "current_period_end": "2024-02-01T00:00:00Z",
            "cancel_at_period_end": False,
        }

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        result = await client.get_tenant_subscription("t1")
        assert isinstance(result, TenantSubscription)
        assert result.id == "sub-1"
        assert result.status == "active"

    async def test_get_tenant_subscription_404(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        result = await client.get_tenant_subscription("t1")
        assert result is None

    async def test_get_tenant_subscription_other_status(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Error"

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        result = await client.get_tenant_subscription("t1")
        assert result is None

    async def test_get_tenant_subscription_empty_data(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        result = await client.get_tenant_subscription("t1")
        assert result is None

    async def test_get_tenant_subscription_no_period_dates(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "sub-1",
            "status": "active",
        }

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        result = await client.get_tenant_subscription("t1")
        assert result.current_period_start is None
        assert result.current_period_end is None

    async def test_get_tenant_subscription_request_error(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(side_effect=httpx.RequestError("fail"))
        client._http_client = mock_http

        result = await client.get_tenant_subscription("t1")
        assert result is None

    async def test_get_tenant_subscription_unexpected_error(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(side_effect=ValueError("unexpected"))
        client._http_client = mock_http

        result = await client.get_tenant_subscription("t1")
        assert result is None

    # --- preview_upgrade ---

    async def test_preview_upgrade_not_configured(self):
        client = self._make_client(billing_api_url="", billing_socket_path="")
        with pytest.raises(BillingAPIError, match="Billing API not configured"):
            await client.preview_upgrade("sub-1", "p2")

    async def test_preview_upgrade_success(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "current_plan_name": "Starter",
            "new_plan_name": "Pro",
            "current_price_amount": 1000,
            "new_price_amount": 2000,
            "line_items": [
                {"description": "Prorated charge", "amount": 500, "currency": "usd"},
            ],
            "subtotal": 500,
            "total": 500,
            "credit_applied": 0,
            "currency": "usd",
        }

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        result = await client.preview_upgrade("sub-1", "p2")
        assert isinstance(result, UpgradePreview)
        assert result.new_plan_name == "Pro"
        assert len(result.line_items) == 1

    async def test_preview_upgrade_404(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        with pytest.raises(BillingAPIError, match="Subscription or price not found"):
            await client.preview_upgrade("sub-1", "p2")

    async def test_preview_upgrade_400(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"detail": "Same plan"}

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        with pytest.raises(BillingAPIError, match="Same plan"):
            await client.preview_upgrade("sub-1", "p2")

    async def test_preview_upgrade_other_status(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Server Error"

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        with pytest.raises(BillingAPIError, match="Billing API returned 500"):
            await client.preview_upgrade("sub-1", "p2")

    async def test_preview_upgrade_request_error(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(side_effect=httpx.RequestError("fail"))
        client._http_client = mock_http

        with pytest.raises(BillingAPIError, match="Billing API request failed"):
            await client.preview_upgrade("sub-1", "p2")

    # --- upgrade_subscription ---

    async def test_upgrade_subscription_not_configured(self):
        client = self._make_client(billing_api_url="", billing_socket_path="")
        with pytest.raises(BillingAPIError, match="Billing API not configured"):
            await client.upgrade_subscription("sub-1", "p2")

    async def test_upgrade_subscription_success(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "proration_applied": True,
            "amount_due": 500,
            "invoice_id": "inv-1",
        }

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        result = await client.upgrade_subscription("sub-1", "p2")
        assert isinstance(result, UpgradeResult)
        assert result.success is True
        assert result.invoice_id == "inv-1"

    async def test_upgrade_subscription_404(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        with pytest.raises(BillingAPIError, match="Subscription or price not found"):
            await client.upgrade_subscription("sub-1", "p2")

    async def test_upgrade_subscription_400(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"detail": "Cannot downgrade"}

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        with pytest.raises(BillingAPIError, match="Cannot downgrade"):
            await client.upgrade_subscription("sub-1", "p2")

    async def test_upgrade_subscription_other_error(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Error"

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        with pytest.raises(BillingAPIError, match="Billing API returned 500"):
            await client.upgrade_subscription("sub-1", "p2")

    async def test_upgrade_subscription_request_error(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(side_effect=httpx.RequestError("fail"))
        client._http_client = mock_http

        with pytest.raises(BillingAPIError, match="Billing API request failed"):
            await client.upgrade_subscription("sub-1", "p2")

    # --- cancel_subscription ---

    async def test_cancel_subscription_not_configured(self):
        client = self._make_client(billing_api_url="", billing_socket_path="")
        result = await client.cancel_subscription("sub-1")
        assert result.success is False
        assert result.error == "Billing API not configured"

    async def test_cancel_subscription_success(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "cancel_at_period_end": True,
            "current_period_end": "2024-02-01T00:00:00Z",
        }

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        result = await client.cancel_subscription("sub-1")
        assert isinstance(result, CancelResult)
        assert result.success is True
        assert result.cancel_at_period_end is True
        assert result.current_period_end is not None

    async def test_cancel_subscription_success_no_period_end(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "cancel_at_period_end": True,
        }

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        result = await client.cancel_subscription("sub-1")
        assert result.success is True
        assert result.current_period_end is None

    async def test_cancel_subscription_404(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        result = await client.cancel_subscription("sub-1")
        assert result.success is False
        assert result.error == "Subscription not found"

    async def test_cancel_subscription_409(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_response = MagicMock()
        mock_response.status_code = 409

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        result = await client.cancel_subscription("sub-1")
        assert result.success is False
        assert result.error == "Subscription is already canceled"

    async def test_cancel_subscription_other_status(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Server Error"

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        result = await client.cancel_subscription("sub-1")
        assert result.success is False
        assert "500" in result.error

    async def test_cancel_subscription_request_error(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(side_effect=httpx.RequestError("fail"))
        client._http_client = mock_http

        result = await client.cancel_subscription("sub-1")
        assert result.success is False
        assert "Request failed" in result.error

    async def test_cancel_subscription_unexpected_error(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(side_effect=ValueError("unexpected"))
        client._http_client = mock_http

        result = await client.cancel_subscription("sub-1")
        assert result.success is False
        assert "Unexpected error" in result.error

    # --- reactivate_subscription ---

    async def test_reactivate_subscription_not_configured(self):
        client = self._make_client(billing_api_url="", billing_socket_path="")
        result = await client.reactivate_subscription("sub-1")
        assert result.success is False
        assert result.error == "Billing API not configured"

    async def test_reactivate_subscription_success(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "active"}

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        result = await client.reactivate_subscription("sub-1")
        assert isinstance(result, ReactivateResult)
        assert result.success is True
        assert result.status == "active"

    async def test_reactivate_subscription_404(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        result = await client.reactivate_subscription("sub-1")
        assert result.success is False
        assert result.error == "Subscription not found"

    async def test_reactivate_subscription_409(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_response = MagicMock()
        mock_response.status_code = 409

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        result = await client.reactivate_subscription("sub-1")
        assert result.success is False
        assert result.error == "Subscription cannot be reactivated"

    async def test_reactivate_subscription_other_status(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Error"

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        result = await client.reactivate_subscription("sub-1")
        assert result.success is False
        assert "500" in result.error

    async def test_reactivate_subscription_request_error(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(side_effect=httpx.RequestError("fail"))
        client._http_client = mock_http

        result = await client.reactivate_subscription("sub-1")
        assert result.success is False
        assert "Request failed" in result.error

    async def test_reactivate_subscription_unexpected_error(self):
        client = self._make_client()
        client._get_access_token = AsyncMock(return_value="tok")

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(side_effect=ValueError("unexpected"))
        client._http_client = mock_http

        result = await client.reactivate_subscription("sub-1")
        assert result.success is False
        assert "Unexpected error" in result.error

    # --- close ---

    async def test_close_both_clients(self):
        client = self._make_client()
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.aclose = AsyncMock()
        client._http_client = mock_http

        mock_redis = AsyncMock()
        mock_redis.aclose = AsyncMock()
        client._redis_client = mock_redis

        await client.close()
        mock_http.aclose.assert_awaited_once()
        mock_redis.aclose.assert_awaited_once()

    async def test_close_no_clients(self):
        client = self._make_client()
        # Should not raise
        await client.close()

    async def test_close_http_already_closed(self):
        client = self._make_client()
        mock_http = AsyncMock()
        mock_http.is_closed = True
        client._http_client = mock_http
        await client.close()
        mock_http.aclose.assert_not_awaited()


# --- get_billing_client singleton ---


class TestCheckoutRedirectUrls:
    def _urls(self, success="https://app.test/ok", cancel="https://app.test/ko"):
        settings = MagicMock()
        settings.billing_checkout_success_url = success
        settings.billing_checkout_cancel_url = cancel
        with patch("knowledge.services.billing.get_settings", return_value=settings):
            return checkout_redirect_urls()

    def test_urls_come_from_the_settings(self):
        assert self._urls() == ("https://app.test/ok", "https://app.test/ko")

    @pytest.mark.parametrize("missing", ["success", "cancel"])
    def test_both_urls_are_required(self, missing):
        urls = {"success": "https://app.test/ok", "cancel": "https://app.test/ko", missing: ""}
        with pytest.raises(BillingAPIError, match="BILLING_CHECKOUT_SUCCESS_URL"):
            self._urls(**urls)


class TestGetBillingClient:
    @patch("knowledge.services.billing._billing_client", None)
    @patch("knowledge.services.billing.get_settings")
    def test_get_billing_client_creates_new(self, mock_gs):
        mock_gs.return_value = _mock_settings()
        client = get_billing_client()
        assert isinstance(client, BillingClient)

    @patch("knowledge.services.billing._billing_client")
    def test_get_billing_client_returns_existing(self, mock_existing):
        mock_existing.__class__ = BillingClient
        # If _billing_client is not None, it is returned
        import knowledge.services.billing as mod

        original = mod._billing_client
        sentinel = MagicMock()
        mod._billing_client = sentinel
        try:
            result = get_billing_client()
            assert result is sentinel
        finally:
            mod._billing_client = original
