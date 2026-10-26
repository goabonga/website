# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for platform price routes."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from billing.config import settings
from httpx import AsyncClient


def _mock_result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _mock_list_result(items):
    r = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    r.scalars.return_value = scalars
    return r


@pytest.fixture
def saas_id():
    return str(uuid4())


@pytest.fixture
def product_id():
    return str(uuid4())


@pytest.fixture
def price_id():
    return str(uuid4())


@pytest.fixture
def mock_saas(saas_id):
    app = MagicMock()
    app.id = saas_id
    app.slug = "test-app"
    return app


@pytest.fixture
def mock_product(product_id, saas_id):
    p = MagicMock()
    p.id = product_id
    p.saas_app_id = saas_id
    p.stripe_product_id = "prod_test123"
    p.name = "Test Product"
    return p


@pytest.fixture
def mock_price(price_id, product_id):
    p = MagicMock()
    p.id = price_id
    p.product_id = product_id
    p.stripe_price_id = "price_test123"
    p.nickname = "Monthly"
    p.currency = "usd"
    p.unit_amount = 1000
    p.billing_type = "recurring"
    p.recurring_interval = "month"
    p.recurring_interval_count = 1
    p.usage_type = "licensed"
    p.is_active = True
    p.created_at = "2024-01-01T00:00:00Z"
    p.updated_at = "2024-01-01T00:00:00Z"
    return p


class TestGetProductOr404:
    """Tests for get_product_or_404 helper via endpoints."""

    @pytest.mark.asyncio
    async def test_saas_not_found(
        self, auth_client: AsyncClient, mock_db_session, saas_id, product_id
    ):
        mock_db_session.execute.side_effect = [_mock_result(None)]

        response = await auth_client.get(f"/platform/{saas_id}/products/{product_id}/prices")

        assert response.status_code == 404
        assert "SaaS app not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_product_not_found(
        self, auth_client: AsyncClient, mock_db_session, mock_saas, saas_id, product_id
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(None),
        ]

        response = await auth_client.get(f"/platform/{saas_id}/products/{product_id}/prices")

        assert response.status_code == 404
        assert "Product not found" in response.json()["detail"]


class TestCreatePrice:
    """Tests for POST /platform/{saas_id}/products/{product_id}/prices."""

    @pytest.mark.asyncio
    @patch("billing.routes.platform.prices.get_stripe_service")
    async def test_create_success(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_product,
        saas_id,
        product_id,
    ):
        mock_stripe = MagicMock()
        mock_stripe_price = MagicMock()
        mock_stripe_price.id = "price_new123"
        mock_stripe.create_price.return_value = mock_stripe_price
        mock_get_stripe.return_value = mock_stripe

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_product),
        ]

        response = await auth_client.post(
            f"/platform/{saas_id}/products/{product_id}/prices",
            json={
                "unit_amount": 2000,
                "currency": "usd",
                "billing_type": "recurring",
                "recurring_interval": "month",
                "usage_type": "licensed",
            },
        )

        assert response.status_code == 201
        mock_db_session.add.assert_called_once()

    @pytest.mark.asyncio
    @patch("billing.routes.platform.prices.get_stripe_service")
    async def test_create_applies_the_configured_defaults(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_product,
        saas_id,
        product_id,
        monkeypatch,
    ):
        """Currency and interval left out by the caller come from the settings."""
        monkeypatch.setattr(settings, "default_currency", "eur")
        monkeypatch.setattr(settings, "default_recurring_interval", "year")
        mock_stripe = mock_get_stripe.return_value
        mock_stripe.create_price.return_value = MagicMock(id="price_new123")
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_product),
        ]

        response = await auth_client.post(
            f"/platform/{saas_id}/products/{product_id}/prices", json={"unit_amount": 2000}
        )

        assert response.status_code == 201
        sent = mock_stripe.create_price.call_args.kwargs
        stored = mock_db_session.add.call_args[0][0]
        assert (sent["currency"], sent["recurring_interval"]) == ("eur", "year")
        assert (stored.currency, stored.recurring_interval) == ("eur", "year")

    @pytest.mark.asyncio
    @patch("billing.routes.platform.prices.get_stripe_service")
    async def test_create_one_time_price_has_no_interval(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_product,
        saas_id,
        product_id,
    ):
        mock_get_stripe.return_value.create_price.return_value = MagicMock(id="price_new123")
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_product),
        ]

        response = await auth_client.post(
            f"/platform/{saas_id}/products/{product_id}/prices",
            json={"unit_amount": 500, "billing_type": "one_time"},
        )

        assert response.status_code == 201
        assert mock_db_session.add.call_args[0][0].recurring_interval is None


class TestListPrices:
    """Tests for GET /platform/{saas_id}/products/{product_id}/prices."""

    @pytest.mark.asyncio
    async def test_list_success(
        self,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_product,
        mock_price,
        saas_id,
        product_id,
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_product),
            _mock_list_result([mock_price]),
        ]

        response = await auth_client.get(f"/platform/{saas_id}/products/{product_id}/prices")

        assert response.status_code == 200
        assert len(response.json()) == 1

    @pytest.mark.asyncio
    async def test_list_include_inactive(
        self,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_product,
        saas_id,
        product_id,
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_product),
            _mock_list_result([]),
        ]

        response = await auth_client.get(
            f"/platform/{saas_id}/products/{product_id}/prices?include_inactive=true"
        )

        assert response.status_code == 200


class TestGetPrice:
    """Tests for GET /platform/{saas_id}/products/{product_id}/prices/{price_id}."""

    @pytest.mark.asyncio
    async def test_get_success(
        self,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_product,
        mock_price,
        saas_id,
        product_id,
        price_id,
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_product),
            _mock_result(mock_price),
        ]

        response = await auth_client.get(
            f"/platform/{saas_id}/products/{product_id}/prices/{price_id}"
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_not_found(
        self,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_product,
        saas_id,
        product_id,
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_product),
            _mock_result(None),
        ]

        response = await auth_client.get(
            f"/platform/{saas_id}/products/{product_id}/prices/{uuid4()}"
        )

        assert response.status_code == 404


class TestUpdatePrice:
    """Tests for PATCH /platform/{saas_id}/products/{product_id}/prices/{price_id}."""

    @pytest.mark.asyncio
    @patch("billing.routes.platform.prices.get_stripe_service")
    async def test_update_success(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_product,
        mock_price,
        saas_id,
        product_id,
        price_id,
    ):
        mock_stripe = MagicMock()
        mock_get_stripe.return_value = mock_stripe

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_product),
            _mock_result(mock_price),
        ]

        response = await auth_client.patch(
            f"/platform/{saas_id}/products/{product_id}/prices/{price_id}",
            json={"nickname": "Updated", "is_active": False},
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    @patch("billing.routes.platform.prices.get_stripe_service")
    async def test_update_not_found(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_product,
        saas_id,
        product_id,
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_product),
            _mock_result(None),
        ]

        response = await auth_client.patch(
            f"/platform/{saas_id}/products/{product_id}/prices/{uuid4()}",
            json={"nickname": "X"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    @patch("billing.routes.platform.prices.get_stripe_service")
    async def test_update_stripe_error(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_product,
        mock_price,
        saas_id,
        product_id,
        price_id,
    ):
        mock_stripe = MagicMock()
        mock_stripe.update_price.side_effect = Exception("Stripe error")
        mock_get_stripe.return_value = mock_stripe

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_product),
            _mock_result(mock_price),
        ]

        response = await auth_client.patch(
            f"/platform/{saas_id}/products/{product_id}/prices/{price_id}",
            json={"nickname": "Updated"},
        )

        # Should still succeed (best effort Stripe update)
        assert response.status_code == 200

    @pytest.mark.asyncio
    @patch("billing.routes.platform.prices.get_stripe_service")
    async def test_update_only_is_active(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_product,
        mock_price,
        saas_id,
        product_id,
        price_id,
    ):
        """Update with only is_active (no nickname) to cover nickname-None branch."""
        mock_stripe = MagicMock()
        mock_get_stripe.return_value = mock_stripe

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_product),
            _mock_result(mock_price),
        ]

        response = await auth_client.patch(
            f"/platform/{saas_id}/products/{product_id}/prices/{price_id}",
            json={"is_active": False},
        )

        assert response.status_code == 200
