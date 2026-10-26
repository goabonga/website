# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for plans route (public, no auth required)."""

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from billing.routes.plans import parse_limits
from httpx import AsyncClient


@pytest.fixture
def mock_saas_app():
    """Create a mock SaasApp object."""
    app = MagicMock()
    app.id = str(uuid4())
    app.slug = "test-app"
    app.is_active = True
    return app


@pytest.fixture
def mock_price_monthly():
    """Create a mock monthly price."""
    price = MagicMock()
    price.id = str(uuid4())
    price.currency = "usd"
    price.unit_amount = 1000
    price.billing_type = "recurring"
    price.is_active = True
    price.recurring_interval = "month"
    price.recurring_interval_count = 1
    return price


@pytest.fixture
def mock_price_yearly():
    """Create a mock yearly price."""
    price = MagicMock()
    price.id = str(uuid4())
    price.currency = "usd"
    price.unit_amount = 10000
    price.billing_type = "recurring"
    price.is_active = True
    price.recurring_interval = "year"
    price.recurring_interval_count = 1
    return price


@pytest.fixture
def mock_price_free():
    """Create a mock free price."""
    price = MagicMock()
    price.id = str(uuid4())
    price.currency = "usd"
    price.unit_amount = 0
    price.billing_type = "recurring"
    price.is_active = True
    price.recurring_interval = "month"
    price.recurring_interval_count = 1
    return price


@pytest.fixture
def mock_price_inactive():
    """Create a mock inactive price (should be filtered out)."""
    price = MagicMock()
    price.id = str(uuid4())
    price.currency = "usd"
    price.unit_amount = 500
    price.billing_type = "recurring"
    price.is_active = False
    price.recurring_interval = "month"
    price.recurring_interval_count = 1
    return price


@pytest.fixture
def mock_product_pro(mock_price_monthly, mock_price_yearly):
    """Create a mock Pro product with dict and string features."""
    product = MagicMock()
    product.id = str(uuid4())
    product.name = "Pro"
    product.slug = "pro"
    product.description = "Pro plan"
    product.extra_data = {
        "features": [
            {"label": "5 users", "highlight": True},
            {"label": "Disabled feature", "disabled": True},
            "Basic support",
        ],
        "limits": {"max_seats": 10, "max_projects": 1000},
        "slug": "pro",
        "is_recommended": True,
        "sort_order": 1,
    }
    product.is_active = True
    product.created_at = datetime(2024, 1, 1, tzinfo=UTC)
    product.prices = [mock_price_monthly, mock_price_yearly]
    return product


@pytest.fixture
def mock_product_free(mock_price_free):
    """Create a mock Free product."""
    product = MagicMock()
    product.id = str(uuid4())
    product.name = "Free"
    product.slug = "free"
    product.description = "Free plan"
    product.extra_data = {
        "features": ["1 user", "Community support"],
        "slug": "free",
        "is_recommended": False,
        "sort_order": 0,
    }
    product.is_active = True
    product.created_at = datetime(2024, 1, 1, tzinfo=UTC)
    product.prices = [mock_price_free]
    return product


@pytest.fixture
def mock_product_no_metadata():
    """Create a mock product with no extra_data."""
    product = MagicMock()
    product.id = str(uuid4())
    product.name = "Enterprise"
    product.slug = "enterprise"
    product.description = "Enterprise plan"
    product.extra_data = None
    product.is_active = True
    product.created_at = datetime(2024, 1, 2, tzinfo=UTC)
    product.prices = []
    return product


def _setup_plans_db_mock(mock_db_session, saas_app, products):
    """Helper to set up mock db for plans endpoint.

    First call: SaasApp lookup.
    Second call: Products with prices (selectinload).
    """
    # First call: SaasApp lookup
    mock_saas_result = MagicMock()
    mock_saas_result.scalar_one_or_none.return_value = saas_app

    # Second call: Products with prices
    mock_products_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = products
    mock_products_result.scalars.return_value = mock_scalars

    mock_db_session.execute.side_effect = [mock_saas_result, mock_products_result]


class TestListPlans:
    """Tests for GET /plans/{app_slug} endpoint."""

    @pytest.mark.asyncio
    async def test_list_plans_success(
        self,
        client: AsyncClient,
        mock_db_session,
        mock_saas_app,
        mock_product_pro,
    ):
        """GET /plans/test-app should return 200 with plans list."""
        _setup_plans_db_mock(mock_db_session, mock_saas_app, [mock_product_pro])

        response = await client.get("/plans/test-app")

        assert response.status_code == 200
        data = response.json()
        assert data["app_slug"] == "test-app"
        assert len(data["plans"]) == 1

        plan = data["plans"][0]
        assert plan["name"] == "Pro"
        assert plan["slug"] == "pro"
        assert plan["description"] == "Pro plan"
        assert plan["is_recommended"] is True
        assert plan["sort_order"] == 1

    @pytest.mark.asyncio
    async def test_list_plans_features_parsed(
        self,
        client: AsyncClient,
        mock_db_session,
        mock_saas_app,
        mock_product_pro,
    ):
        """Features should be parsed from both dict and string formats."""
        _setup_plans_db_mock(mock_db_session, mock_saas_app, [mock_product_pro])

        response = await client.get("/plans/test-app")
        plan = response.json()["plans"][0]

        features = plan["features"]
        assert len(features) == 3

        # Dict feature with highlight
        assert features[0]["label"] == "5 users"
        assert features[0]["highlight"] is True
        assert features[0]["disabled"] is False

        # Dict feature with disabled
        assert features[1]["label"] == "Disabled feature"
        assert features[1]["disabled"] is True

        # String feature (defaults)
        assert features[2]["label"] == "Basic support"
        assert features[2]["highlight"] is False
        assert features[2]["disabled"] is False

    @pytest.mark.asyncio
    async def test_list_plans_limits_parsed(
        self,
        client: AsyncClient,
        mock_db_session,
        mock_saas_app,
        mock_product_pro,
    ):
        """Limits should be parsed from product extra_data."""
        _setup_plans_db_mock(mock_db_session, mock_saas_app, [mock_product_pro])

        response = await client.get("/plans/test-app")
        plan = response.json()["plans"][0]

        limits = plan["limits"]
        assert limits is not None
        assert limits == {"max_seats": 10, "max_projects": 1000}

    @pytest.mark.asyncio
    async def test_list_plans_prices_sorted_by_unit_amount(
        self,
        client: AsyncClient,
        mock_db_session,
        mock_saas_app,
        mock_product_pro,
    ):
        """Prices should be sorted by unit_amount (cheapest first)."""
        _setup_plans_db_mock(mock_db_session, mock_saas_app, [mock_product_pro])

        response = await client.get("/plans/test-app")
        plan = response.json()["plans"][0]

        prices = plan["prices"]
        assert len(prices) == 2
        # Monthly (1000) should come before yearly (10000)
        assert prices[0]["unit_amount"] == 1000
        assert prices[0]["interval"] == "month"
        assert prices[1]["unit_amount"] == 10000
        assert prices[1]["interval"] == "year"

    @pytest.mark.asyncio
    async def test_list_plans_sorted_by_sort_order(
        self,
        client: AsyncClient,
        mock_db_session,
        mock_saas_app,
        mock_product_pro,
        mock_product_free,
    ):
        """Plans should be sorted by sort_order."""
        # Products returned in wrong order (Pro first, Free second)
        _setup_plans_db_mock(mock_db_session, mock_saas_app, [mock_product_pro, mock_product_free])

        response = await client.get("/plans/test-app")
        plans = response.json()["plans"]

        assert len(plans) == 2
        # Free (sort_order=0) should come before Pro (sort_order=1)
        assert plans[0]["slug"] == "free"
        assert plans[0]["sort_order"] == 0
        assert plans[1]["slug"] == "pro"
        assert plans[1]["sort_order"] == 1

    @pytest.mark.asyncio
    async def test_list_plans_inactive_prices_excluded(
        self,
        client: AsyncClient,
        mock_db_session,
        mock_saas_app,
        mock_price_monthly,
        mock_price_inactive,
    ):
        """Inactive prices should be excluded from the response."""
        product = MagicMock()
        product.id = str(uuid4())
        product.name = "Test"
        product.slug = "test"
        product.description = "Test plan"
        product.extra_data = {"slug": "test", "sort_order": 0}
        product.is_active = True
        product.created_at = datetime(2024, 1, 1, tzinfo=UTC)
        product.prices = [mock_price_monthly, mock_price_inactive]

        _setup_plans_db_mock(mock_db_session, mock_saas_app, [product])

        response = await client.get("/plans/test-app")
        plan = response.json()["plans"][0]

        # Only active price should be included
        assert len(plan["prices"]) == 1
        assert plan["prices"][0]["unit_amount"] == 1000

    @pytest.mark.asyncio
    async def test_list_plans_not_found(
        self,
        client: AsyncClient,
        mock_db_session,
    ):
        """GET /plans/unknown should return 404 when SaasApp not found."""
        mock_saas_result = MagicMock()
        mock_saas_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.side_effect = [mock_saas_result]

        response = await client.get("/plans/unknown")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_list_plans_no_products(
        self,
        client: AsyncClient,
        mock_db_session,
        mock_saas_app,
    ):
        """GET /plans/test-app with no products should return empty plans list."""
        _setup_plans_db_mock(mock_db_session, mock_saas_app, [])

        response = await client.get("/plans/test-app")

        assert response.status_code == 200
        data = response.json()
        assert data["app_slug"] == "test-app"
        assert data["plans"] == []

    @pytest.mark.asyncio
    async def test_list_plans_product_no_metadata(
        self,
        client: AsyncClient,
        mock_db_session,
        mock_saas_app,
        mock_product_no_metadata,
    ):
        """Product with no extra_data should get default values."""
        _setup_plans_db_mock(mock_db_session, mock_saas_app, [mock_product_no_metadata])

        response = await client.get("/plans/test-app")
        plan = response.json()["plans"][0]

        assert plan["slug"] == "enterprise"  # The slug column of the product
        assert plan["features"] == []
        assert plan["limits"] is None
        assert plan["is_recommended"] is False
        assert plan["sort_order"] == 0

    @pytest.mark.asyncio
    async def test_list_plans_no_auth_required(
        self,
        client: AsyncClient,
        mock_db_session,
        mock_saas_app,
    ):
        """Plans endpoint should work without authentication."""
        _setup_plans_db_mock(mock_db_session, mock_saas_app, [])

        response = await client.get("/plans/test-app")

        # Should not get 401/403 even without auth
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_plans_feature_non_dict_non_string_skipped(
        self,
        client: AsyncClient,
        mock_db_session,
        mock_saas_app,
    ):
        """Features that are neither dict nor string should be skipped."""
        product = MagicMock()
        product.id = str(uuid4())
        product.name = "Test"
        product.slug = "test"
        product.description = "Test plan"
        product.extra_data = {
            "features": [
                "Valid string feature",
                42,  # Not a dict or string -> should be skipped
                None,  # Not a dict or string -> should be skipped
                {"label": "Valid dict feature"},
            ],
            "slug": "test",
            "sort_order": 0,
        }
        product.is_active = True
        product.created_at = datetime(2024, 1, 1, tzinfo=UTC)
        product.prices = []

        _setup_plans_db_mock(mock_db_session, mock_saas_app, [product])

        response = await client.get("/plans/test-app")
        plan = response.json()["plans"][0]

        # Only 2 valid features should be included (string + dict)
        assert len(plan["features"]) == 2
        assert plan["features"][0]["label"] == "Valid string feature"
        assert plan["features"][1]["label"] == "Valid dict feature"


class TestPlanLimits:
    """Limits are free-form integers defined by each SaaS application."""

    @pytest.mark.asyncio
    async def test_any_limit_names_are_exposed(
        self, client: AsyncClient, mock_db_session, mock_saas_app, mock_product_free
    ):
        """Another SaaS application can expose its own limits, unknown to the platform."""
        mock_product_free.extra_data["limits"] = {"max_seats": 3, "emails_per_day": -1}
        _setup_plans_db_mock(mock_db_session, mock_saas_app, [mock_product_free])

        response = await client.get("/plans/test-app")

        assert response.json()["plans"][0]["limits"] == {"max_seats": 3, "emails_per_day": -1}

    @pytest.mark.asyncio
    async def test_plan_without_limits(
        self, client: AsyncClient, mock_db_session, mock_saas_app, mock_product_free
    ):
        _setup_plans_db_mock(mock_db_session, mock_saas_app, [mock_product_free])

        response = await client.get("/plans/test-app")

        assert response.json()["plans"][0]["limits"] is None

    def test_parse_limits_keeps_integers(self):
        assert parse_limits({"a": 1, "b": 0, "c": -1, "d": 2.0}) == {
            "a": 1,
            "b": 0,
            "c": -1,
            "d": 2,
        }

    def test_parse_limits_drops_non_integers(self):
        raw = {"ok": 5, "none": None, "text": "10", "flag": True, "ratio": 1.5, "nested": {"a": 1}}

        assert parse_limits(raw) == {"ok": 5}

    @pytest.mark.parametrize("raw", [None, [], "limits", 3])
    def test_parse_limits_ignores_non_mappings(self, raw):
        assert parse_limits(raw) is None

    def test_parse_limits_of_an_empty_document(self):
        assert parse_limits({}) == {}

    def test_no_application_specific_key_is_declared_by_the_schema(self):
        """The platform schema must not know the keys of any SaaS application."""
        from billing.schemas import plan

        assert plan.PlanLimits == dict[str, int]
        assert not hasattr(plan, "PlanLimit")
