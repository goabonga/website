# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for platform customer routes."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
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
def customer_id():
    return str(uuid4())


@pytest.fixture
def mock_saas(saas_id):
    app = MagicMock()
    app.id = saas_id
    app.slug = "test-app"
    app.checkout_url_allowlist = ["https://example.com"]
    return app


@pytest.fixture
def mock_customer(customer_id, saas_id):
    c = MagicMock()
    c.id = customer_id
    c.saas_app_id = saas_id
    c.external_id = "ext-123"
    c.stripe_customer_id = "cus_test123"
    c.email = "test@example.com"
    c.name = "Test Customer"
    c.extra_data = None
    c.deleted_at = None
    c.created_at = "2024-01-01T00:00:00Z"
    c.updated_at = "2024-01-01T00:00:00Z"
    return c


class TestCreateCustomer:
    """Tests for POST /platform/{saas_id}/customers."""

    @pytest.mark.asyncio
    @patch("billing.routes.platform.customers.get_stripe_service")
    async def test_create_success(
        self, mock_get_stripe, auth_client: AsyncClient, mock_db_session, mock_saas, saas_id
    ):
        mock_stripe = MagicMock()
        mock_stripe_customer = MagicMock()
        mock_stripe_customer.id = "cus_new123"
        mock_stripe.create_customer.return_value = mock_stripe_customer
        mock_get_stripe.return_value = mock_stripe

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),  # saas lookup
            _mock_result(None),  # no conflict
        ]

        response = await auth_client.post(
            f"/platform/{saas_id}/customers",
            json={
                "external_id": "ext-new",
                "email": "new@example.com",
                "name": "New Customer",
            },
        )

        assert response.status_code == 201
        mock_db_session.add.assert_called_once()

    @pytest.mark.asyncio
    @patch("billing.routes.platform.customers.get_stripe_service")
    async def test_create_conflict(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_customer,
        saas_id,
    ):
        mock_get_stripe.return_value = MagicMock()

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_customer),  # already exists
        ]

        response = await auth_client.post(
            f"/platform/{saas_id}/customers",
            json={
                "external_id": "ext-123",
                "email": "test@example.com",
            },
        )

        assert response.status_code == 409

    @pytest.mark.asyncio
    @patch("billing.routes.platform.customers.get_stripe_service")
    async def test_create_saas_not_found(
        self, mock_get_stripe, auth_client: AsyncClient, mock_db_session
    ):
        mock_db_session.execute.side_effect = [_mock_result(None)]

        response = await auth_client.post(
            f"/platform/{uuid4()}/customers",
            json={
                "external_id": "ext-1",
                "email": "x@x.com",
            },
        )

        assert response.status_code == 404


class TestListCustomers:
    """Tests for GET /platform/{saas_id}/customers."""

    @pytest.mark.asyncio
    async def test_list_success(
        self, auth_client: AsyncClient, mock_db_session, mock_saas, mock_customer, saas_id
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_list_result([mock_customer]),
        ]

        response = await auth_client.get(f"/platform/{saas_id}/customers")

        assert response.status_code == 200
        assert len(response.json()) == 1

    @pytest.mark.asyncio
    async def test_list_with_pagination(
        self, auth_client: AsyncClient, mock_db_session, mock_saas, saas_id
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_list_result([]),
        ]

        response = await auth_client.get(f"/platform/{saas_id}/customers?limit=10&offset=5")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_limit_is_bounded_by_the_settings(
        self, auth_client: AsyncClient, mock_saas, saas_id, monkeypatch
    ):
        """A limit above LIST_MAX_LIMIT is rejected; the bound is read when routes load."""
        from billing.config import settings

        too_big = settings.list_max_limit + 1
        response = await auth_client.get(f"/platform/{saas_id}/customers?limit={too_big}")

        assert response.status_code == 422


class TestGetCustomer:
    """Tests for GET /platform/{saas_id}/customers/{customer_id}."""

    @pytest.mark.asyncio
    async def test_get_success(
        self,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_customer,
        saas_id,
        customer_id,
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_customer),
        ]

        response = await auth_client.get(f"/platform/{saas_id}/customers/{customer_id}")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_not_found(
        self, auth_client: AsyncClient, mock_db_session, mock_saas, saas_id
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(None),
        ]

        response = await auth_client.get(f"/platform/{saas_id}/customers/{uuid4()}")

        assert response.status_code == 404


class TestUpdateCustomer:
    """Tests for PATCH /platform/{saas_id}/customers/{customer_id}."""

    @pytest.mark.asyncio
    @patch("billing.routes.platform.customers.get_stripe_service")
    async def test_update_success(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_customer,
        saas_id,
        customer_id,
    ):
        mock_stripe = MagicMock()
        mock_get_stripe.return_value = mock_stripe

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_customer),
        ]

        response = await auth_client.patch(
            f"/platform/{saas_id}/customers/{customer_id}",
            json={
                "email": "updated@example.com",
            },
        )

        assert response.status_code == 200
        mock_stripe.update_customer.assert_called_once()

    @pytest.mark.asyncio
    @patch("billing.routes.platform.customers.get_stripe_service")
    async def test_update_not_found(
        self, mock_get_stripe, auth_client: AsyncClient, mock_db_session, mock_saas, saas_id
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(None),
        ]

        response = await auth_client.patch(
            f"/platform/{saas_id}/customers/{uuid4()}", json={"email": "x@x.com"}
        )

        assert response.status_code == 404


class TestGetCustomerPortal:
    """Tests for GET /platform/{saas_id}/customers/{customer_id}/portal."""

    @pytest.mark.asyncio
    @patch("billing.routes.platform.customers.get_stripe_service")
    async def test_portal_success(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_customer,
        saas_id,
        customer_id,
    ):
        mock_stripe = MagicMock()
        mock_session = MagicMock()
        mock_session.url = "https://billing.stripe.com/session/123"
        mock_stripe.create_customer_portal_session.return_value = mock_session
        mock_get_stripe.return_value = mock_stripe

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_customer),
        ]

        response = await auth_client.get(
            f"/platform/{saas_id}/customers/{customer_id}/portal?return_url=https://example.com"
        )

        assert response.status_code == 200
        assert response.json()["url"] == "https://billing.stripe.com/session/123"

    @pytest.mark.asyncio
    @patch("billing.routes.platform.customers.get_stripe_service")
    async def test_portal_customer_not_found(
        self, mock_get_stripe, auth_client: AsyncClient, mock_db_session, mock_saas, saas_id
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(None),
        ]

        response = await auth_client.get(
            f"/platform/{saas_id}/customers/{uuid4()}/portal?return_url=https://example.com"
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    @patch("billing.routes.platform.customers.get_stripe_service")
    async def test_portal_refuses_a_return_url_outside_the_allowlist(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        saas_id,
        customer_id,
    ):
        mock_db_session.execute.side_effect = [_mock_result(mock_saas)]

        response = await auth_client.get(
            f"/platform/{saas_id}/customers/{customer_id}/portal?return_url=https://evil.test"
        )

        assert response.status_code == 422
        assert "return_url" in response.json()["detail"]
        mock_get_stripe.return_value.create_customer_portal_session.assert_not_called()

    @pytest.mark.asyncio
    @patch("billing.routes.platform.customers.get_stripe_service")
    async def test_portal_refuses_any_url_without_allowlist(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        saas_id,
        customer_id,
    ):
        mock_saas.checkout_url_allowlist = None
        mock_db_session.execute.side_effect = [_mock_result(mock_saas)]

        response = await auth_client.get(
            f"/platform/{saas_id}/customers/{customer_id}/portal?return_url=https://example.com"
        )

        assert response.status_code == 422
