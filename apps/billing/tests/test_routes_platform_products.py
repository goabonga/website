# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for platform product routes."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient


def _mock_result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _mock_first(row):
    """Result of a query read with ``.first()`` (None means no row)."""
    r = MagicMock()
    r.first.return_value = row
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
    p.slug = "test-product"
    p.name = "Test Product"
    p.description = "Test"
    p.extra_data = {}
    p.is_active = True
    p.created_at = "2024-01-01T00:00:00Z"
    p.updated_at = "2024-01-01T00:00:00Z"
    return p


class TestCreateProduct:
    """Tests for POST /platform/{saas_id}/products."""

    @pytest.mark.asyncio
    @patch("billing.routes.platform.products.get_stripe_service")
    async def test_create_success(
        self, mock_get_stripe, auth_client: AsyncClient, mock_db_session, mock_saas, saas_id
    ):
        mock_stripe = MagicMock()
        mock_stripe_product = MagicMock()
        mock_stripe_product.id = "prod_test123"
        mock_stripe.create_product.return_value = mock_stripe_product
        mock_get_stripe.return_value = mock_stripe

        mock_db_session.execute.side_effect = [_mock_result(mock_saas), _mock_first(None)]

        response = await auth_client.post(
            f"/platform/{saas_id}/products",
            json={
                "name": "New Product",
                "description": "A new product",
            },
        )

        assert response.status_code == 201
        mock_db_session.add.assert_called_once()
        created = mock_db_session.add.call_args[0][0]
        assert created.slug == "new-product"
        assert created.extra_data == {"slug": "new-product"}

    @pytest.mark.asyncio
    @patch("billing.routes.platform.products.get_stripe_service")
    async def test_create_uses_explicit_slug_and_stringifies_limits(
        self, mock_get_stripe, auth_client: AsyncClient, mock_db_session, mock_saas, saas_id
    ):
        mock_stripe = MagicMock()
        mock_stripe.create_product.return_value = MagicMock(id="prod_x")
        mock_get_stripe.return_value = mock_stripe
        mock_db_session.execute.side_effect = [_mock_result(mock_saas), _mock_first(None)]

        response = await auth_client.post(
            f"/platform/{saas_id}/products",
            json={"name": "Pro Plan", "slug": "pro", "metadata": {"limits": {"seats": 5}}},
        )

        assert response.status_code == 201
        created = mock_db_session.add.call_args[0][0]
        assert created.slug == "pro"
        assert created.extra_data == {"limits": {"seats": 5}, "slug": "pro"}
        sent = mock_stripe.create_product.call_args.kwargs["metadata"]
        assert sent["slug"] == "pro"

    @pytest.mark.asyncio
    @patch("billing.routes.platform.products.get_stripe_service")
    async def test_create_reads_the_slug_from_metadata(
        self, mock_get_stripe, auth_client: AsyncClient, mock_db_session, mock_saas, saas_id
    ):
        """Clients that only send metadata.slug (admin forms) keep working."""
        mock_get_stripe.return_value.create_product.return_value = MagicMock(id="prod_x")
        mock_db_session.execute.side_effect = [_mock_result(mock_saas), _mock_first(None)]

        response = await auth_client.post(
            f"/platform/{saas_id}/products",
            json={"name": "Whatever", "metadata": {"slug": "Team Plan", "sort_order": 2}},
        )

        assert response.status_code == 201
        created = mock_db_session.add.call_args[0][0]
        assert created.slug == "team-plan"
        assert created.extra_data["sort_order"] == 2

    @pytest.mark.asyncio
    @patch("billing.routes.platform.products.get_stripe_service")
    async def test_create_duplicate_slug_conflicts_before_calling_stripe(
        self, mock_get_stripe, auth_client: AsyncClient, mock_db_session, mock_saas, saas_id
    ):
        mock_db_session.execute.side_effect = [_mock_result(mock_saas), _mock_first(("id",))]

        response = await auth_client.post(
            f"/platform/{saas_id}/products", json={"name": "Pro", "slug": "pro"}
        )

        assert response.status_code == 409
        assert "pro" in response.json()["detail"]
        mock_get_stripe.return_value.create_product.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_rejects_invalid_slug(self, auth_client: AsyncClient, saas_id):
        response = await auth_client.post(
            f"/platform/{saas_id}/products", json={"name": "Pro", "slug": "Not A Slug"}
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_without_derivable_slug_is_rejected(
        self, auth_client: AsyncClient, saas_id
    ):
        response = await auth_client.post(f"/platform/{saas_id}/products", json={"name": "!!!"})

        assert response.status_code == 422

    @pytest.mark.asyncio
    @patch("billing.routes.platform.products.get_stripe_service")
    async def test_create_saas_not_found(
        self, mock_get_stripe, auth_client: AsyncClient, mock_db_session
    ):
        mock_db_session.execute.side_effect = [_mock_result(None)]

        response = await auth_client.post(
            f"/platform/{uuid4()}/products",
            json={
                "name": "X",
                "description": "X",
            },
        )

        assert response.status_code == 404
        assert "SaaS app not found" in response.json()["detail"]


class TestListProducts:
    """Tests for GET /platform/{saas_id}/products."""

    @pytest.mark.asyncio
    async def test_list_success(
        self, auth_client: AsyncClient, mock_db_session, mock_saas, mock_product, saas_id
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_list_result([mock_product]),
        ]

        response = await auth_client.get(f"/platform/{saas_id}/products")

        assert response.status_code == 200
        assert len(response.json()) == 1

    @pytest.mark.asyncio
    async def test_list_include_inactive(
        self, auth_client: AsyncClient, mock_db_session, mock_saas, saas_id
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_list_result([]),
        ]

        response = await auth_client.get(f"/platform/{saas_id}/products?include_inactive=true")

        assert response.status_code == 200


class TestGetProduct:
    """Tests for GET /platform/{saas_id}/products/{product_id}."""

    @pytest.mark.asyncio
    async def test_get_success(
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
        ]

        response = await auth_client.get(f"/platform/{saas_id}/products/{product_id}")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_not_found(
        self, auth_client: AsyncClient, mock_db_session, mock_saas, saas_id
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(None),
        ]

        response = await auth_client.get(f"/platform/{saas_id}/products/{uuid4()}")

        assert response.status_code == 404


class TestUpdateProduct:
    """Tests for PATCH /platform/{saas_id}/products/{product_id}."""

    @pytest.mark.asyncio
    @patch("billing.routes.platform.products.get_stripe_service")
    async def test_update_success(
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
        mock_get_stripe.return_value = mock_stripe

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_product),
        ]

        response = await auth_client.patch(
            f"/platform/{saas_id}/products/{product_id}",
            json={
                "name": "Updated",
                "metadata": {"key": "value"},
            },
        )

        assert response.status_code == 200
        mock_stripe.update_product.assert_called_once()
        assert mock_product.extra_data == {"key": "value", "slug": "test-product"}

    @pytest.mark.asyncio
    @patch("billing.routes.platform.products.get_stripe_service")
    async def test_update_slug(
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
            _mock_first(None),
        ]

        response = await auth_client.patch(
            f"/platform/{saas_id}/products/{product_id}", json={"slug": "enterprise"}
        )

        assert response.status_code == 200
        assert mock_product.slug == "enterprise"
        assert mock_product.extra_data["slug"] == "enterprise"

    @pytest.mark.asyncio
    @patch("billing.routes.platform.products.get_stripe_service")
    async def test_update_slug_conflict(
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
            _mock_first(("id",)),
        ]

        response = await auth_client.patch(
            f"/platform/{saas_id}/products/{product_id}", json={"slug": "taken"}
        )

        assert response.status_code == 409
        mock_get_stripe.return_value.update_product.assert_not_called()

    @pytest.mark.asyncio
    @patch("billing.routes.platform.products.get_stripe_service")
    async def test_update_not_found(
        self, mock_get_stripe, auth_client: AsyncClient, mock_db_session, mock_saas, saas_id
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(None),
        ]

        response = await auth_client.patch(
            f"/platform/{saas_id}/products/{uuid4()}", json={"name": "X"}
        )

        assert response.status_code == 404
