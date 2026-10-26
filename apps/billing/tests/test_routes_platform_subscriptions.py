# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for platform subscription routes."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from billing.models.subscription import SubscriptionStatus
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
def subscription_id():
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
def mock_customer(customer_id, saas_id):
    c = MagicMock()
    c.id = customer_id
    c.saas_app_id = saas_id
    c.external_id = "ext-123"
    c.stripe_customer_id = "cus_test123"
    c.email = "test@example.com"
    return c


@pytest.fixture
def mock_subscription(subscription_id, customer_id, price_id):
    s = MagicMock()
    s.id = subscription_id
    s.customer_id = customer_id
    s.price_id = price_id
    s.stripe_subscription_id = "sub_test123"
    s.stripe_subscription_item_id = "si_test123"
    s.status = SubscriptionStatus.ACTIVE
    s.current_period_start = datetime(2024, 1, 1, tzinfo=UTC)
    s.current_period_end = datetime(2024, 2, 1, tzinfo=UTC)
    s.cancel_at_period_end = False
    s.canceled_at = None
    s.extra_data = None
    s.created_at = datetime(2024, 1, 1, tzinfo=UTC)
    s.updated_at = datetime(2024, 1, 1, tzinfo=UTC)
    return s


@pytest.fixture
def mock_price(price_id, saas_id):
    p = MagicMock()
    p.id = price_id
    p.stripe_price_id = "price_test123"
    p.unit_amount = 2000
    p.product = MagicMock()
    p.product.name = "Pro Plan"
    p.product.saas_app_id = saas_id
    return p


class TestListSubscriptions:
    @pytest.mark.asyncio
    async def test_list_success(
        self, auth_client: AsyncClient, mock_db_session, mock_saas, mock_subscription, saas_id
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_list_result([mock_subscription]),
        ]
        response = await auth_client.get(f"/platform/{saas_id}/subscriptions")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_saas_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.execute.side_effect = [_mock_result(None)]
        response = await auth_client.get(f"/platform/{uuid4()}/subscriptions")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_with_status_filter(
        self, auth_client: AsyncClient, mock_db_session, mock_saas, saas_id
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_list_result([]),
        ]
        response = await auth_client.get(f"/platform/{saas_id}/subscriptions?status_filter=active")
        assert response.status_code == 200


class TestListCustomerSubscriptions:
    @pytest.mark.asyncio
    async def test_list_success(
        self,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_customer,
        mock_subscription,
        saas_id,
        customer_id,
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_customer),
            _mock_list_result([mock_subscription]),
        ]
        response = await auth_client.get(
            f"/platform/{saas_id}/customers/{customer_id}/subscriptions"
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_customer_not_found(
        self, auth_client: AsyncClient, mock_db_session, mock_saas, saas_id
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(None),
        ]
        response = await auth_client.get(f"/platform/{saas_id}/customers/{uuid4()}/subscriptions")
        assert response.status_code == 404


class TestGetSubscriptionByExternalId:
    @pytest.mark.asyncio
    async def test_found(
        self,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_customer,
        mock_subscription,
        saas_id,
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_customer),
            _mock_result(mock_subscription),
        ]
        response = await auth_client.get(f"/platform/{saas_id}/external/ext-123/subscription")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_customer_not_found(
        self, auth_client: AsyncClient, mock_db_session, mock_saas, saas_id
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(None),
        ]
        response = await auth_client.get(f"/platform/{saas_id}/external/missing/subscription")
        assert response.status_code == 200
        assert response.json() is None

    @pytest.mark.asyncio
    async def test_no_subscription(
        self, auth_client: AsyncClient, mock_db_session, mock_saas, mock_customer, saas_id
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_customer),
            _mock_result(None),
        ]
        response = await auth_client.get(f"/platform/{saas_id}/external/ext-123/subscription")
        assert response.status_code == 200
        assert response.json() is None


class TestGetSubscription:
    @pytest.mark.asyncio
    async def test_get_success(
        self,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        saas_id,
        subscription_id,
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
        ]
        response = await auth_client.get(f"/platform/{saas_id}/subscriptions/{subscription_id}")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_not_found(
        self, auth_client: AsyncClient, mock_db_session, mock_saas, saas_id
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(None),
        ]
        response = await auth_client.get(f"/platform/{saas_id}/subscriptions/{uuid4()}")
        assert response.status_code == 404


class TestCreateSubscription:
    @pytest.mark.asyncio
    @patch("billing.routes.platform.subscriptions.get_stripe_service")
    async def test_create_success(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_customer,
        saas_id,
        customer_id,
        price_id,
    ):
        mock_stripe = MagicMock()
        mock_stripe_sub = MagicMock()
        mock_stripe_sub.id = "sub_new123"
        mock_stripe_sub.status = "active"
        mock_stripe_sub.items = MagicMock()
        mock_stripe_sub.items.data = [MagicMock(id="si_item1")]
        mock_stripe_sub.get.return_value = 1704067200  # timestamp
        mock_stripe.create_subscription.return_value = mock_stripe_sub
        mock_get_stripe.return_value = mock_stripe

        mock_price_obj = MagicMock()
        mock_price_obj.id = price_id
        mock_price_obj.stripe_price_id = "price_test123"

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_customer),
            _mock_result(mock_price_obj),
        ]

        response = await auth_client.post(
            f"/platform/{saas_id}/customers/{customer_id}/subscriptions",
            json={
                "price_id": price_id,
            },
        )

        assert response.status_code == 201

    @pytest.mark.asyncio
    @patch("billing.routes.platform.subscriptions.get_stripe_service")
    async def test_create_no_period(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_customer,
        saas_id,
        customer_id,
        price_id,
    ):
        mock_stripe = MagicMock()
        mock_stripe_sub = MagicMock()
        mock_stripe_sub.id = "sub_new123"
        mock_stripe_sub.status = "active"
        mock_stripe_sub.items = MagicMock()
        mock_stripe_sub.items.data = []
        mock_stripe_sub.get.return_value = None
        mock_stripe.create_subscription.return_value = mock_stripe_sub
        mock_get_stripe.return_value = mock_stripe

        mock_price_obj = MagicMock()
        mock_price_obj.id = price_id
        mock_price_obj.stripe_price_id = "price_test"

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_customer),
            _mock_result(mock_price_obj),
        ]

        response = await auth_client.post(
            f"/platform/{saas_id}/customers/{customer_id}/subscriptions",
            json={
                "price_id": price_id,
            },
        )

        assert response.status_code == 201

    @pytest.mark.asyncio
    @patch("billing.routes.platform.subscriptions.get_stripe_service")
    async def test_create_customer_not_found(
        self, mock_get_stripe, auth_client: AsyncClient, mock_db_session, mock_saas, saas_id
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(None),
        ]
        response = await auth_client.post(
            f"/platform/{saas_id}/customers/{uuid4()}/subscriptions",
            json={
                "price_id": str(uuid4()),
            },
        )
        assert response.status_code == 404
        assert "Customer not found" in response.json()["detail"]

    @pytest.mark.asyncio
    @patch("billing.routes.platform.subscriptions.get_stripe_service")
    async def test_create_price_not_found(
        self,
        mock_get_stripe,
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
            _mock_result(None),
        ]
        response = await auth_client.post(
            f"/platform/{saas_id}/customers/{customer_id}/subscriptions",
            json={
                "price_id": str(uuid4()),
            },
        )
        assert response.status_code == 404
        assert "Price not found" in response.json()["detail"]


class TestUpdateSubscription:
    @pytest.mark.asyncio
    @patch("billing.routes.platform.subscriptions.get_stripe_service")
    async def test_update_success(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        saas_id,
        subscription_id,
    ):
        mock_get_stripe.return_value = MagicMock()
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
        ]
        response = await auth_client.patch(
            f"/platform/{saas_id}/subscriptions/{subscription_id}",
            json={
                "cancel_at_period_end": True,
            },
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    @patch("billing.routes.platform.subscriptions.get_stripe_service")
    async def test_update_not_found(
        self, mock_get_stripe, auth_client: AsyncClient, mock_db_session, mock_saas, saas_id
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(None),
        ]
        response = await auth_client.patch(
            f"/platform/{saas_id}/subscriptions/{uuid4()}",
            json={
                "cancel_at_period_end": True,
            },
        )
        assert response.status_code == 404


class TestCancelSubscription:
    @pytest.mark.asyncio
    @patch("billing.routes.platform.subscriptions.get_stripe_service")
    async def test_cancel_at_period_end(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        saas_id,
        subscription_id,
    ):
        mock_stripe = MagicMock()
        mock_stripe_sub = MagicMock()
        mock_stripe_sub.status = "active"
        mock_stripe_sub.cancel_at_period_end = True
        mock_stripe.cancel_subscription.return_value = mock_stripe_sub
        mock_get_stripe.return_value = mock_stripe

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
        ]
        response = await auth_client.delete(f"/platform/{saas_id}/subscriptions/{subscription_id}")
        assert response.status_code == 200

    @pytest.mark.asyncio
    @patch("billing.routes.platform.subscriptions.get_stripe_service")
    async def test_cancel_immediately(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        saas_id,
        subscription_id,
    ):
        mock_stripe = MagicMock()
        mock_stripe_sub = MagicMock()
        mock_stripe_sub.status = "canceled"
        mock_stripe_sub.cancel_at_period_end = False
        mock_stripe.cancel_subscription.return_value = mock_stripe_sub
        mock_get_stripe.return_value = mock_stripe

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
        ]
        response = await auth_client.delete(
            f"/platform/{saas_id}/subscriptions/{subscription_id}?immediately=true"
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    @patch("billing.routes.platform.subscriptions.get_stripe_service")
    async def test_cancel_not_found(
        self, mock_get_stripe, auth_client: AsyncClient, mock_db_session, mock_saas, saas_id
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(None),
        ]
        response = await auth_client.delete(f"/platform/{saas_id}/subscriptions/{uuid4()}")
        assert response.status_code == 404


class TestSyncSubscription:
    @pytest.mark.asyncio
    @patch("billing.routes.platform.subscriptions.get_stripe_service")
    async def test_sync_success(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        saas_id,
        subscription_id,
    ):
        mock_stripe = MagicMock()
        mock_stripe_sub = MagicMock()
        mock_stripe_sub.status = "active"
        mock_stripe_sub.cancel_at_period_end = False
        mock_stripe_sub.canceled_at = None
        mock_stripe_sub.__getitem__ = lambda self, key: {
            "items": MagicMock(
                data=[
                    {
                        "id": "si_new",
                        "current_period_start": 1704067200,
                        "current_period_end": 1706745600,
                    }
                ]
            ),
        }.get(key)
        mock_stripe.get_subscription.return_value = mock_stripe_sub
        mock_get_stripe.return_value = mock_stripe

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
        ]
        response = await auth_client.post(
            f"/platform/{saas_id}/subscriptions/{subscription_id}/sync"
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    @patch("billing.routes.platform.subscriptions.get_stripe_service")
    async def test_sync_with_canceled_at(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        saas_id,
        subscription_id,
    ):
        mock_stripe = MagicMock()
        mock_stripe_sub = MagicMock()
        mock_stripe_sub.status = "canceled"
        mock_stripe_sub.cancel_at_period_end = True
        mock_stripe_sub.canceled_at = 1704067200
        mock_stripe_sub.__getitem__ = lambda self, key: None  # No items
        mock_stripe.get_subscription.return_value = mock_stripe_sub
        mock_get_stripe.return_value = mock_stripe

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
        ]
        response = await auth_client.post(
            f"/platform/{saas_id}/subscriptions/{subscription_id}/sync"
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    @patch("billing.routes.platform.subscriptions.get_stripe_service")
    async def test_sync_not_found(
        self, mock_get_stripe, auth_client: AsyncClient, mock_db_session, mock_saas, saas_id
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(None),
        ]
        response = await auth_client.post(f"/platform/{saas_id}/subscriptions/{uuid4()}/sync")
        assert response.status_code == 404

    @pytest.mark.asyncio
    @patch("billing.routes.platform.subscriptions.get_stripe_service")
    async def test_sync_items_attribute_error(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        saas_id,
        subscription_id,
    ):
        """Test sync when items access raises an error (covers exception handler)."""
        mock_stripe = MagicMock()
        mock_stripe_sub = MagicMock()
        mock_stripe_sub.status = "active"
        mock_stripe_sub.cancel_at_period_end = False
        mock_stripe_sub.canceled_at = None
        # Make items access raise KeyError
        mock_stripe_sub.__getitem__ = MagicMock(side_effect=KeyError("items"))
        mock_stripe.get_subscription.return_value = mock_stripe_sub
        mock_get_stripe.return_value = mock_stripe

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
        ]
        response = await auth_client.post(
            f"/platform/{saas_id}/subscriptions/{subscription_id}/sync"
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    @patch("billing.routes.platform.subscriptions.get_stripe_service")
    async def test_sync_stripe_error(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        saas_id,
        subscription_id,
    ):
        mock_stripe = MagicMock()
        mock_stripe.get_subscription.side_effect = Exception("Stripe error")
        mock_get_stripe.return_value = mock_stripe

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
        ]
        response = await auth_client.post(
            f"/platform/{saas_id}/subscriptions/{subscription_id}/sync"
        )
        assert response.status_code == 502


class TestPreviewSubscriptionUpgrade:
    @pytest.mark.asyncio
    @patch("billing.routes.platform.subscriptions.get_stripe_service")
    async def test_preview_success(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        mock_price,
        saas_id,
        subscription_id,
    ):
        new_price_id = str(uuid4())
        new_price = MagicMock()
        new_price.id = new_price_id
        new_price.stripe_price_id = "price_new123"
        new_price.unit_amount = 5000
        new_price.product = MagicMock()
        new_price.product.name = "Enterprise"
        new_price.product.saas_app_id = saas_id

        mock_subscription.price = mock_price
        mock_subscription.price_id = mock_price.id

        mock_stripe = MagicMock()
        mock_invoice = MagicMock()
        mock_invoice.currency = "usd"
        mock_line_item = MagicMock()
        mock_line_item.get.side_effect = lambda k, d=None: {
            "proration": True,
            "description": "Unused time",
        }.get(k, d)
        mock_line_item.amount = -500
        mock_line_item.currency = "usd"
        mock_invoice.lines.data = [mock_line_item]
        mock_stripe.preview_subscription_upgrade.return_value = mock_invoice
        mock_get_stripe.return_value = mock_stripe

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
            _mock_result(new_price),
        ]

        response = await auth_client.post(
            f"/platform/{saas_id}/subscriptions/{subscription_id}/upgrade/preview",
            json={
                "new_price_id": new_price_id,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["credit_applied"] == 500

    @pytest.mark.asyncio
    @patch("billing.routes.platform.subscriptions.get_stripe_service")
    async def test_preview_non_proration_line_detected_by_description(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        mock_price,
        saas_id,
        subscription_id,
    ):
        new_price_id = str(uuid4())
        new_price = MagicMock()
        new_price.id = new_price_id
        new_price.stripe_price_id = "price_new"
        new_price.unit_amount = 5000
        new_price.product = MagicMock()
        new_price.product.name = "Enterprise"
        new_price.product.saas_app_id = saas_id

        mock_subscription.price = mock_price
        mock_subscription.price_id = mock_price.id

        mock_stripe = MagicMock()
        mock_invoice = MagicMock()
        mock_invoice.currency = "usd"
        # Line item not marked as proration, but description contains "Remaining time"
        mock_line_item = MagicMock()
        mock_line_item.get.side_effect = lambda k, d=None: {
            "proration": False,
            "description": "Remaining time on Pro",
        }.get(k, d)
        mock_line_item.amount = 1500
        mock_line_item.currency = "usd"
        # Second item: regular charge (not proration, no proration description)
        mock_regular_item = MagicMock()
        mock_regular_item.get.side_effect = lambda k, d=None: {
            "proration": False,
            "description": "Pro Plan monthly",
        }.get(k, d)
        mock_regular_item.amount = 2000
        mock_regular_item.currency = "usd"
        mock_invoice.lines.data = [mock_line_item, mock_regular_item]
        mock_stripe.preview_subscription_upgrade.return_value = mock_invoice
        mock_get_stripe.return_value = mock_stripe

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
            _mock_result(new_price),
        ]

        response = await auth_client.post(
            f"/platform/{saas_id}/subscriptions/{subscription_id}/upgrade/preview",
            json={
                "new_price_id": new_price_id,
            },
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    @patch("billing.routes.platform.subscriptions.get_stripe_service")
    async def test_preview_no_current_price(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        saas_id,
        subscription_id,
    ):
        new_price_id = str(uuid4())
        new_price = MagicMock()
        new_price.id = new_price_id
        new_price.stripe_price_id = "price_new"
        new_price.unit_amount = 5000
        new_price.product = MagicMock()
        new_price.product.name = "Enterprise"
        new_price.product.saas_app_id = saas_id

        mock_subscription.price = None
        mock_subscription.price_id = None

        mock_stripe = MagicMock()
        mock_invoice = MagicMock()
        mock_invoice.currency = "usd"
        mock_invoice.lines.data = []
        mock_stripe.preview_subscription_upgrade.return_value = mock_invoice
        mock_get_stripe.return_value = mock_stripe

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
            _mock_result(new_price),
        ]

        response = await auth_client.post(
            f"/platform/{saas_id}/subscriptions/{subscription_id}/upgrade/preview",
            json={
                "new_price_id": new_price_id,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["current_plan_name"] == "Unknown"
        assert data["current_price_amount"] == 0

    @pytest.mark.asyncio
    async def test_preview_inactive_subscription(
        self,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        saas_id,
        subscription_id,
    ):
        mock_subscription.status = SubscriptionStatus.CANCELED
        mock_subscription.price = MagicMock()

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
        ]

        response = await auth_client.post(
            f"/platform/{saas_id}/subscriptions/{subscription_id}/upgrade/preview",
            json={
                "new_price_id": str(uuid4()),
            },
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_preview_subscription_not_found(
        self, auth_client: AsyncClient, mock_db_session, mock_saas, saas_id
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(None),  # subscription not found
        ]
        response = await auth_client.post(
            f"/platform/{saas_id}/subscriptions/{uuid4()}/upgrade/preview",
            json={
                "new_price_id": str(uuid4()),
            },
        )
        assert response.status_code == 404
        assert "Subscription not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_preview_price_not_found(
        self,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        saas_id,
        subscription_id,
    ):
        mock_subscription.price = MagicMock()

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
            _mock_result(None),
        ]

        response = await auth_client.post(
            f"/platform/{saas_id}/subscriptions/{subscription_id}/upgrade/preview",
            json={
                "new_price_id": str(uuid4()),
            },
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_preview_wrong_saas(
        self,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        saas_id,
        subscription_id,
    ):
        mock_subscription.price = MagicMock()
        new_price = MagicMock()
        new_price.id = str(uuid4())
        new_price.product = MagicMock()
        new_price.product.saas_app_id = str(uuid4())  # Different saas

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
            _mock_result(new_price),
        ]

        response = await auth_client.post(
            f"/platform/{saas_id}/subscriptions/{subscription_id}/upgrade/preview",
            json={
                "new_price_id": new_price.id,
            },
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_preview_same_price(
        self,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        mock_price,
        saas_id,
        subscription_id,
        price_id,
    ):
        mock_subscription.price = mock_price
        mock_subscription.price_id = price_id

        new_price = MagicMock()
        new_price.id = price_id  # Same price
        new_price.product = MagicMock()
        new_price.product.saas_app_id = saas_id

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
            _mock_result(new_price),
        ]

        response = await auth_client.post(
            f"/platform/{saas_id}/subscriptions/{subscription_id}/upgrade/preview",
            json={
                "new_price_id": price_id,
            },
        )
        assert response.status_code == 400
        assert "Already subscribed" in response.json()["detail"]

    @pytest.mark.asyncio
    @patch("billing.routes.platform.subscriptions.get_stripe_service")
    async def test_preview_stripe_error(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        mock_price,
        saas_id,
        subscription_id,
    ):
        mock_subscription.price = mock_price
        mock_subscription.price_id = mock_price.id

        new_price_id = str(uuid4())
        new_price = MagicMock()
        new_price.id = new_price_id
        new_price.product = MagicMock()
        new_price.product.saas_app_id = saas_id

        mock_stripe = MagicMock()
        mock_stripe.preview_subscription_upgrade.side_effect = Exception("Stripe error")
        mock_get_stripe.return_value = mock_stripe

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
            _mock_result(new_price),
        ]

        response = await auth_client.post(
            f"/platform/{saas_id}/subscriptions/{subscription_id}/upgrade/preview",
            json={
                "new_price_id": new_price_id,
            },
        )
        assert response.status_code == 502


class TestUpgradeSubscription:
    @pytest.mark.asyncio
    @patch("billing.routes.platform.subscriptions.get_stripe_service")
    async def test_upgrade_success(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        mock_price,
        saas_id,
        subscription_id,
    ):
        new_price_id = str(uuid4())
        new_price = MagicMock()
        new_price.id = new_price_id
        new_price.stripe_price_id = "price_new"
        new_price.product = MagicMock()
        new_price.product.saas_app_id = saas_id

        mock_subscription.price = mock_price
        mock_subscription.price_id = mock_price.id

        mock_stripe = MagicMock()
        mock_stripe_sub = MagicMock()
        mock_stripe_sub.status = "active"
        mock_stripe_sub.items = MagicMock()
        mock_stripe_sub.items.data = [MagicMock(id="si_new")]
        mock_invoice = MagicMock()
        mock_invoice.amount_due = 1500
        mock_invoice.id = "inv_test"
        mock_stripe.upgrade_subscription.return_value = (mock_stripe_sub, mock_invoice)
        mock_get_stripe.return_value = mock_stripe

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
            _mock_result(new_price),
        ]

        response = await auth_client.post(
            f"/platform/{saas_id}/subscriptions/{subscription_id}/upgrade",
            json={
                "new_price_id": new_price_id,
                "proration_behavior": "always_invoice",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["amount_due"] == 1500
        assert data["invoice_id"] == "inv_test"

    @pytest.mark.asyncio
    @patch("billing.routes.platform.subscriptions.get_stripe_service")
    async def test_upgrade_no_invoice(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        mock_price,
        saas_id,
        subscription_id,
    ):
        new_price_id = str(uuid4())
        new_price = MagicMock()
        new_price.id = new_price_id
        new_price.stripe_price_id = "price_new"
        new_price.product = MagicMock()
        new_price.product.saas_app_id = saas_id

        mock_subscription.price = mock_price
        mock_subscription.price_id = mock_price.id

        mock_stripe = MagicMock()
        mock_stripe_sub = MagicMock()
        mock_stripe_sub.status = "active"
        mock_stripe_sub.items = MagicMock()
        mock_stripe_sub.items.data = []
        mock_stripe.upgrade_subscription.return_value = (mock_stripe_sub, None)
        mock_get_stripe.return_value = mock_stripe

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
            _mock_result(new_price),
        ]

        response = await auth_client.post(
            f"/platform/{saas_id}/subscriptions/{subscription_id}/upgrade",
            json={
                "new_price_id": new_price_id,
                "proration_behavior": "none",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["amount_due"] == 0
        assert data["proration_applied"] is False

    @pytest.mark.asyncio
    async def test_upgrade_inactive_subscription(
        self,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        saas_id,
        subscription_id,
    ):
        mock_subscription.status = SubscriptionStatus.CANCELED
        mock_subscription.price = MagicMock()

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
        ]

        response = await auth_client.post(
            f"/platform/{saas_id}/subscriptions/{subscription_id}/upgrade",
            json={
                "new_price_id": str(uuid4()),
            },
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_upgrade_price_not_found(
        self,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        saas_id,
        subscription_id,
    ):
        mock_subscription.price = MagicMock()

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
            _mock_result(None),
        ]

        response = await auth_client.post(
            f"/platform/{saas_id}/subscriptions/{subscription_id}/upgrade",
            json={
                "new_price_id": str(uuid4()),
            },
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_upgrade_wrong_saas(
        self,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        saas_id,
        subscription_id,
    ):
        mock_subscription.price = MagicMock()
        new_price = MagicMock()
        new_price.id = str(uuid4())
        new_price.product = MagicMock()
        new_price.product.saas_app_id = str(uuid4())

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
            _mock_result(new_price),
        ]

        response = await auth_client.post(
            f"/platform/{saas_id}/subscriptions/{subscription_id}/upgrade",
            json={
                "new_price_id": new_price.id,
            },
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_upgrade_same_price(
        self,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        mock_price,
        saas_id,
        subscription_id,
        price_id,
    ):
        mock_subscription.price = mock_price
        mock_subscription.price_id = price_id

        new_price = MagicMock()
        new_price.id = price_id
        new_price.product = MagicMock()
        new_price.product.saas_app_id = saas_id

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
            _mock_result(new_price),
        ]

        response = await auth_client.post(
            f"/platform/{saas_id}/subscriptions/{subscription_id}/upgrade",
            json={
                "new_price_id": price_id,
            },
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    @patch("billing.routes.platform.subscriptions.get_stripe_service")
    async def test_upgrade_stripe_error(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        mock_price,
        saas_id,
        subscription_id,
    ):
        mock_subscription.price = mock_price
        mock_subscription.price_id = mock_price.id

        new_price_id = str(uuid4())
        new_price = MagicMock()
        new_price.id = new_price_id
        new_price.product = MagicMock()
        new_price.product.saas_app_id = saas_id

        mock_stripe = MagicMock()
        mock_stripe.upgrade_subscription.side_effect = Exception("Stripe error")
        mock_get_stripe.return_value = mock_stripe

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
            _mock_result(new_price),
        ]

        response = await auth_client.post(
            f"/platform/{saas_id}/subscriptions/{subscription_id}/upgrade",
            json={
                "new_price_id": new_price_id,
            },
        )
        assert response.status_code == 502
