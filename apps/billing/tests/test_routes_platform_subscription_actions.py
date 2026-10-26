# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the cancel and reactivate actions of platform subscriptions."""

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


@pytest.fixture
def saas_id():
    return str(uuid4())


@pytest.fixture
def subscription_id():
    return str(uuid4())


@pytest.fixture
def mock_saas(saas_id):
    app = MagicMock()
    app.id = saas_id
    app.slug = "test-app"
    return app


@pytest.fixture
def mock_subscription(subscription_id):
    s = MagicMock()
    s.id = subscription_id
    s.customer_id = str(uuid4())
    s.price_id = str(uuid4())
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


def _stripe(status: str, cancel_at_period_end: bool) -> MagicMock:
    stripe_sub = MagicMock()
    stripe_sub.status = status
    stripe_sub.cancel_at_period_end = cancel_at_period_end
    return stripe_sub


class TestCancelAction:
    """Tests for POST /platform/{saas_id}/subscriptions/{id}/cancel."""

    @pytest.mark.asyncio
    @patch("billing.routes.platform.subscriptions.get_stripe_service")
    async def test_default_cancels_at_period_end(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        saas_id,
        subscription_id,
    ):
        """Without a body the subscription keeps running until the period ends."""
        mock_stripe = mock_get_stripe.return_value
        mock_stripe.cancel_subscription.return_value = _stripe("active", True)
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
        ]

        response = await auth_client.post(
            f"/platform/{saas_id}/subscriptions/{subscription_id}/cancel"
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "active"
        assert body["cancel_at_period_end"] is True
        assert body["canceled_at"] is None
        mock_stripe.cancel_subscription.assert_called_once_with(
            stripe_subscription_id="sub_test123", immediately=False
        )

    @pytest.mark.asyncio
    @patch("billing.routes.platform.subscriptions.get_stripe_service")
    async def test_cancel_at_period_end_true_in_the_body(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        saas_id,
        subscription_id,
    ):
        mock_stripe = mock_get_stripe.return_value
        mock_stripe.cancel_subscription.return_value = _stripe("active", True)
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
        ]

        response = await auth_client.post(
            f"/platform/{saas_id}/subscriptions/{subscription_id}/cancel",
            json={"cancel_at_period_end": True},
        )

        assert response.status_code == 200
        assert mock_stripe.cancel_subscription.call_args.kwargs["immediately"] is False

    @pytest.mark.asyncio
    @patch("billing.routes.platform.subscriptions.get_stripe_service")
    async def test_immediate_cancellation(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        saas_id,
        subscription_id,
    ):
        mock_stripe = mock_get_stripe.return_value
        mock_stripe.cancel_subscription.return_value = _stripe("canceled", False)
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
        ]

        response = await auth_client.post(
            f"/platform/{saas_id}/subscriptions/{subscription_id}/cancel",
            json={"cancel_at_period_end": False},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "canceled"
        assert body["canceled_at"] is not None
        assert mock_stripe.cancel_subscription.call_args.kwargs["immediately"] is True

    @pytest.mark.asyncio
    @patch("billing.routes.platform.subscriptions.get_stripe_service")
    async def test_already_canceled_conflicts(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        saas_id,
        subscription_id,
    ):
        mock_subscription.status = SubscriptionStatus.CANCELED
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
        ]

        response = await auth_client.post(
            f"/platform/{saas_id}/subscriptions/{subscription_id}/cancel"
        )

        assert response.status_code == 409
        mock_get_stripe.return_value.cancel_subscription.assert_not_called()

    @pytest.mark.asyncio
    @patch("billing.routes.platform.subscriptions.get_stripe_service")
    async def test_stripe_failure_is_a_bad_gateway(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        saas_id,
        subscription_id,
    ):
        mock_get_stripe.return_value.cancel_subscription.side_effect = RuntimeError("boom")
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
        ]

        response = await auth_client.post(
            f"/platform/{saas_id}/subscriptions/{subscription_id}/cancel"
        )

        assert response.status_code == 502
        assert mock_subscription.cancel_at_period_end is False

    @pytest.mark.asyncio
    async def test_unknown_subscription(
        self, auth_client: AsyncClient, mock_db_session, mock_saas, saas_id
    ):
        mock_db_session.execute.side_effect = [_mock_result(mock_saas), _mock_result(None)]

        response = await auth_client.post(f"/platform/{saas_id}/subscriptions/{uuid4()}/cancel")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_unknown_saas(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.execute.side_effect = [_mock_result(None)]

        response = await auth_client.post(f"/platform/{uuid4()}/subscriptions/{uuid4()}/cancel")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_requires_authentication(self, client: AsyncClient):
        response = await client.post(f"/platform/{uuid4()}/subscriptions/{uuid4()}/cancel")

        assert response.status_code == 401


class TestReactivateAction:
    """Tests for POST /platform/{saas_id}/subscriptions/{id}/reactivate."""

    @pytest.mark.asyncio
    @patch("billing.routes.platform.subscriptions.get_stripe_service")
    async def test_reactivates_a_scheduled_cancellation(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        saas_id,
        subscription_id,
    ):
        mock_subscription.cancel_at_period_end = True
        mock_stripe = mock_get_stripe.return_value
        mock_stripe.update_subscription.return_value = _stripe("active", False)
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
        ]

        response = await auth_client.post(
            f"/platform/{saas_id}/subscriptions/{subscription_id}/reactivate"
        )

        assert response.status_code == 200
        assert response.json()["cancel_at_period_end"] is False
        mock_stripe.update_subscription.assert_called_once_with(
            stripe_subscription_id="sub_test123", cancel_at_period_end=False
        )

    @pytest.mark.asyncio
    @patch("billing.routes.platform.subscriptions.get_stripe_service")
    async def test_reactivating_a_running_subscription_is_a_noop(
        self,
        mock_get_stripe,
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

        response = await auth_client.post(
            f"/platform/{saas_id}/subscriptions/{subscription_id}/reactivate"
        )

        assert response.status_code == 200
        assert response.json()["status"] == "active"
        mock_get_stripe.return_value.update_subscription.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "final", [SubscriptionStatus.CANCELED, SubscriptionStatus.INCOMPLETE_EXPIRED]
    )
    @patch("billing.routes.platform.subscriptions.get_stripe_service")
    async def test_a_final_subscription_cannot_be_reactivated(
        self,
        mock_get_stripe,
        final,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        saas_id,
        subscription_id,
    ):
        mock_subscription.status = final
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
        ]

        response = await auth_client.post(
            f"/platform/{saas_id}/subscriptions/{subscription_id}/reactivate"
        )

        assert response.status_code == 409
        assert "new subscription" in response.json()["detail"]
        mock_get_stripe.return_value.update_subscription.assert_not_called()

    @pytest.mark.asyncio
    @patch("billing.routes.platform.subscriptions.get_stripe_service")
    async def test_stripe_failure_is_a_bad_gateway(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        saas_id,
        subscription_id,
    ):
        mock_subscription.cancel_at_period_end = True
        mock_get_stripe.return_value.update_subscription.side_effect = RuntimeError("boom")
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
        ]

        response = await auth_client.post(
            f"/platform/{saas_id}/subscriptions/{subscription_id}/reactivate"
        )

        assert response.status_code == 502

    @pytest.mark.asyncio
    async def test_unknown_subscription(
        self, auth_client: AsyncClient, mock_db_session, mock_saas, saas_id
    ):
        mock_db_session.execute.side_effect = [_mock_result(mock_saas), _mock_result(None)]

        response = await auth_client.post(f"/platform/{saas_id}/subscriptions/{uuid4()}/reactivate")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_requires_authentication(self, client: AsyncClient):
        response = await client.post(f"/platform/{uuid4()}/subscriptions/{uuid4()}/reactivate")

        assert response.status_code == 401
