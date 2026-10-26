# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for usage reporting routes."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
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
    s.stripe_subscription_item_id = "si_test123"
    return s


@pytest.fixture
def mock_subscription_no_item(subscription_id):
    s = MagicMock()
    s.id = subscription_id
    s.stripe_subscription_item_id = None
    return s


class TestReportUsage:
    """Tests for POST /usage/{saas_id}/report."""

    @pytest.mark.asyncio
    async def test_report_success(
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

        response = await auth_client.post(
            f"/usage/{saas_id}/report",
            json={
                "subscription_id": subscription_id,
                "quantity": 10,
                "action": "api_call",
            },
        )

        assert response.status_code == 201
        mock_db_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_report_with_idempotency_new(
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
            _mock_result(None),  # No existing event with this key
        ]

        response = await auth_client.post(
            f"/usage/{saas_id}/report",
            json={
                "subscription_id": subscription_id,
                "quantity": 5,
                "idempotency_key": "unique-key-123",
            },
        )

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_report_with_idempotency_duplicate(
        self,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        saas_id,
        subscription_id,
    ):
        existing_event = MagicMock()
        existing_event.id = str(uuid4())
        existing_event.subscription_id = subscription_id
        existing_event.quantity = 5
        existing_event.status = "pending"
        existing_event.timestamp = "2024-01-01T00:00:00Z"
        existing_event.idempotency_key = "dup-key"
        existing_event.action = "api_call"
        existing_event.metadata = None
        existing_event.stripe_usage_record_id = None
        existing_event.reported_at = None
        existing_event.error_message = None
        existing_event.created_at = "2024-01-01T00:00:00Z"
        existing_event.updated_at = "2024-01-01T00:00:00Z"

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
            _mock_result(existing_event),
        ]

        response = await auth_client.post(
            f"/usage/{saas_id}/report",
            json={
                "subscription_id": subscription_id,
                "quantity": 5,
                "idempotency_key": "dup-key",
            },
        )

        assert response.status_code == 201
        mock_db_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_report_saas_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.execute.side_effect = [_mock_result(None)]

        response = await auth_client.post(
            f"/usage/{uuid4()}/report",
            json={
                "subscription_id": str(uuid4()),
                "quantity": 1,
            },
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_report_subscription_not_found(
        self, auth_client: AsyncClient, mock_db_session, mock_saas, saas_id
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(None),
        ]

        response = await auth_client.post(
            f"/usage/{saas_id}/report",
            json={
                "subscription_id": str(uuid4()),
                "quantity": 1,
            },
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_report_no_metered_billing(
        self,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription_no_item,
        saas_id,
        subscription_id,
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription_no_item),
        ]

        response = await auth_client.post(
            f"/usage/{saas_id}/report",
            json={
                "subscription_id": subscription_id,
                "quantity": 1,
            },
        )

        assert response.status_code == 400


class TestReportUsageBatch:
    """Tests for POST /usage/{saas_id}/batch."""

    @pytest.mark.asyncio
    async def test_batch_success(
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
            _mock_result(mock_subscription),
        ]

        response = await auth_client.post(
            f"/usage/{saas_id}/batch",
            json={
                "events": [
                    {"subscription_id": subscription_id, "quantity": 5},
                    {"subscription_id": subscription_id, "quantity": 10},
                ],
            },
        )

        assert response.status_code == 201
        assert len(response.json()) == 2

    @pytest.mark.asyncio
    async def test_batch_subscription_not_found(
        self, auth_client: AsyncClient, mock_db_session, mock_saas, saas_id
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(None),
        ]

        response = await auth_client.post(
            f"/usage/{saas_id}/batch",
            json={
                "events": [
                    {"subscription_id": str(uuid4()), "quantity": 5},
                ],
            },
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_batch_no_metered(
        self,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription_no_item,
        saas_id,
        subscription_id,
    ):
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription_no_item),
        ]

        response = await auth_client.post(
            f"/usage/{saas_id}/batch",
            json={
                "events": [
                    {"subscription_id": subscription_id, "quantity": 5},
                ],
            },
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_batch_with_idempotency_new(
        self,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        saas_id,
        subscription_id,
    ):
        """Batch with idempotency key where no duplicate exists -> creates new event."""
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
            _mock_result(None),  # Idempotency check -> not found
        ]

        response = await auth_client.post(
            f"/usage/{saas_id}/batch",
            json={
                "events": [
                    {
                        "subscription_id": subscription_id,
                        "quantity": 5,
                        "idempotency_key": "new-key",
                    },
                ],
            },
        )

        assert response.status_code == 201
        assert len(response.json()) == 1

    @pytest.mark.asyncio
    async def test_batch_with_idempotency_duplicate(
        self,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        saas_id,
        subscription_id,
    ):
        existing_event = MagicMock()
        existing_event.id = str(uuid4())
        existing_event.subscription_id = subscription_id
        existing_event.quantity = 5
        existing_event.status = "pending"
        existing_event.timestamp = "2024-01-01T00:00:00Z"
        existing_event.idempotency_key = "dup-batch"
        existing_event.action = None
        existing_event.metadata = None
        existing_event.stripe_usage_record_id = None
        existing_event.reported_at = None
        existing_event.error_message = None
        existing_event.created_at = "2024-01-01T00:00:00Z"
        existing_event.updated_at = "2024-01-01T00:00:00Z"

        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
            _mock_result(existing_event),  # Idempotency hit
        ]

        response = await auth_client.post(
            f"/usage/{saas_id}/batch",
            json={
                "events": [
                    {
                        "subscription_id": subscription_id,
                        "quantity": 5,
                        "idempotency_key": "dup-batch",
                    },
                ],
            },
        )

        assert response.status_code == 201
        assert len(response.json()) == 1

    @pytest.mark.asyncio
    async def test_report_requires_auth(self, client: AsyncClient):
        response = await client.post(
            f"/usage/{uuid4()}/report",
            json={
                "subscription_id": str(uuid4()),
                "quantity": 1,
            },
        )
        assert response.status_code == 401


class TestUsageIdempotencyScoping:
    """Idempotency keys belong to one SaaS app."""

    @pytest.mark.asyncio
    async def test_events_record_their_saas_app(
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

        response = await auth_client.post(
            f"/usage/{saas_id}/report",
            json={"subscription_id": subscription_id, "quantity": 2},
        )

        assert response.status_code == 201
        assert mock_db_session.add.call_args[0][0].saas_app_id == saas_id

    @pytest.mark.asyncio
    async def test_idempotency_lookup_is_scoped_to_the_saas_app(
        self,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        saas_id,
        subscription_id,
    ):
        """The same key used by another SaaS app must not be seen as a duplicate."""
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
            _mock_result(None),
        ]

        await auth_client.post(
            f"/usage/{saas_id}/report",
            json={"subscription_id": subscription_id, "quantity": 2, "idempotency_key": "k-1"},
        )

        lookup = mock_db_session.execute.call_args_list[-1][0][0].compile()
        assert "usage_events.saas_app_id" in str(lookup)
        assert saas_id in lookup.params.values()
        assert "k-1" in lookup.params.values()

    @pytest.mark.asyncio
    async def test_batch_collapses_a_repeated_key(
        self,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas,
        mock_subscription,
        saas_id,
        subscription_id,
    ):
        """Two events with the same key in one batch are recorded once."""
        mock_db_session.execute.side_effect = [
            _mock_result(mock_saas),
            _mock_result(mock_subscription),
            _mock_result(None),  # first event: no stored duplicate
            _mock_result(mock_subscription),  # second event: subscription only
        ]
        event = {"subscription_id": subscription_id, "quantity": 1, "idempotency_key": "same"}

        response = await auth_client.post(
            f"/usage/{saas_id}/batch", json={"events": [event, event]}
        )

        assert response.status_code == 201
        assert mock_db_session.add.call_count == 1
        assert len(response.json()) == 2

    @pytest.mark.asyncio
    async def test_batch_size_is_bounded_by_the_settings(
        self, auth_client: AsyncClient, saas_id, subscription_id
    ):
        from billing.config import settings

        events = [{"subscription_id": subscription_id, "quantity": 1}] * (
            settings.usage_batch_max_events + 1
        )

        response = await auth_client.post(f"/usage/{saas_id}/batch", json={"events": events})

        assert response.status_code == 422
