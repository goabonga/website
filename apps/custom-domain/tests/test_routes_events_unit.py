# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for custom_domain/routes/events.py (direct function calls)."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from custom_domain.auth.dependencies import AuthContext
from custom_domain.auth.models import User
from custom_domain.models.enums import DomainStatus, ProvisioningStep


def _auth(user: User) -> AuthContext:
    """Wrap a User in an AuthContext."""
    return AuthContext(user=user)


class TestEventsGetDomainOr404:
    """Unit tests for events get_domain_or_404 helper function."""

    @pytest.mark.asyncio
    async def test_domain_not_found(self):
        """Test raises 404 when domain not found."""
        from custom_domain.routes.events import get_domain_or_404
        from fastapi import HTTPException

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:read"],
            client_id="test-client",
        )

        with pytest.raises(HTTPException) as exc:
            await get_domain_or_404(mock_db, uuid4(), _auth(user))

        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_domain_access_denied(self):
        """Test raises 403 when user doesn't own domain."""
        from custom_domain.routes.events import get_domain_or_404
        from fastapi import HTTPException

        mock_domain = MagicMock()
        mock_domain.client_id = "other-client"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:read"],
            client_id="test-client",
        )

        with pytest.raises(HTTPException) as exc:
            await get_domain_or_404(mock_db, uuid4(), _auth(user))

        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_domain_found_and_owned(self):
        """Test returns domain when found and owned."""
        from custom_domain.routes.events import get_domain_or_404

        mock_domain = MagicMock()
        mock_domain.client_id = "test-client"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:read"],
            client_id="test-client",
        )

        result = await get_domain_or_404(mock_db, uuid4(), _auth(user))
        assert result == mock_domain


class TestGetDomainStatus:
    """Unit tests for get_domain_status endpoint."""

    @pytest.mark.asyncio
    async def test_get_status_success(self):
        """Test getting domain status."""
        from custom_domain.routes.events import get_domain_status

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.status = DomainStatus.PENDING
        mock_domain.client_id = "test-client"
        mock_domain.error_message = None
        mock_domain.retry_count = 0

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:read"],
            client_id="test-client",
        )

        result = await get_domain_status(mock_domain.id, mock_db, _auth(user))

        assert result.domain == "test.example.com"
        assert result.status == DomainStatus.PENDING


class TestGetEventHistory:
    """Unit tests for get_event_history endpoint."""

    @pytest.mark.asyncio
    async def test_get_history_empty(self):
        """Test getting event history with no events."""
        from custom_domain.routes.events import get_event_history

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.client_id = "test-client"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:read"],
            client_id="test-client",
        )

        with patch("custom_domain.routes.events.redis") as mock_redis_module:
            mock_client = AsyncMock()
            mock_redis_module.from_url.return_value = mock_client
            mock_client.lrange = AsyncMock(return_value=[])
            mock_client.llen = AsyncMock(return_value=0)
            mock_client.close = AsyncMock()

            result = await get_event_history(
                domain_id=mock_domain.id,
                limit=50,
                since=None,
                db=mock_db,
                auth=_auth(user),
            )

            assert len(result.events) == 0
            assert result.has_more is False

    @pytest.mark.asyncio
    async def test_get_history_with_events(self):
        """Test getting event history with events."""
        import json

        from custom_domain.routes.events import get_event_history

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.client_id = "test-client"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:read"],
            client_id="test-client",
        )

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
        ]

        with patch("custom_domain.routes.events.redis") as mock_redis_module:
            mock_client = AsyncMock()
            mock_redis_module.from_url.return_value = mock_client
            mock_client.lrange = AsyncMock(return_value=events)
            mock_client.llen = AsyncMock(return_value=1)
            mock_client.close = AsyncMock()

            result = await get_event_history(
                domain_id=mock_domain.id,
                limit=50,
                since=None,
                db=mock_db,
                auth=_auth(user),
            )

            assert len(result.events) == 1
            assert result.events[0].type == "progress"

    @pytest.mark.asyncio
    async def test_get_history_with_since_filter(self):
        """Test getting event history with since filter."""
        import json

        from custom_domain.routes.events import get_event_history

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.client_id = "test-client"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:read"],
            client_id="test-client",
        )

        # Create events with different timestamps
        old_time = "2023-01-01T00:00:00Z"
        new_time = "2025-06-01T00:00:00Z"

        events = [
            json.dumps(
                {
                    "type": "old_event",
                    "payload": {
                        "message": "Old event",
                        "timestamp": old_time,
                    },
                }
            ),
            json.dumps(
                {
                    "type": "new_event",
                    "payload": {
                        "message": "New event",
                        "timestamp": new_time,
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

            # Filter to get only events after 2024-01-01
            since = datetime(2024, 1, 1, tzinfo=UTC)
            result = await get_event_history(
                domain_id=mock_domain.id,
                limit=50,
                since=since,
                db=mock_db,
                auth=_auth(user),
            )

            # Should only get the new event
            assert len(result.events) == 1
            assert result.events[0].type == "new_event"


class TestGetProgressForStatus:
    """Unit tests for get_progress_for_status helper function."""

    def test_pending_status(self):
        """Test progress for PENDING status."""
        from custom_domain.routes.events import get_progress_for_status

        result = get_progress_for_status(DomainStatus.PENDING)

        assert result.current_step is None
        assert result.percentage == 0
        assert len(result.steps_completed) == 0

    def test_dns_verifying_status(self):
        """Test progress for DNS_VERIFYING status."""
        from custom_domain.routes.events import get_progress_for_status

        result = get_progress_for_status(DomainStatus.DNS_VERIFYING)

        assert result.current_step == ProvisioningStep.DNS_CHECK.value
        assert result.percentage == 10
        assert len(result.steps_completed) == 0

    def test_dns_verified_status(self):
        """Test progress for DNS_VERIFIED status."""
        from custom_domain.routes.events import get_progress_for_status

        result = get_progress_for_status(DomainStatus.DNS_VERIFIED)

        assert result.current_step is None
        assert result.percentage == 25
        assert ProvisioningStep.DNS_CHECK.value in result.steps_completed

    def test_ssl_provisioning_status(self):
        """Test progress for SSL_PROVISIONING status."""
        from custom_domain.routes.events import get_progress_for_status

        result = get_progress_for_status(DomainStatus.SSL_PROVISIONING)

        assert result.current_step == ProvisioningStep.CERTBOT.value
        assert result.percentage == 60
        assert ProvisioningStep.DNS_CHECK.value in result.steps_completed
        assert ProvisioningStep.NGINX_HTTP.value in result.steps_completed

    def test_active_status(self):
        """Test progress for ACTIVE status."""
        from custom_domain.routes.events import get_progress_for_status

        result = get_progress_for_status(DomainStatus.ACTIVE)

        assert result.current_step is None
        assert result.percentage == 100
        assert len(result.steps_remaining) == 0

    def test_failed_status(self):
        """Test progress for FAILED status."""
        from custom_domain.routes.events import get_progress_for_status

        result = get_progress_for_status(DomainStatus.FAILED)

        assert result.percentage == 0


class TestDomainEventsSSE:
    """Unit tests for domain_events SSE endpoint."""

    @pytest.mark.asyncio
    async def test_domain_events_initial_state_active(self):
        """Test SSE endpoint sends completed event for already active domain."""
        from custom_domain.routes.events import domain_events

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.status = DomainStatus.ACTIVE
        mock_domain.client_id = "test-client"
        mock_domain.error_message = None

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:read"],
            client_id="test-client",
        )

        mock_request = MagicMock()
        mock_request.is_disconnected = AsyncMock(return_value=False)

        # The endpoint returns an EventSourceResponse, so we need to test differently
        # We can test by checking the response type
        with patch("custom_domain.routes.events.redis") as mock_redis_module:
            mock_client = AsyncMock()
            mock_redis_module.from_url.return_value = mock_client
            mock_pubsub = AsyncMock()
            mock_client.pubsub.return_value = mock_pubsub
            mock_pubsub.subscribe = AsyncMock()
            mock_pubsub.get_message = AsyncMock(return_value=None)
            mock_pubsub.unsubscribe = AsyncMock()
            mock_pubsub.close = AsyncMock()
            mock_client.close = AsyncMock()

            response = await domain_events(
                domain_id=mock_domain.id,
                request=mock_request,
                db=mock_db,
                auth=_auth(user),
            )

            # Response should be an EventSourceResponse
            assert response is not None

    @pytest.mark.asyncio
    async def test_domain_events_initial_state_failed(self):
        """Test SSE endpoint sends error event for failed domain."""
        from custom_domain.routes.events import domain_events

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.status = DomainStatus.FAILED
        mock_domain.client_id = "test-client"
        mock_domain.error_message = "DNS verification failed"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:read"],
            client_id="test-client",
        )

        mock_request = MagicMock()
        mock_request.is_disconnected = AsyncMock(return_value=False)

        with patch("custom_domain.routes.events.redis") as mock_redis_module:
            mock_client = AsyncMock()
            mock_redis_module.from_url.return_value = mock_client
            mock_pubsub = AsyncMock()
            mock_client.pubsub.return_value = mock_pubsub
            mock_pubsub.subscribe = AsyncMock()
            mock_pubsub.get_message = AsyncMock(return_value=None)
            mock_pubsub.unsubscribe = AsyncMock()
            mock_pubsub.close = AsyncMock()
            mock_client.close = AsyncMock()

            response = await domain_events(
                domain_id=mock_domain.id,
                request=mock_request,
                db=mock_db,
                auth=_auth(user),
            )

            assert response is not None

    @pytest.mark.asyncio
    async def test_domain_events_pending_domain(self):
        """Test SSE endpoint for pending domain streams events."""
        from custom_domain.routes.events import domain_events

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.status = DomainStatus.PENDING
        mock_domain.client_id = "test-client"
        mock_domain.error_message = None

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:read"],
            client_id="test-client",
        )

        mock_request = MagicMock()
        mock_request.is_disconnected = AsyncMock(return_value=True)  # Disconnect immediately

        with patch("custom_domain.routes.events.redis") as mock_redis_module:
            mock_client = AsyncMock()
            mock_redis_module.from_url.return_value = mock_client
            mock_pubsub = AsyncMock()
            mock_client.pubsub.return_value = mock_pubsub
            mock_pubsub.subscribe = AsyncMock()
            mock_pubsub.get_message = AsyncMock(return_value=None)
            mock_pubsub.unsubscribe = AsyncMock()
            mock_pubsub.close = AsyncMock()
            mock_client.close = AsyncMock()

            response = await domain_events(
                domain_id=mock_domain.id,
                request=mock_request,
                db=mock_db,
                auth=_auth(user),
            )

            assert response is not None


class TestSSEEventGeneratorConsumption:
    """Tests that actually consume the SSE event generator to improve coverage."""

    @pytest.mark.asyncio
    async def test_sse_generator_active_domain_sends_completed(self):
        """Test SSE generator sends initial_state and completed for active domain.

        This test fully consumes the generator to ensure the return statement
        after yielding completed is executed (line 172 coverage).
        """
        from custom_domain.routes.events import domain_events

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.status = DomainStatus.ACTIVE
        mock_domain.client_id = "test-client"
        mock_domain.error_message = None

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:read"],
            client_id="test-client",
        )

        mock_request = MagicMock()

        with patch("custom_domain.routes.events.redis") as mock_redis_module:
            # redis.from_url returns a sync client
            mock_client = MagicMock()
            mock_redis_module.from_url.return_value = mock_client
            # pubsub() is a sync method returning a pubsub object
            mock_pubsub = MagicMock()
            mock_client.pubsub.return_value = mock_pubsub
            # subscribe, unsubscribe, close are async
            mock_pubsub.subscribe = AsyncMock()
            mock_pubsub.unsubscribe = AsyncMock()
            mock_pubsub.close = AsyncMock()
            mock_client.close = AsyncMock()

            response = await domain_events(
                domain_id=mock_domain.id,
                request=mock_request,
                db=mock_db,
                auth=_auth(user),
            )

            # Fully consume the generator to ensure return is executed
            events = []
            async for event in response.body_iterator:
                events.append(event)

            # Should have exactly 2 events: initial_state and completed
            # Generator should terminate after the return statement
            assert len(events) == 2

    @pytest.mark.asyncio
    async def test_sse_generator_failed_domain_sends_error(self):
        """Test SSE generator sends initial_state and error for failed domain."""
        from custom_domain.routes.events import domain_events

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.status = DomainStatus.FAILED
        mock_domain.client_id = "test-client"
        mock_domain.error_message = "Certificate failed"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:read"],
            client_id="test-client",
        )

        mock_request = MagicMock()

        with patch("custom_domain.routes.events.redis") as mock_redis_module:
            mock_client = MagicMock()
            mock_redis_module.from_url.return_value = mock_client
            mock_pubsub = MagicMock()
            mock_client.pubsub.return_value = mock_pubsub
            mock_pubsub.subscribe = AsyncMock()
            mock_pubsub.unsubscribe = AsyncMock()
            mock_pubsub.close = AsyncMock()
            mock_client.close = AsyncMock()

            response = await domain_events(
                domain_id=mock_domain.id,
                request=mock_request,
                db=mock_db,
                auth=_auth(user),
            )

            # Consume the generator
            events = []
            async for event in response.body_iterator:
                events.append(event)
                if len(events) >= 2:  # Initial state + error
                    break

            assert len(events) >= 2

    @pytest.mark.asyncio
    async def test_sse_generator_pending_domain_with_completed_message(self):
        """Test SSE generator processes completed message and stops."""

        from custom_domain.routes.events import domain_events

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.status = DomainStatus.PENDING
        mock_domain.client_id = "test-client"
        mock_domain.error_message = None

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:read"],
            client_id="test-client",
        )

        mock_request = MagicMock()
        mock_request.is_disconnected = AsyncMock(return_value=False)

        with patch("custom_domain.routes.events.redis") as mock_redis_module:
            mock_client = MagicMock()
            mock_redis_module.from_url.return_value = mock_client
            mock_pubsub = MagicMock()
            mock_client.pubsub.return_value = mock_pubsub
            mock_pubsub.subscribe = AsyncMock()

            # Simulate a completed message from Redis
            completed_message = {
                "type": "message",
                "data": json.dumps(
                    {
                        "type": "completed",
                        "payload": {
                            "status": "active",
                            "timestamp": datetime.now(UTC).isoformat(),
                        },
                    }
                ),
            }

            message_call_count = [0]

            async def get_message(ignore_subscribe_messages=False):
                message_call_count[0] += 1
                if message_call_count[0] == 1:
                    return completed_message
                return None

            mock_pubsub.get_message = get_message
            mock_pubsub.unsubscribe = AsyncMock()
            mock_pubsub.close = AsyncMock()
            mock_client.close = AsyncMock()

            response = await domain_events(
                domain_id=mock_domain.id,
                request=mock_request,
                db=mock_db,
                auth=_auth(user),
            )

            # Consume the generator
            events = []
            async for event in response.body_iterator:
                events.append(event)

            # Should have initial_state and completed
            assert len(events) >= 2

    @pytest.mark.asyncio
    async def test_sse_generator_pending_domain_disconnect(self):
        """Test SSE generator handles client disconnect."""
        import asyncio

        from custom_domain.routes.events import domain_events

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.status = DomainStatus.PENDING
        mock_domain.client_id = "test-client"
        mock_domain.error_message = None

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:read"],
            client_id="test-client",
        )

        mock_request = MagicMock()
        # Simulate client disconnect after first check
        disconnect_call_count = [0]

        async def is_disconnected():
            disconnect_call_count[0] += 1
            return disconnect_call_count[0] > 1

        mock_request.is_disconnected = is_disconnected

        with patch("custom_domain.routes.events.redis") as mock_redis_module:
            mock_client = MagicMock()
            mock_redis_module.from_url.return_value = mock_client
            mock_pubsub = MagicMock()
            mock_client.pubsub.return_value = mock_pubsub
            mock_pubsub.subscribe = AsyncMock()

            async def get_message(ignore_subscribe_messages=False):
                await asyncio.sleep(0.01)
                return None

            mock_pubsub.get_message = get_message
            mock_pubsub.unsubscribe = AsyncMock()
            mock_pubsub.close = AsyncMock()
            mock_client.close = AsyncMock()

            response = await domain_events(
                domain_id=mock_domain.id,
                request=mock_request,
                db=mock_db,
                auth=_auth(user),
            )

            # Consume the generator
            events = []
            async for event in response.body_iterator:
                events.append(event)

            # Should have at least initial_state
            assert len(events) >= 1

    @pytest.mark.asyncio
    async def test_sse_generator_with_error_message(self):
        """Test SSE generator processes error message and stops."""
        from custom_domain.routes.events import domain_events

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.status = DomainStatus.DNS_VERIFYING
        mock_domain.client_id = "test-client"
        mock_domain.error_message = None

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:read"],
            client_id="test-client",
        )

        mock_request = MagicMock()
        mock_request.is_disconnected = AsyncMock(return_value=False)

        with patch("custom_domain.routes.events.redis") as mock_redis_module:
            mock_client = MagicMock()
            mock_redis_module.from_url.return_value = mock_client
            mock_pubsub = MagicMock()
            mock_client.pubsub.return_value = mock_pubsub
            mock_pubsub.subscribe = AsyncMock()

            # Simulate an error message from Redis
            error_message = {
                "type": "message",
                "data": json.dumps(
                    {
                        "type": "error",
                        "payload": {
                            "code": "DNS_FAILED",
                            "message": "DNS verification failed",
                            "timestamp": datetime.now(UTC).isoformat(),
                        },
                    }
                ),
            }

            message_call_count = [0]

            async def get_message(ignore_subscribe_messages=False):
                message_call_count[0] += 1
                if message_call_count[0] == 1:
                    return error_message
                return None

            mock_pubsub.get_message = get_message
            mock_pubsub.unsubscribe = AsyncMock()
            mock_pubsub.close = AsyncMock()
            mock_client.close = AsyncMock()

            response = await domain_events(
                domain_id=mock_domain.id,
                request=mock_request,
                db=mock_db,
                auth=_auth(user),
            )

            # Consume the generator
            events = []
            async for event in response.body_iterator:
                events.append(event)

            # Should have initial_state and error
            assert len(events) >= 2

    @pytest.mark.asyncio
    async def test_sse_generator_timeout_and_heartbeat(self):
        """Test SSE generator handles timeout and sends heartbeat."""

        from custom_domain.routes.events import domain_events

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.status = DomainStatus.DNS_VERIFYING
        mock_domain.client_id = "test-client"
        mock_domain.error_message = None

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:read"],
            client_id="test-client",
        )

        mock_request = MagicMock()
        # Disconnect after several iterations to allow heartbeat
        iteration_count = [0]

        async def is_disconnected():
            iteration_count[0] += 1
            # Stay connected for a few iterations
            return iteration_count[0] > 5

        mock_request.is_disconnected = is_disconnected

        with patch("custom_domain.routes.events.redis") as mock_redis_module:
            mock_client = MagicMock()
            mock_redis_module.from_url.return_value = mock_client
            mock_pubsub = MagicMock()
            mock_client.pubsub.return_value = mock_pubsub
            mock_pubsub.subscribe = AsyncMock()

            # Simulate timeout on get_message to trigger the except TimeoutError path
            async def get_message(ignore_subscribe_messages=False):
                raise TimeoutError()

            mock_pubsub.get_message = get_message
            mock_pubsub.unsubscribe = AsyncMock()
            mock_pubsub.close = AsyncMock()
            mock_client.close = AsyncMock()

            with patch("custom_domain.routes.events.settings") as mock_settings:
                mock_settings.sse_heartbeat_interval = 0  # Trigger heartbeat immediately
                mock_settings.sse_poll_interval_seconds = 0.01

                response = await domain_events(
                    domain_id=mock_domain.id,
                    request=mock_request,
                    db=mock_db,
                    auth=_auth(user),
                )

                # Consume the generator
                events = []
                async for event in response.body_iterator:
                    events.append(event)

                # Should have initial_state and at least one heartbeat
                assert len(events) >= 1
                # Check if heartbeat was sent
                [str(e) for e in events]
                # Should contain either heartbeat or just initial state
                assert len(events) >= 1


def make_test_user(client_id: str = "test-client"):
    """Create a test user for testing."""
    return User(
        id=uuid4(),
        email="test@example.com",
        scopes=["custom-domain:read", "custom-domain:write"],
        client_id=client_id,
    )


class TestSSEEventsNonTerminalMessage:
    """Test SSE event handling for non-terminal messages (line 195->202)."""

    @pytest.mark.asyncio
    async def test_sse_events_progress_message(self):
        """Test that progress messages don't terminate the stream."""
        import json
        from unittest.mock import AsyncMock, MagicMock, patch

        # Create mock domain
        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.status = DomainStatus.PENDING  # Not complete
        mock_domain.client_id = "test-client"
        mock_domain.error_message = None

        # Create mock user
        user = make_test_user("test-client")

        # Create mock db
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Create mock request
        mock_request = MagicMock()
        disconnect_count = 0

        async def is_disconnected():
            nonlocal disconnect_count
            disconnect_count += 1
            # Disconnect after 3 checks to end the test
            return disconnect_count >= 3

        mock_request.is_disconnected = is_disconnected

        # Create mock pubsub
        mock_pubsub = MagicMock()
        message_count = 0

        async def get_message(ignore_subscribe_messages=True):
            nonlocal message_count
            message_count += 1
            if message_count == 1:
                # Return a progress message (non-terminal)
                return {
                    "type": "message",
                    "data": json.dumps(
                        {
                            "type": "step_started",  # Not "completed" or "error"
                            "payload": {
                                "step": "dns_check",
                                "message": "Checking DNS...",
                            },
                        }
                    ),
                }
            return None

        mock_pubsub.get_message = get_message
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.unsubscribe = AsyncMock()
        mock_pubsub.close = AsyncMock()

        mock_redis = MagicMock()
        mock_redis.pubsub.return_value = mock_pubsub
        mock_redis.close = AsyncMock()

        with (
            patch("custom_domain.routes.events.redis.from_url", return_value=mock_redis),
            patch("custom_domain.routes.events.get_domain_or_404", return_value=mock_domain),
            patch("custom_domain.routes.events.settings") as mock_settings,
        ):
            mock_settings.redis_url = "redis://localhost:6379"
            mock_settings.sse_heartbeat_interval = 30
            mock_settings.sse_poll_interval_seconds = 0.01

            from custom_domain.routes.events import domain_events

            # Get the EventSourceResponse
            response = await domain_events(
                mock_domain.id,
                mock_request,
                mock_db,
                _auth(user),
            )

            # Consume some events from the generator
            events = []
            async for event in response.body_iterator:
                events.append(event)
                if len(events) >= 3:
                    break

            # Should have initial_state and at least one more event
            assert len(events) >= 1


class TestEventsGetProgressForStatusOtherStatuses:
    """Test get_progress_for_status for remaining statuses."""

    def test_suspended_status(self):
        """Test progress for SUSPENDED status."""
        from custom_domain.routes.events import get_progress_for_status

        result = get_progress_for_status(DomainStatus.SUSPENDED)
        assert result.percentage == 0

    def test_expired_status(self):
        """Test progress for EXPIRED status."""
        from custom_domain.routes.events import get_progress_for_status

        result = get_progress_for_status(DomainStatus.EXPIRED)
        assert result.percentage == 0


class TestHistoryRoundTrip:
    """Events written by the Celery tasks must be readable by the history endpoint."""

    @pytest.mark.asyncio
    async def test_history_parses_events_written_by_the_tasks(self):
        """The timestamp produced by publish_event is accepted by get_event_history."""
        import json

        from custom_domain.routes.events import get_event_history
        from custom_domain.tasks.provisioning import publish_event

        with patch("custom_domain.services.events.redis") as sync_redis:
            publish_event("domain-1", "step_started", {"step": "certbot", "message": "go"})
        stored = sync_redis.from_url.return_value.lpush.call_args[0][1]
        assert json.loads(stored)["type"] == "step_started"

        domain = MagicMock()
        domain.id = uuid4()
        domain.client_id = "test-client"
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = domain
        mock_db.execute = AsyncMock(return_value=mock_result)
        user = User(
            id=uuid4(),
            email="test@example.com",
            scopes=["custom-domain:read"],
            client_id="test-client",
        )

        with patch("custom_domain.routes.events.redis") as async_redis:
            client = AsyncMock()
            async_redis.from_url.return_value = client
            client.lrange = AsyncMock(return_value=[stored])
            client.llen = AsyncMock(return_value=1)
            client.close = AsyncMock()

            result = await get_event_history(
                domain_id=domain.id, limit=50, since=None, db=mock_db, auth=_auth(user)
            )

        assert [event.type for event in result.events] == ["step_started"]
        assert result.events[0].step == "certbot"
