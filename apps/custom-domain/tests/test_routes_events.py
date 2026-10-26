# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/routes/events.py - Unit tests with mocks."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from custom_domain.models.enums import DomainStatus, ProvisioningStep
from custom_domain.routes.events import get_progress_for_status
from httpx import AsyncClient


class TestGetProgressForStatus:
    """Tests for get_progress_for_status function."""

    def test_pending_status(self):
        """Test progress for PENDING status."""
        progress = get_progress_for_status(DomainStatus.PENDING)
        assert progress.current_step is None
        assert progress.percentage == 0
        assert len(progress.steps_completed) == 0

    def test_dns_verifying_status(self):
        """Test progress for DNS_VERIFYING status."""
        progress = get_progress_for_status(DomainStatus.DNS_VERIFYING)
        assert progress.current_step == ProvisioningStep.DNS_CHECK.value
        assert progress.percentage == 10

    def test_dns_verified_status(self):
        """Test progress for DNS_VERIFIED status."""
        progress = get_progress_for_status(DomainStatus.DNS_VERIFIED)
        assert progress.percentage == 25
        assert ProvisioningStep.DNS_CHECK.value in progress.steps_completed

    def test_ssl_provisioning_status(self):
        """Test progress for SSL_PROVISIONING status."""
        progress = get_progress_for_status(DomainStatus.SSL_PROVISIONING)
        assert progress.current_step == ProvisioningStep.CERTBOT.value
        assert progress.percentage == 60

    def test_active_status(self):
        """Test progress for ACTIVE status."""
        progress = get_progress_for_status(DomainStatus.ACTIVE)
        assert progress.current_step is None
        assert progress.percentage == 100
        assert len(progress.steps_remaining) == 0

    def test_failed_status(self):
        """Test progress for FAILED status."""
        progress = get_progress_for_status(DomainStatus.FAILED)
        assert progress.percentage == 0

    def test_suspended_status(self):
        """Test progress for SUSPENDED status."""
        progress = get_progress_for_status(DomainStatus.SUSPENDED)
        assert progress.percentage == 0

    def test_expired_status(self):
        """Test progress for EXPIRED status."""
        progress = get_progress_for_status(DomainStatus.EXPIRED)
        assert progress.percentage == 0


class TestGetDomainStatus:
    """Tests for get domain status endpoint."""

    @pytest.mark.asyncio
    async def test_get_status_not_found(self, auth_client: AsyncClient, mock_db_session):
        """Test getting status for non-existent domain."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await auth_client.get(f"/api/v1/domains/{uuid4()}/status")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_status_success(
        self, auth_client: AsyncClient, mock_db_session, mock_custom_domain
    ):
        """Test getting status for an existing domain."""
        mock_custom_domain.client_id = "test-client-id"
        mock_custom_domain.id = uuid4()
        mock_custom_domain.status = DomainStatus.PENDING

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_custom_domain
        mock_db_session.execute.return_value = mock_result

        response = await auth_client.get(f"/api/v1/domains/{mock_custom_domain.id}/status")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "progress" in data
        assert "domain" in data

    @pytest.mark.asyncio
    async def test_get_status_forbidden(
        self, auth_client: AsyncClient, mock_db_session, mock_custom_domain
    ):
        """Test getting status for domain owned by another client."""
        mock_custom_domain.client_id = "other-client-id"
        mock_custom_domain.id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_custom_domain
        mock_db_session.execute.return_value = mock_result

        response = await auth_client.get(f"/api/v1/domains/{mock_custom_domain.id}/status")
        assert response.status_code == 403


class TestDomainEventsSSE:
    """Tests for domain events SSE endpoint."""

    @pytest.mark.asyncio
    async def test_events_not_found(self, auth_client: AsyncClient, mock_db_session):
        """Test getting events for non-existent domain."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await auth_client.get(f"/api/v1/domains/{uuid4()}/events")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_events_forbidden(
        self, auth_client: AsyncClient, mock_db_session, mock_custom_domain
    ):
        """Test getting events for domain owned by another client."""
        mock_custom_domain.client_id = "other-client-id"
        mock_custom_domain.id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_custom_domain
        mock_db_session.execute.return_value = mock_result

        response = await auth_client.get(f"/api/v1/domains/{mock_custom_domain.id}/events")
        assert response.status_code == 403


class TestGetEventHistory:
    """Tests for get event history endpoint."""

    @pytest.mark.asyncio
    async def test_get_history_not_found(self, auth_client: AsyncClient, mock_db_session):
        """Test getting history for non-existent domain."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await auth_client.get(f"/api/v1/domains/{uuid4()}/events/history")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_history_success(
        self, auth_client: AsyncClient, mock_db_session, mock_custom_domain
    ):
        """Test getting history for an existing domain."""
        mock_custom_domain.client_id = "test-client-id"
        mock_custom_domain.id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_custom_domain
        mock_db_session.execute.return_value = mock_result

        with patch("custom_domain.routes.events.redis") as mock_redis_module:
            mock_client = AsyncMock()
            mock_redis_module.from_url.return_value = mock_client
            mock_client.lrange = AsyncMock(return_value=[])
            mock_client.llen = AsyncMock(return_value=0)
            mock_client.close = AsyncMock()

            response = await auth_client.get(
                f"/api/v1/domains/{mock_custom_domain.id}/events/history"
            )
            assert response.status_code == 200
            data = response.json()
            assert "events" in data
            assert "has_more" in data

    @pytest.mark.asyncio
    async def test_get_history_with_events(
        self, auth_client: AsyncClient, mock_db_session, mock_custom_domain
    ):
        """Test getting history with actual events."""
        mock_custom_domain.client_id = "test-client-id"
        mock_custom_domain.id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_custom_domain
        mock_db_session.execute.return_value = mock_result

        now = datetime.now(UTC).isoformat()
        events = [
            json.dumps(
                {
                    "type": "progress",
                    "payload": {
                        "step": "dns_check",
                        "message": "Checking DNS",
                        "timestamp": now,
                    },
                }
            ),
            json.dumps(
                {
                    "type": "completed",
                    "payload": {
                        "message": "Domain provisioned",
                        "timestamp": now,
                    },
                }
            ),
        ]

        with patch("custom_domain.routes.events.redis") as mock_redis_module:
            mock_client = AsyncMock()
            mock_redis_module.from_url.return_value = mock_client
            mock_client.lrange = AsyncMock(return_value=events)
            mock_client.llen = AsyncMock(return_value=2)
            mock_client.close = AsyncMock()

            response = await auth_client.get(
                f"/api/v1/domains/{mock_custom_domain.id}/events/history"
            )
            assert response.status_code == 200
            data = response.json()
            assert len(data["events"]) == 2
            assert data["events"][0]["type"] == "progress"

    @pytest.mark.asyncio
    async def test_get_history_with_limit(
        self, auth_client: AsyncClient, mock_db_session, mock_custom_domain
    ):
        """Test getting history with custom limit."""
        mock_custom_domain.client_id = "test-client-id"
        mock_custom_domain.id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_custom_domain
        mock_db_session.execute.return_value = mock_result

        with patch("custom_domain.routes.events.redis") as mock_redis_module:
            mock_client = AsyncMock()
            mock_redis_module.from_url.return_value = mock_client
            mock_client.lrange = AsyncMock(return_value=[])
            mock_client.llen = AsyncMock(return_value=0)
            mock_client.close = AsyncMock()

            response = await auth_client.get(
                f"/api/v1/domains/{mock_custom_domain.id}/events/history?limit=10"
            )
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_history_forbidden(
        self, auth_client: AsyncClient, mock_db_session, mock_custom_domain
    ):
        """Test getting history for domain owned by another client."""
        mock_custom_domain.client_id = "other-client-id"
        mock_custom_domain.id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_custom_domain
        mock_db_session.execute.return_value = mock_result

        response = await auth_client.get(f"/api/v1/domains/{mock_custom_domain.id}/events/history")
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_history_has_more(
        self, auth_client: AsyncClient, mock_db_session, mock_custom_domain
    ):
        """Test history indicates when there are more events."""
        mock_custom_domain.client_id = "test-client-id"
        mock_custom_domain.id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_custom_domain
        mock_db_session.execute.return_value = mock_result

        now = datetime.now(UTC).isoformat()
        events = [
            json.dumps(
                {
                    "type": "progress",
                    "payload": {"message": "Event", "timestamp": now},
                }
            )
        ]

        with patch("custom_domain.routes.events.redis") as mock_redis_module:
            mock_client = AsyncMock()
            mock_redis_module.from_url.return_value = mock_client
            mock_client.lrange = AsyncMock(return_value=events)
            mock_client.llen = AsyncMock(return_value=100)
            mock_client.close = AsyncMock()

            response = await auth_client.get(
                f"/api/v1/domains/{mock_custom_domain.id}/events/history?limit=1"
            )
            assert response.status_code == 200
            data = response.json()
            assert data["has_more"] is True
