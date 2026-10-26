# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for platform SaaS app routes."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from billing.routes.platform.saas import (
    STRIPE_PRICE_ID_PATTERN,
    STRIPE_PRODUCT_ID_PATTERN,
    is_placeholder_stripe_id,
)
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
def mock_saas(saas_id):
    app = MagicMock()
    app.id = saas_id
    app.slug = "test-app"
    app.name = "Test App"
    app.description = "Test"
    app.webhook_url = "https://example.com/webhook"
    app.webhook_secret = "secret"
    app.branding = {}
    app.checkout_url_allowlist = ["https://app.example.test"]
    app.is_active = True
    app.created_at = "2024-01-01T00:00:00Z"
    app.updated_at = "2024-01-01T00:00:00Z"
    return app


class TestIsPlaceholderStripeId:
    """Tests for is_placeholder_stripe_id."""

    def test_placeholder_product_id(self):
        assert is_placeholder_stripe_id("placeholder_123", STRIPE_PRODUCT_ID_PATTERN) is True

    def test_real_product_id(self):
        assert is_placeholder_stripe_id("prod_AbCdEfGhIjKlMn", STRIPE_PRODUCT_ID_PATTERN) is False

    def test_placeholder_price_id(self):
        assert is_placeholder_stripe_id("placeholder_price", STRIPE_PRICE_ID_PATTERN) is True

    def test_real_price_id(self):
        assert is_placeholder_stripe_id("price_AbCdEfGhIjKlMn", STRIPE_PRICE_ID_PATTERN) is False


class TestCreateSaasApp:
    """Tests for POST /platform/saas."""

    @pytest.mark.asyncio
    async def test_create_success(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.execute.side_effect = [_mock_result(None)]  # no conflict

        response = await admin_client.post(
            "/platform/saas",
            json={
                "name": "New App",
                "slug": "new-app",
            },
        )

        assert response.status_code == 201
        mock_db_session.add.assert_called_once()
        mock_db_session.flush.assert_called()

    @pytest.mark.asyncio
    async def test_create_stores_checkout_url_allowlist(
        self, admin_client: AsyncClient, mock_db_session
    ):
        mock_db_session.execute.side_effect = [_mock_result(None)]

        response = await admin_client.post(
            "/platform/saas",
            json={
                "name": "New App",
                "slug": "new-app",
                "checkout_url_allowlist": ["https://app.example.test/", "http://localhost:3000"],
            },
        )

        assert response.status_code == 201
        created = mock_db_session.add.call_args[0][0]
        assert created.checkout_url_allowlist == [
            "https://app.example.test",
            "http://localhost:3000",
        ]

    @pytest.mark.asyncio
    async def test_create_rejects_invalid_allowlist_entry(self, admin_client: AsyncClient):
        response = await admin_client.post(
            "/platform/saas",
            json={"name": "New App", "slug": "new-app", "checkout_url_allowlist": ["not a url"]},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_slug_conflict(
        self, admin_client: AsyncClient, mock_db_session, mock_saas
    ):
        mock_db_session.execute.side_effect = [_mock_result(mock_saas)]

        response = await admin_client.post(
            "/platform/saas",
            json={
                "name": "New App",
                "slug": "test-app",
            },
        )

        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_requires_auth(self, client: AsyncClient):
        response = await client.post("/platform/saas", json={"name": "X", "slug": "x"})
        assert response.status_code == 401


class TestListSaasApps:
    """Tests for GET /platform/saas."""

    @pytest.mark.asyncio
    async def test_list_active_only(self, auth_client: AsyncClient, mock_db_session, mock_saas):
        mock_db_session.execute.side_effect = [_mock_list_result([mock_saas])]

        response = await auth_client.get("/platform/saas")

        assert response.status_code == 200
        assert len(response.json()) == 1

    @pytest.mark.asyncio
    async def test_list_include_inactive(
        self, auth_client: AsyncClient, mock_db_session, mock_saas
    ):
        mock_db_session.execute.side_effect = [_mock_list_result([mock_saas])]

        response = await auth_client.get("/platform/saas?include_inactive=true")

        assert response.status_code == 200


class TestGetSaasApp:
    """Tests for GET /platform/saas/{saas_id}."""

    @pytest.mark.asyncio
    async def test_get_success(self, auth_client: AsyncClient, mock_db_session, mock_saas, saas_id):
        mock_db_session.execute.side_effect = [_mock_result(mock_saas)]

        response = await auth_client.get(f"/platform/saas/{saas_id}")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.execute.side_effect = [_mock_result(None)]

        response = await auth_client.get(f"/platform/saas/{uuid4()}")

        assert response.status_code == 404


class TestUpdateSaasApp:
    """Tests for PATCH /platform/saas/{saas_id}."""

    @pytest.mark.asyncio
    async def test_update_success(
        self, auth_client: AsyncClient, mock_db_session, mock_saas, saas_id
    ):
        mock_db_session.execute.side_effect = [_mock_result(mock_saas)]

        response = await auth_client.patch(f"/platform/saas/{saas_id}", json={"name": "Updated"})

        assert response.status_code == 200
        mock_db_session.flush.assert_called()

    @pytest.mark.asyncio
    async def test_update_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.execute.side_effect = [_mock_result(None)]

        response = await auth_client.patch(f"/platform/saas/{uuid4()}", json={"name": "X"})

        assert response.status_code == 404


class TestSyncSaasToStripe:
    """Tests for POST /platform/saas/{saas_id}/sync-stripe."""

    @pytest.mark.asyncio
    async def test_sync_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.execute.side_effect = [_mock_result(None)]

        response = await auth_client.post(f"/platform/saas/{uuid4()}/sync-stripe")

        assert response.status_code == 404

    @pytest.mark.asyncio
    @patch("billing.routes.platform.saas.get_stripe_service")
    async def test_sync_products_synced(
        self, mock_get_stripe, auth_client: AsyncClient, mock_db_session, saas_id
    ):
        mock_stripe_service = MagicMock()
        mock_stripe_product = MagicMock()
        mock_stripe_product.id = "prod_RealStripeId12345"
        mock_stripe_service.create_product.return_value = mock_stripe_product

        mock_stripe_price = MagicMock()
        mock_stripe_price.id = "price_RealStripeId12345"
        mock_stripe_service.create_price.return_value = mock_stripe_price
        mock_get_stripe.return_value = mock_stripe_service

        # Create mock price
        mock_price = MagicMock()
        mock_price.stripe_price_id = "placeholder_price_1"
        mock_price.unit_amount = 1000
        mock_price.currency = "usd"
        mock_price.billing_type = MagicMock(value="recurring")
        mock_price.recurring_interval = "month"
        mock_price.recurring_interval_count = 1
        mock_price.usage_type = MagicMock(value="licensed")
        mock_price.nickname = "Monthly"

        # Create mock product with placeholder ID
        mock_product = MagicMock()
        mock_product.stripe_product_id = "placeholder_prod_1"
        mock_product.name = "Test Product"
        mock_product.description = "Test"
        mock_product.prices = [mock_price]

        # Create mock SaaS app
        mock_saas = MagicMock()
        mock_saas.id = saas_id
        mock_saas.slug = "test-app"
        mock_saas.products = [mock_product]

        mock_db_session.execute.side_effect = [_mock_result(mock_saas)]

        response = await auth_client.post(f"/platform/saas/{saas_id}/sync-stripe")

        assert response.status_code == 200
        data = response.json()
        assert data["products_synced"] == 1
        assert data["prices_synced"] == 1

    @pytest.mark.asyncio
    @patch("billing.routes.platform.saas.get_stripe_service")
    async def test_sync_products_skipped(
        self, mock_get_stripe, auth_client: AsyncClient, mock_db_session, saas_id
    ):
        mock_get_stripe.return_value = MagicMock()

        # Product with real Stripe ID (should be skipped)
        mock_product = MagicMock()
        mock_product.stripe_product_id = "prod_AbCdEfGhIjKlMn"
        mock_product.prices = []

        mock_saas = MagicMock()
        mock_saas.id = saas_id
        mock_saas.slug = "test-app"
        mock_saas.products = [mock_product]

        mock_db_session.execute.side_effect = [_mock_result(mock_saas)]

        response = await auth_client.post(f"/platform/saas/{saas_id}/sync-stripe")

        assert response.status_code == 200
        data = response.json()
        assert data["products_skipped"] == 1
        assert data["products_synced"] == 0

    @pytest.mark.asyncio
    @patch("billing.routes.platform.saas.get_stripe_service")
    async def test_sync_price_no_amount_skipped(
        self, mock_get_stripe, auth_client: AsyncClient, mock_db_session, saas_id
    ):
        mock_stripe_service = MagicMock()
        mock_stripe_product = MagicMock()
        mock_stripe_product.id = "prod_RealStripeId12345"
        mock_stripe_service.create_product.return_value = mock_stripe_product
        mock_get_stripe.return_value = mock_stripe_service

        mock_price = MagicMock()
        mock_price.stripe_price_id = "placeholder_price_1"
        mock_price.unit_amount = None  # No amount -> skip
        mock_price.nickname = "Custom"

        mock_product = MagicMock()
        mock_product.stripe_product_id = "placeholder_prod_1"
        mock_product.name = "Test"
        mock_product.description = "Test"
        mock_product.prices = [mock_price]

        mock_saas = MagicMock()
        mock_saas.id = saas_id
        mock_saas.slug = "test"
        mock_saas.products = [mock_product]

        mock_db_session.execute.side_effect = [_mock_result(mock_saas)]

        response = await auth_client.post(f"/platform/saas/{saas_id}/sync-stripe")

        assert response.status_code == 200
        data = response.json()
        assert data["prices_skipped"] == 1

    @pytest.mark.asyncio
    @patch("billing.routes.platform.saas.get_stripe_service")
    async def test_sync_price_with_real_id_skipped(
        self, mock_get_stripe, auth_client: AsyncClient, mock_db_session, saas_id
    ):
        mock_stripe_service = MagicMock()
        mock_stripe_product = MagicMock()
        mock_stripe_product.id = "prod_RealStripeId12345"
        mock_stripe_service.create_product.return_value = mock_stripe_product
        mock_get_stripe.return_value = mock_stripe_service

        mock_price = MagicMock()
        mock_price.stripe_price_id = "price_AbCdEfGhIjKlMn"  # Real ID -> skip
        mock_price.unit_amount = 1000

        mock_product = MagicMock()
        mock_product.stripe_product_id = "placeholder_prod_1"
        mock_product.name = "Test"
        mock_product.description = "Test"
        mock_product.prices = [mock_price]

        mock_saas = MagicMock()
        mock_saas.id = saas_id
        mock_saas.slug = "test"
        mock_saas.products = [mock_product]

        mock_db_session.execute.side_effect = [_mock_result(mock_saas)]

        response = await auth_client.post(f"/platform/saas/{saas_id}/sync-stripe")

        assert response.status_code == 200
        data = response.json()
        assert data["prices_skipped"] == 1

    @pytest.mark.asyncio
    @patch("billing.routes.platform.saas.get_stripe_service")
    async def test_sync_product_stripe_error(
        self, mock_get_stripe, auth_client: AsyncClient, mock_db_session, saas_id
    ):
        import stripe as stripe_mod

        mock_stripe_service = MagicMock()
        mock_stripe_service.create_product.side_effect = stripe_mod.error.StripeError("fail")
        mock_get_stripe.return_value = mock_stripe_service

        mock_product = MagicMock()
        mock_product.stripe_product_id = "placeholder_prod_1"
        mock_product.name = "Test"
        mock_product.prices = []

        mock_saas = MagicMock()
        mock_saas.id = saas_id
        mock_saas.slug = "test"
        mock_saas.products = [mock_product]

        mock_db_session.execute.side_effect = [_mock_result(mock_saas)]

        response = await auth_client.post(f"/platform/saas/{saas_id}/sync-stripe")

        assert response.status_code == 200
        data = response.json()
        assert len(data["errors"]) == 1

    @pytest.mark.asyncio
    @patch("billing.routes.platform.saas.get_stripe_service")
    async def test_sync_price_stripe_error(
        self, mock_get_stripe, auth_client: AsyncClient, mock_db_session, saas_id
    ):
        import stripe as stripe_mod

        mock_stripe_service = MagicMock()
        mock_stripe_product = MagicMock()
        mock_stripe_product.id = "prod_RealStripeId12345"
        mock_stripe_service.create_product.return_value = mock_stripe_product
        mock_stripe_service.create_price.side_effect = stripe_mod.error.StripeError("price fail")
        mock_get_stripe.return_value = mock_stripe_service

        mock_price = MagicMock()
        mock_price.stripe_price_id = "placeholder_price_1"
        mock_price.unit_amount = 1000
        mock_price.currency = "usd"
        mock_price.billing_type = MagicMock(value="recurring")
        mock_price.recurring_interval = "month"
        mock_price.recurring_interval_count = 1
        mock_price.usage_type = MagicMock(value="licensed")
        mock_price.nickname = "Monthly"

        mock_product = MagicMock()
        mock_product.stripe_product_id = "placeholder_prod_1"
        mock_product.name = "Test"
        mock_product.description = "Test"
        mock_product.prices = [mock_price]

        mock_saas = MagicMock()
        mock_saas.id = saas_id
        mock_saas.slug = "test"
        mock_saas.products = [mock_product]

        mock_db_session.execute.side_effect = [_mock_result(mock_saas)]

        response = await auth_client.post(f"/platform/saas/{saas_id}/sync-stripe")

        assert response.status_code == 200
        data = response.json()
        assert data["products_synced"] == 1
        assert len(data["errors"]) == 1
