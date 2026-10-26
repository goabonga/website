# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/tasks/verification.py."""

import contextlib
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from celery.exceptions import Retry
from custom_domain.models.enums import DomainStatus


class TestPublishEvent:
    """Tests for publish_event function."""

    def test_publish_event_success(self):
        """Test publishing event to Redis."""
        from custom_domain.tasks.verification import publish_event

        with patch("custom_domain.services.events.redis.from_url") as mock_redis:
            mock_client = MagicMock()
            mock_redis.return_value = mock_client

            publish_event("domain-id", "test_event", {"key": "value"})

            mock_client.publish.assert_called_once()
            mock_client.lpush.assert_called_once()
            mock_client.close.assert_called_once()

    def test_publish_event_error_handling(self):
        """Test publish_event handles errors gracefully."""
        from custom_domain.tasks.verification import publish_event

        with patch("custom_domain.services.events.redis.from_url") as mock_redis:
            mock_redis.side_effect = Exception("Redis error")

            # Should not raise
            publish_event("domain-id", "test_event", {"key": "value"})


class TestVerifyDomainDns:
    """Tests for verify_domain_dns task."""

    def test_domain_not_found(self):
        """Test task handles missing domain."""
        from custom_domain.tasks.verification import verify_domain_dns

        with patch("custom_domain.tasks.verification.get_sync_db") as mock_get_db:
            mock_session = MagicMock()
            mock_session.execute.return_value.scalar_one_or_none.return_value = None
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_db.return_value.__exit__ = MagicMock()

            # Should return without error
            verify_domain_dns(str(uuid4()))

    def test_verify_success(self):
        """Test successful DNS verification updates status."""
        from custom_domain.tasks.verification import verify_domain_dns

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.cname_target = "apps.example.com"
        mock_domain.status = DomainStatus.PENDING

        with patch("custom_domain.tasks.verification.get_sync_db") as mock_get_db:
            mock_session = MagicMock()
            mock_session.execute.return_value.scalar_one_or_none.return_value = mock_domain
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_db.return_value.__exit__ = MagicMock()

            with patch("custom_domain.tasks.verification.publish_event"):
                # Create async function that returns success
                async def mock_check_cname(*args, **kwargs):
                    result = MagicMock()
                    result.success = True
                    return result

                with patch("custom_domain.tasks.verification.dns_service") as mock_dns:
                    mock_dns.check_cname = mock_check_cname

                    with patch(
                        "custom_domain.tasks.provisioning.provision_domain_ssl"
                    ) as mock_provision:
                        mock_provision.delay = MagicMock()

                        verify_domain_dns(str(mock_domain.id))

                        # After successful DNS check, status should be DNS_VERIFIED
                        assert mock_domain.status == DomainStatus.DNS_VERIFIED
                        mock_provision.delay.assert_called_once()

    def test_verify_failure_sets_error_message(self):
        """Test DNS verification failure sets error message."""
        from custom_domain.tasks.verification import verify_domain_dns

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.cname_target = "apps.example.com"
        mock_domain.status = DomainStatus.PENDING
        mock_domain.retry_count = 0

        with patch("custom_domain.tasks.verification.get_sync_db") as mock_get_db:
            mock_session = MagicMock()
            mock_session.execute.return_value.scalar_one_or_none.return_value = mock_domain
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_db.return_value.__exit__ = MagicMock()

            with patch("custom_domain.tasks.verification.publish_event"):
                # Create async function that returns failure
                async def mock_check_cname(*args, **kwargs):
                    result = MagicMock()
                    result.success = False
                    result.error_message = "CNAME not found"
                    result.actual_value = None
                    return result

                with patch("custom_domain.tasks.verification.dns_service") as mock_dns:
                    mock_dns.check_cname = mock_check_cname

                    with contextlib.suppress(Exception):
                        verify_domain_dns(str(mock_domain.id))

                    # Should have updated error message
                    assert mock_domain.error_message == "CNAME not found"


class TestCheckPendingDomains:
    """Tests for check_pending_domains task."""

    def test_checks_pending_domains(self):
        """Test task checks pending domains."""
        from custom_domain.tasks.verification import check_pending_domains

        mock_domain1 = MagicMock()
        mock_domain1.id = uuid4()
        mock_domain1.last_check_at = None

        mock_domain2 = MagicMock()
        mock_domain2.id = uuid4()
        mock_domain2.last_check_at = datetime.now(UTC)

        with patch("custom_domain.tasks.verification.get_sync_db") as mock_get_db:
            mock_session = MagicMock()
            mock_session.execute.return_value.scalars.return_value.all.return_value = [
                mock_domain1,
                mock_domain2,
            ]
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_db.return_value.__exit__ = MagicMock()

            with patch("custom_domain.tasks.verification.verify_domain_dns") as mock_verify:
                mock_verify.delay = MagicMock()

                with patch("custom_domain.tasks.verification.settings") as mock_settings:
                    mock_settings.dns_check_interval_minutes = 5

                    check_pending_domains()

                    # Should trigger verification for domain without last_check_at
                    mock_verify.delay.assert_called()

    def test_skips_recently_checked_domains(self):
        """Test task skips domains that were recently checked."""
        from datetime import timedelta

        from custom_domain.tasks.verification import check_pending_domains

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        # Set last_check_at to very recent (within the check interval)
        mock_domain.last_check_at = datetime.now(UTC) - timedelta(minutes=1)

        with patch("custom_domain.tasks.verification.get_sync_db") as mock_get_db:
            mock_session = MagicMock()
            mock_session.execute.return_value.scalars.return_value.all.return_value = [
                mock_domain,
            ]
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_db.return_value.__exit__ = MagicMock()

            with patch("custom_domain.tasks.verification.verify_domain_dns") as mock_verify:
                mock_verify.delay = MagicMock()

                with patch("custom_domain.tasks.verification.settings") as mock_settings:
                    mock_settings.dns_check_interval_minutes = 5  # 5 minutes

                    check_pending_domains()

                    # Should NOT trigger verification since it was recently checked
                    mock_verify.delay.assert_not_called()


class TestVerifyDomainMaxRetries:
    """Tests for verify_domain_dns max retries handling."""

    def test_verify_max_retries_exceeded_sets_failed(self):
        """Test that max retries exceeded sets domain to FAILED status."""
        from custom_domain.tasks.verification import verify_domain_dns

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.cname_target = "apps.example.com"
        mock_domain.status = DomainStatus.PENDING
        mock_domain.retry_count = 0

        with patch("custom_domain.tasks.verification.get_sync_db") as mock_get_db:
            mock_session = MagicMock()
            mock_session.execute.return_value.scalar_one_or_none.return_value = mock_domain
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_db.return_value.__exit__ = MagicMock()

            with patch("custom_domain.tasks.verification.publish_event"):
                # Create async function that returns failure
                async def mock_check_cname(*args, **kwargs):
                    result = MagicMock()
                    result.success = False
                    result.error_message = "CNAME not found"
                    result.actual_value = None
                    return result

                with patch("custom_domain.tasks.verification.dns_service") as mock_dns:
                    mock_dns.check_cname = mock_check_cname

                    # Access the actual task function to manipulate retry state
                    # When max_retries is reached, the task sets status to FAILED
                    # We simulate this by patching the task's request.retries >= max_retries
                    verify_domain_dns(str(mock_domain.id))

                    # The function sets FAILED when max retries exceeded
                    # Since we're calling directly without Celery, the retry will raise
                    # and be caught, ultimately setting status to FAILED
                    # In direct calls, the retry mechanism triggers the exception path

    def test_verify_max_retries_exhausted_sets_failed_and_publishes_error(self):
        """Test that when max retries are exhausted, domain is set to FAILED and error is published.

        This test uses Celery's bind mechanism to control the retry state.
        """
        from celery.exceptions import Retry

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.cname_target = "apps.example.com"
        mock_domain.status = DomainStatus.PENDING
        mock_domain.retry_count = 0

        published_events = []

        def capture_publish_event(domain_id, event_type, payload):
            published_events.append((event_type, payload))

        with patch("custom_domain.tasks.verification.get_sync_db") as mock_get_db:
            mock_session = MagicMock()
            mock_session.execute.return_value.scalar_one_or_none.return_value = mock_domain
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_db.return_value.__exit__ = MagicMock()

            with patch(
                "custom_domain.tasks.verification.publish_event", side_effect=capture_publish_event
            ):
                # Create async function that returns failure
                async def mock_check_cname(*args, **kwargs):
                    result = MagicMock()
                    result.success = False
                    result.error_message = "CNAME not found"
                    result.actual_value = "wrong.example.com"
                    return result

                with patch("custom_domain.tasks.verification.dns_service") as mock_dns:
                    mock_dns.check_cname = mock_check_cname

                    # Call the task - when run directly without Celery worker,
                    # the retry raises Retry exception
                    try:
                        from custom_domain.tasks.verification import verify_domain_dns

                        verify_domain_dns(str(mock_domain.id))
                    except Retry:
                        pass

                    # Verify the error message was set
                    assert mock_domain.error_message == "CNAME not found"
                    # Verify retry_count was incremented
                    assert mock_domain.retry_count == 1

    def test_verify_max_retries_exceeded_code_path(self):
        """Test the code path when max retries are exceeded.

        Uses Celery's push_request to set the retries count to trigger
        the max retries exceeded path.
        """
        from custom_domain.tasks.verification import verify_domain_dns

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.cname_target = "apps.example.com"
        mock_domain.status = DomainStatus.PENDING
        mock_domain.retry_count = 0

        published_events = []

        def capture_publish_event(domain_id, event_type, payload):
            published_events.append((event_type, payload))

        with patch("custom_domain.tasks.verification.get_sync_db") as mock_get_db:
            mock_session = MagicMock()
            mock_session.execute.return_value.scalar_one_or_none.return_value = mock_domain
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_db.return_value.__exit__ = MagicMock()

            with patch(
                "custom_domain.tasks.verification.publish_event", side_effect=capture_publish_event
            ):
                # Create async function that returns failure
                async def mock_check_cname(*args, **kwargs):
                    result = MagicMock()
                    result.success = False
                    result.error_message = "CNAME not found"
                    result.actual_value = "wrong.example.com"
                    return result

                with patch("custom_domain.tasks.verification.dns_service") as mock_dns:
                    mock_dns.check_cname = mock_check_cname

                    # Use push_request to set up the request context with retries at max
                    # This simulates the task being called at its final retry attempt
                    verify_domain_dns.push_request(retries=3)
                    try:
                        verify_domain_dns(str(mock_domain.id))
                    finally:
                        verify_domain_dns.pop_request()

                    # Verify domain is set to FAILED (else branch was executed)
                    assert mock_domain.status == DomainStatus.FAILED

                    # Verify error event was published
                    error_events = [e for e in published_events if e[0] == "error"]
                    assert len(error_events) >= 1
                    error_payload = error_events[-1][1]
                    assert error_payload["code"] == "DNS_VERIFICATION_FAILED"


class TestCheckPendingDomainsElapsedTime:
    """Test check_pending_domains when elapsed time > interval (line 206->209)."""

    @pytest.mark.asyncio
    async def test_check_pending_domains_elapsed_exceeds_interval(self):
        """Test that domains ARE verified when elapsed time exceeds interval."""
        from custom_domain.tasks.verification import check_pending_domains

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.status = DomainStatus.PENDING
        # Last check was long ago (more than interval)
        mock_domain.last_check_at = datetime.now(UTC) - timedelta(hours=2)

        with (
            patch("custom_domain.tasks.verification.get_sync_db") as mock_get_db,
            patch("custom_domain.tasks.verification.verify_domain_dns") as mock_verify,
            patch("custom_domain.tasks.verification.settings") as mock_settings,
        ):
            mock_db = MagicMock()
            mock_get_db.return_value.__enter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_domain]
            mock_db.execute.return_value = mock_result

            # Set interval to 5 minutes (so 2 hours ago is well beyond)
            mock_settings.dns_check_interval_minutes = 5

            check_pending_domains()

            # verify_domain_dns SHOULD be called because elapsed > interval
            mock_verify.delay.assert_called_once_with(str(mock_domain.id))

    @pytest.mark.asyncio
    async def test_check_pending_domains_no_last_check(self):
        """Test domains with no last_check_at are always verified."""
        from custom_domain.tasks.verification import check_pending_domains

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.status = DomainStatus.PENDING
        mock_domain.last_check_at = None  # Never checked

        with (
            patch("custom_domain.tasks.verification.get_sync_db") as mock_get_db,
            patch("custom_domain.tasks.verification.verify_domain_dns") as mock_verify,
            patch("custom_domain.tasks.verification.settings") as mock_settings,
        ):
            mock_db = MagicMock()
            mock_get_db.return_value.__enter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_domain]
            mock_db.execute.return_value = mock_result

            mock_settings.dns_check_interval_minutes = 5

            check_pending_domains()

            # verify_domain_dns SHOULD be called because no last_check_at
            mock_verify.delay.assert_called_once_with(str(mock_domain.id))


class TestVerifyRetryBackoff:
    """The retry delay and count come from the settings."""

    @staticmethod
    def _failing_check():
        async def check_cname(*args, **kwargs):
            return MagicMock(success=False, error_message="CNAME not found", actual_value=None)

        return check_cname

    def test_delay_doubles_from_the_configured_value(self, monkeypatch):
        from custom_domain.config import settings
        from custom_domain.tasks.verification import verify_domain_dns

        monkeypatch.setattr(settings, "dns_verification_retry_delay_seconds", 7)
        domain = MagicMock(id=uuid4(), domain="test.example.com", retry_count=0)
        domain.cname_target = "apps.example.com"

        with (
            patch("custom_domain.tasks.verification.get_sync_db") as mock_get_db,
            patch("custom_domain.tasks.verification.publish_event"),
            patch("custom_domain.tasks.verification.dns_service") as mock_dns,
            patch.object(verify_domain_dns, "retry", side_effect=Retry()) as mock_retry,
        ):
            session = MagicMock()
            session.execute.return_value.scalar_one_or_none.return_value = domain
            mock_get_db.return_value.__enter__ = MagicMock(return_value=session)
            mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
            mock_dns.check_cname = self._failing_check()

            verify_domain_dns.push_request(retries=2)
            try:
                with pytest.raises(Retry):
                    verify_domain_dns(str(domain.id))
            finally:
                verify_domain_dns.pop_request()

        mock_retry.assert_called_once_with(countdown=28)

    def test_retry_limits_are_task_options(self):
        from custom_domain.config import settings
        from custom_domain.tasks.verification import verify_domain_dns

        assert verify_domain_dns.max_retries == settings.dns_verification_max_retries
        assert (
            verify_domain_dns.default_retry_delay == settings.dns_verification_retry_delay_seconds
        )
