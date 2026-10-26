# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/tasks/provisioning.py."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from celery.exceptions import Retry
from custom_domain.models.enums import DomainStatus


class TestRunAsync:
    """Tests for run_async helper function."""

    def test_run_async_success(self):
        """Test running async function in sync context."""
        from custom_domain.tasks.provisioning import run_async

        async def async_func():
            return "result"

        result = run_async(async_func())
        assert result == "result"


class TestPublishEvent:
    """Tests for publish_event function."""

    def test_publish_event_success(self):
        """Test publishing event to Redis."""
        from custom_domain.tasks.provisioning import publish_event

        with patch("custom_domain.services.events.redis.from_url") as mock_redis:
            mock_client = MagicMock()
            mock_redis.return_value = mock_client

            publish_event("domain-id", "test_event", {"key": "value"})

            mock_client.publish.assert_called_once()
            mock_client.close.assert_called_once()

    def test_publish_event_error_handling(self):
        """Test publish_event handles errors gracefully."""
        from custom_domain.tasks.provisioning import publish_event

        with patch("custom_domain.services.events.redis.from_url") as mock_redis:
            mock_redis.side_effect = Exception("Redis error")

            # Should not raise
            publish_event("domain-id", "test_event", {"key": "value"})


class TestProvisionDomainSsl:
    """Tests for provision_domain_ssl task."""

    def test_domain_not_found(self):
        """Test task handles missing domain."""
        from custom_domain.tasks.provisioning import provision_domain_ssl

        with patch("custom_domain.tasks.provisioning.get_sync_db") as mock_get_db:
            mock_session = MagicMock()
            mock_session.execute.return_value.scalar_one_or_none.return_value = None
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_db.return_value.__exit__ = MagicMock()

            # Should return without error
            provision_domain_ssl(str(uuid4()))

    def test_provision_success(self):
        """Test successful SSL provisioning."""
        from custom_domain.tasks.provisioning import provision_domain_ssl

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.nginx_template_id = None
        mock_domain.status = DomainStatus.DNS_VERIFIED

        mock_template = MagicMock()
        mock_template.http_template = "http config"
        mock_template.https_template = "https config"

        with patch("custom_domain.tasks.provisioning.get_sync_db") as mock_get_db:
            mock_session = MagicMock()
            # First call returns domain, subsequent calls return template
            mock_session.execute.return_value.scalar_one_or_none.side_effect = [
                mock_domain,
                None,  # No specific template
                mock_template,  # Default template
            ]
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_db.return_value.__exit__ = MagicMock()

            with (
                patch("custom_domain.tasks.provisioning.publish_event"),
                patch("custom_domain.tasks.provisioning.nginx_manager") as mock_nginx,
            ):
                mock_nginx.generate_http_config = MagicMock(return_value="http config")
                mock_nginx.generate_https_config = MagicMock(return_value="https config")
                mock_nginx.write_config = MagicMock()
                mock_nginx.reload = MagicMock()

                with patch("custom_domain.tasks.provisioning.certbot_service") as mock_certbot:
                    mock_cert_result = MagicMock()
                    mock_cert_result.success = True
                    mock_cert_result.expires_at = datetime.now(UTC)
                    mock_certbot.provision_certificate = MagicMock(return_value=mock_cert_result)

                    with patch("custom_domain.tasks.provisioning.run_async") as mock_run:
                        mock_run.side_effect = lambda x: x

                        provision_domain_ssl(str(mock_domain.id))

    def test_provision_certbot_failure(self):
        """Test SSL provisioning handles certbot failure."""
        from custom_domain.tasks.provisioning import provision_domain_ssl

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.nginx_template_id = None
        mock_domain.status = DomainStatus.DNS_VERIFIED

        mock_template = MagicMock()

        with patch("custom_domain.tasks.provisioning.get_sync_db") as mock_get_db:
            mock_session = MagicMock()
            mock_session.execute.return_value.scalar_one_or_none.side_effect = [
                mock_domain,
                None,
                mock_template,
            ]
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_db.return_value.__exit__ = MagicMock()

            with (
                patch("custom_domain.tasks.provisioning.publish_event"),
                patch("custom_domain.tasks.provisioning.nginx_manager") as mock_nginx,
            ):
                mock_nginx.generate_http_config = MagicMock(return_value="http config")
                mock_nginx.write_config = MagicMock()
                mock_nginx.reload = MagicMock()

                with patch("custom_domain.tasks.provisioning.certbot_service") as mock_certbot:
                    mock_cert_result = MagicMock()
                    mock_cert_result.success = False
                    mock_cert_result.error_message = "Challenge failed"
                    mock_certbot.provision_certificate = MagicMock(return_value=mock_cert_result)

                    with patch("custom_domain.tasks.provisioning.run_async") as mock_run:
                        mock_run.side_effect = lambda x: x

                        provision_domain_ssl(str(mock_domain.id))

                        assert mock_domain.status == DomainStatus.FAILED


def _session_returning(*values):
    """A sync database context manager whose successive lookups return ``values``."""
    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.side_effect = list(values)
    manager = MagicMock()
    manager.__enter__ = MagicMock(return_value=session)
    manager.__exit__ = MagicMock(return_value=False)
    return session, manager


class TestDeprovisionDomain:
    """Tests for deprovision_domain task."""

    @staticmethod
    def _domain(status=DomainStatus.DEPROVISIONING, deleted_at=None):
        domain = MagicMock()
        domain.id = uuid4()
        domain.domain = "test.example.com"
        domain.status = status
        domain.deleted_at = deleted_at
        domain.error_message = None
        return domain

    def _run(
        self, domain, *, nginx_error=None, revoke_success=True, retries=0, revoke=True, **kwargs
    ):
        from custom_domain.config import settings
        from custom_domain.tasks.provisioning import deprovision_domain

        _, manager = _session_returning(domain)
        events = []
        with (
            patch("custom_domain.tasks.provisioning.get_sync_db", return_value=manager),
            patch("custom_domain.tasks.provisioning.nginx_manager") as nginx,
            patch("custom_domain.tasks.provisioning.certbot_service") as certbot,
            patch("custom_domain.tasks.provisioning.run_async", side_effect=lambda x: x),
            patch(
                "custom_domain.tasks.provisioning.publish_event",
                side_effect=lambda _id, kind, payload: events.append((kind, payload)),
            ),
            patch.object(settings, "certbot_revoke_on_deprovision", revoke),
        ):
            nginx.remove_config = MagicMock(side_effect=nginx_error)
            nginx.reload = MagicMock()
            certbot.revoke_certificate = MagicMock(
                return_value=MagicMock(success=revoke_success, error_message="revocation refused")
            )
            deprovision_domain.push_request(retries=retries)
            try:
                deprovision_domain(str(domain.id), **kwargs)
            finally:
                deprovision_domain.pop_request()
        return nginx, certbot, events

    def test_domain_not_found(self):
        """Test task handles missing domain."""
        from custom_domain.tasks.provisioning import deprovision_domain

        _, manager = _session_returning(None)
        with patch("custom_domain.tasks.provisioning.get_sync_db", return_value=manager):
            deprovision_domain(str(uuid4()))

    def test_deprovision_success(self):
        """The nginx file is removed, nginx reloaded, the certificate revoked, the domain deleted."""
        domain = self._domain()
        nginx, certbot, events = self._run(domain)

        nginx.remove_config.assert_called_once_with("test.example.com")
        nginx.reload.assert_called_once()
        certbot.revoke_certificate.assert_called_once_with("test.example.com")
        assert domain.deleted_at is not None
        assert domain.status == DomainStatus.DEPROVISIONING
        assert events[-1] == ("completed", {"status": "deprovisioning", "deleted": True})

    def test_marks_the_domain_when_the_api_did_not(self):
        """A domain removed by a maintenance task is moved to deprovisioning first."""
        domain = self._domain(status=DomainStatus.ACTIVE)
        _, _, events = self._run(domain)

        assert domain.status == DomainStatus.DEPROVISIONING
        assert events[0] == (
            "status_change",
            {"status": "deprovisioning", "previous_status": "active"},
        )

    def test_keeps_an_existing_deletion_date(self):
        """A domain soft-deleted by maintenance keeps its original deletion time."""
        deleted_at = datetime(2024, 1, 1, tzinfo=UTC)
        domain = self._domain(deleted_at=deleted_at)
        self._run(domain)
        assert domain.deleted_at == deleted_at

    def test_certificate_is_kept_when_revocation_is_disabled(self):
        domain = self._domain()
        _, certbot, _ = self._run(domain, revoke=False)
        certbot.revoke_certificate.assert_not_called()
        assert domain.deleted_at is not None

    def test_a_caller_can_ask_to_keep_the_certificate(self):
        """The maintenance tasks retire domains without revoking their certificates."""
        domain = self._domain()
        _, certbot, _ = self._run(domain, revoke_certificate=False)
        certbot.revoke_certificate.assert_not_called()
        assert domain.deleted_at is not None

    def test_failed_revocation_does_not_block_the_deletion(self):
        domain = self._domain()
        _, _, events = self._run(domain, revoke_success=False)
        assert domain.deleted_at is not None
        assert events[-1][0] == "completed"

    def test_nginx_failure_is_retried(self):
        """Before the retries are exhausted the failure is re-raised for Celery to retry."""
        domain = self._domain()
        with pytest.raises(Exception, match="Remove failed"):
            self._run(domain, nginx_error=Exception("Remove failed"), retries=0)
        assert domain.deleted_at is None
        assert domain.status == DomainStatus.DEPROVISIONING

    def test_nginx_failure_after_the_last_retry_marks_the_domain_failed(self):
        from custom_domain.tasks.provisioning import deprovision_domain

        domain = self._domain()
        _, certbot, events = self._run(
            domain,
            nginx_error=Exception("Remove failed"),
            retries=deprovision_domain.max_retries,
        )

        assert domain.status == DomainStatus.FAILED
        assert "Remove failed" in domain.error_message
        assert domain.deleted_at is None
        certbot.revoke_certificate.assert_not_called()
        assert events[-1][0] == "error"
        assert events[-1][1]["code"] == "DEPROVISIONING_FAILED"


class TestResolveTemplate:
    """Template resolution: domain, client default, global default."""

    @staticmethod
    def _domain(template_id=None):
        domain = MagicMock()
        domain.nginx_template_id = template_id
        domain.client_id = "tenant-a"
        return domain

    def test_domain_template_wins(self):
        from custom_domain.tasks.provisioning import resolve_template

        own = MagicMock()
        session, _ = _session_returning(own)
        assert resolve_template(session, self._domain(template_id=7)) is own
        assert session.execute.call_count == 1

    def test_client_default_is_used_before_the_global_default(self):
        from custom_domain.tasks.provisioning import resolve_template

        branded = MagicMock()
        # no domain template, the client points at template 3, which is active
        session, _ = _session_returning(3, branded)
        assert resolve_template(session, self._domain()) is branded
        assert session.execute.call_count == 2

    def test_inactive_client_default_falls_back_to_global(self):
        from custom_domain.tasks.provisioning import resolve_template

        default = MagicMock()
        session, _ = _session_returning(3, None, default)
        assert resolve_template(session, self._domain()) is default

    def test_unknown_domain_template_falls_back_to_client_default(self):
        from custom_domain.tasks.provisioning import resolve_template

        branded = MagicMock()
        session, _ = _session_returning(None, 3, branded)
        assert resolve_template(session, self._domain(template_id=99)) is branded

    def test_no_template_at_all_uses_the_packaged_files(self):
        from custom_domain.tasks.provisioning import resolve_template

        session, _ = _session_returning(None, None)
        assert resolve_template(session, self._domain()) is None


class TestProvisionWithTemplate:
    """Tests for provisioning with specific nginx templates."""

    def test_provision_with_specific_template(self):
        """Test SSL provisioning with domain-specific template."""
        from custom_domain.tasks.provisioning import provision_domain_ssl

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.nginx_template_id = 42  # Specific template ID
        mock_domain.status = DomainStatus.DNS_VERIFIED

        mock_specific_template = MagicMock()
        mock_specific_template.http_template = "specific http config"
        mock_specific_template.https_template = "specific https config"

        with patch("custom_domain.tasks.provisioning.get_sync_db") as mock_get_db:
            mock_session = MagicMock()
            # First call returns domain, second call returns specific template
            mock_session.execute.return_value.scalar_one_or_none.side_effect = [
                mock_domain,
                mock_specific_template,  # Specific template found
            ]
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_db.return_value.__exit__ = MagicMock()

            with (
                patch("custom_domain.tasks.provisioning.publish_event"),
                patch("custom_domain.tasks.provisioning.nginx_manager") as mock_nginx,
            ):
                mock_nginx.generate_http_config = MagicMock(return_value="http config")
                mock_nginx.generate_https_config = MagicMock(return_value="https config")
                mock_nginx.write_config = MagicMock()
                mock_nginx.reload = MagicMock()

                with patch("custom_domain.tasks.provisioning.certbot_service") as mock_certbot:
                    mock_cert_result = MagicMock()
                    mock_cert_result.success = True
                    mock_cert_result.expires_at = datetime.now(UTC)
                    mock_certbot.provision_certificate = MagicMock(return_value=mock_cert_result)

                    with patch("custom_domain.tasks.provisioning.run_async") as mock_run:
                        mock_run.side_effect = lambda x: x

                        provision_domain_ssl(str(mock_domain.id))

                        # Verify nginx was called with the specific template
                        assert mock_nginx.generate_http_config.called

    def test_provision_no_template_fallback_to_default(self):
        """Test SSL provisioning falls back to default template when specific not found."""
        from custom_domain.tasks.provisioning import provision_domain_ssl

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.nginx_template_id = 999  # Template ID that won't be found
        mock_domain.status = DomainStatus.DNS_VERIFIED

        mock_default_template = MagicMock()
        mock_default_template.http_template = "default http config"
        mock_default_template.https_template = "default https config"

        with patch("custom_domain.tasks.provisioning.get_sync_db") as mock_get_db:
            mock_session = MagicMock()
            # domain, specific template (not found), client default (none), global default
            mock_session.execute.return_value.scalar_one_or_none.side_effect = [
                mock_domain,
                None,  # Specific template not found
                None,  # The client has no default template
                mock_default_template,  # Fallback to default
            ]
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_db.return_value.__exit__ = MagicMock()

            with (
                patch("custom_domain.tasks.provisioning.publish_event"),
                patch("custom_domain.tasks.provisioning.nginx_manager") as mock_nginx,
            ):
                mock_nginx.generate_http_config = MagicMock(return_value="http config")
                mock_nginx.generate_https_config = MagicMock(return_value="https config")
                mock_nginx.write_config = MagicMock()
                mock_nginx.reload = MagicMock()

                with patch("custom_domain.tasks.provisioning.certbot_service") as mock_certbot:
                    mock_cert_result = MagicMock()
                    mock_cert_result.success = True
                    mock_cert_result.expires_at = datetime.now(UTC)
                    mock_certbot.provision_certificate = MagicMock(return_value=mock_cert_result)

                    with patch("custom_domain.tasks.provisioning.run_async") as mock_run:
                        mock_run.side_effect = lambda x: x

                        provision_domain_ssl(str(mock_domain.id))

                        # Should complete successfully with default template
                        assert mock_domain.status == DomainStatus.ACTIVE
                        template_used = mock_nginx.generate_http_config.call_args[0][1]
                        assert template_used is mock_default_template


class TestProvisionRateLimitRetry:
    """Tests for rate limit handling and retries."""

    def test_provision_rate_limit_sets_error(self):
        """Test rate limit error sets error message.

        When a rate limit error occurs and retry is attempted, the Celery Retry
        exception propagates to the worker and the domain is not marked as failed.
        """
        from custom_domain.tasks.provisioning import provision_domain_ssl

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.nginx_template_id = None
        mock_domain.status = DomainStatus.DNS_VERIFIED

        mock_template = MagicMock()

        with patch("custom_domain.tasks.provisioning.get_sync_db") as mock_get_db:
            mock_session = MagicMock()
            mock_session.execute.return_value.scalar_one_or_none.side_effect = [
                mock_domain,
                None,
                mock_template,
            ]
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

            with (
                patch("custom_domain.tasks.provisioning.publish_event"),
                patch("custom_domain.tasks.provisioning.nginx_manager") as mock_nginx,
            ):
                mock_nginx.generate_http_config = MagicMock(return_value="http config")
                mock_nginx.write_config = MagicMock()
                mock_nginx.reload = MagicMock()

                with patch("custom_domain.tasks.provisioning.certbot_service") as mock_certbot:
                    mock_cert_result = MagicMock()
                    mock_cert_result.success = False
                    mock_cert_result.error_message = "Rate limit exceeded"
                    mock_certbot.provision_certificate = MagicMock(return_value=mock_cert_result)

                    with patch("custom_domain.tasks.provisioning.run_async") as mock_run:
                        mock_run.side_effect = lambda x: x

                        # When called directly, Celery's retry raises Retry
                        with pytest.raises(Retry):
                            provision_domain_ssl(str(mock_domain.id))

                        assert mock_domain.status != DomainStatus.FAILED


class TestProvisionExceptionHandling:
    """Tests for exception handling in provisioning."""

    def test_provision_general_exception(self):
        """Test provisioning handles general exceptions."""
        from custom_domain.tasks.provisioning import provision_domain_ssl

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.nginx_template_id = None
        mock_domain.status = DomainStatus.DNS_VERIFIED

        mock_template = MagicMock()

        with patch("custom_domain.tasks.provisioning.get_sync_db") as mock_get_db:
            mock_session = MagicMock()
            mock_session.execute.return_value.scalar_one_or_none.side_effect = [
                mock_domain,
                None,
                mock_template,
            ]
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_db.return_value.__exit__ = MagicMock()

            with (
                patch("custom_domain.tasks.provisioning.publish_event"),
                patch("custom_domain.tasks.provisioning.nginx_manager") as mock_nginx,
            ):
                # Simulate exception during HTTP config generation
                mock_nginx.generate_http_config = MagicMock(
                    side_effect=Exception("Nginx generation failed")
                )

                with patch("custom_domain.tasks.provisioning.run_async") as mock_run:
                    mock_run.side_effect = Exception("Nginx generation failed")

                    provision_domain_ssl(str(mock_domain.id))

                    # Should have set status to FAILED and error message
                    assert mock_domain.status == DomainStatus.FAILED
                    assert "Nginx generation failed" in mock_domain.error_message


class TestProvisionMaxRetriesExceeded:
    """Tests for retry and rate limit handling in provisioning."""

    def test_provision_rate_limit_triggers_retry(self):
        """Test that rate limit error triggers retry mechanism.

        When run directly (not via Celery worker), the retry raises a Retry exception
        that is not swallowed: the domain keeps its error message but is not failed.
        """
        from custom_domain.tasks.provisioning import provision_domain_ssl

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.nginx_template_id = None
        mock_domain.status = DomainStatus.DNS_VERIFIED

        mock_template = MagicMock()

        with patch("custom_domain.tasks.provisioning.get_sync_db") as mock_get_db:
            mock_session = MagicMock()
            mock_session.execute.return_value.scalar_one_or_none.side_effect = [
                mock_domain,
                None,
                mock_template,
            ]
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

            with (
                patch("custom_domain.tasks.provisioning.publish_event"),
                patch("custom_domain.tasks.provisioning.nginx_manager") as mock_nginx,
            ):
                mock_nginx.generate_http_config = MagicMock(return_value="http config")
                mock_nginx.write_config = MagicMock()
                mock_nginx.reload = MagicMock()

                with patch("custom_domain.tasks.provisioning.certbot_service") as mock_certbot:
                    mock_cert_result = MagicMock()
                    mock_cert_result.success = False
                    # Error message containing "rate limit" triggers retry
                    mock_cert_result.error_message = "Rate limit exceeded for domain"
                    mock_certbot.provision_certificate = MagicMock(return_value=mock_cert_result)

                    with patch("custom_domain.tasks.provisioning.run_async") as mock_run:
                        mock_run.side_effect = lambda x: x

                        # When called directly, the retry raises Retry exception
                        with pytest.raises(Retry):
                            provision_domain_ssl(str(mock_domain.id))

                        # The retry was requested: the domain is not failed
                        assert mock_domain.status != DomainStatus.FAILED

    def test_provision_max_retries_exceeded_path(self):
        """Test the code path when max retries are reached for rate limit.

        Uses Celery's push_request to set retries count at max to trigger
        the non-retry path (lines 159->163 in provisioning.py).
        """
        from custom_domain.tasks.provisioning import provision_domain_ssl

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.nginx_template_id = None
        mock_domain.status = DomainStatus.DNS_VERIFIED

        mock_template = MagicMock()

        published_events = []

        def capture_publish_event(domain_id, event_type, payload):
            published_events.append((event_type, payload))

        with patch("custom_domain.tasks.provisioning.get_sync_db") as mock_get_db:
            mock_session = MagicMock()
            mock_session.execute.return_value.scalar_one_or_none.side_effect = [
                mock_domain,
                None,
                mock_template,
            ]
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_db.return_value.__exit__ = MagicMock()

            with (
                patch(
                    "custom_domain.tasks.provisioning.publish_event",
                    side_effect=capture_publish_event,
                ),
                patch("custom_domain.tasks.provisioning.nginx_manager") as mock_nginx,
            ):
                mock_nginx.generate_http_config = MagicMock(return_value="http config")
                mock_nginx.write_config = MagicMock()
                mock_nginx.reload = MagicMock()

                with patch("custom_domain.tasks.provisioning.certbot_service") as mock_certbot:
                    mock_cert_result = MagicMock()
                    mock_cert_result.success = False
                    mock_cert_result.error_message = "Rate limit exceeded for domain"
                    mock_certbot.provision_certificate = MagicMock(return_value=mock_cert_result)

                    with patch("custom_domain.tasks.provisioning.run_async") as mock_run:
                        mock_run.side_effect = lambda x: x

                        # Use push_request with retries at max to trigger
                        # the non-retry path (lines 159->163)
                        provision_domain_ssl.push_request(retries=2)
                        try:
                            provision_domain_ssl(str(mock_domain.id))
                        finally:
                            provision_domain_ssl.pop_request()

                        # Verify domain is set to FAILED
                        assert mock_domain.status == DomainStatus.FAILED

                        # Verify error event was published
                        error_events = [e for e in published_events if e[0] == "error"]
                        assert len(error_events) >= 1
                        error_payload = error_events[-1][1]
                        assert error_payload["code"] == "SSL_PROVISIONING_FAILED"

    def test_provision_max_retries_exceeded_error_handler(self):
        """Test the MaxRetriesExceededError exception handler (lines 241-245).

        This simulates the case where retry() raises MaxRetriesExceededError
        because max retries have been exhausted.
        """
        from celery.exceptions import MaxRetriesExceededError
        from custom_domain.tasks.provisioning import provision_domain_ssl

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.nginx_template_id = None
        mock_domain.status = DomainStatus.DNS_VERIFIED

        mock_template = MagicMock()

        published_events = []

        def capture_publish_event(domain_id, event_type, payload):
            published_events.append((event_type, payload))

        with patch("custom_domain.tasks.provisioning.get_sync_db") as mock_get_db:
            mock_session = MagicMock()
            mock_session.execute.return_value.scalar_one_or_none.side_effect = [
                mock_domain,
                None,
                mock_template,
            ]
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_db.return_value.__exit__ = MagicMock()

            with (
                patch(
                    "custom_domain.tasks.provisioning.publish_event",
                    side_effect=capture_publish_event,
                ),
                patch("custom_domain.tasks.provisioning.nginx_manager") as mock_nginx,
            ):
                # Simulate nginx throwing MaxRetriesExceededError
                # This triggers the except self.MaxRetriesExceededError block
                mock_nginx.generate_http_config = MagicMock(side_effect=MaxRetriesExceededError())

                with patch("custom_domain.tasks.provisioning.run_async") as mock_run:
                    # run_async will propagate the exception
                    def raise_for_coro(coro):
                        if hasattr(coro, "__await__"):
                            # If it's a coroutine, try to get the result
                            import asyncio

                            loop = asyncio.new_event_loop()
                            try:
                                return loop.run_until_complete(coro)
                            finally:
                                loop.close()
                        return coro

                    mock_run.side_effect = raise_for_coro

                    # When MaxRetriesExceededError is raised from within the try block,
                    # the except self.MaxRetriesExceededError handler should catch it
                    provision_domain_ssl.push_request(retries=0)
                    try:
                        provision_domain_ssl(str(mock_domain.id))
                    finally:
                        provision_domain_ssl.pop_request()

                    # Verify domain is set to FAILED
                    assert mock_domain.status == DomainStatus.FAILED

                    # Verify error event was published with MAX_RETRIES_EXCEEDED code
                    error_events = [e for e in published_events if e[0] == "error"]
                    assert len(error_events) >= 1
                    error_payload = error_events[-1][1]
                    assert error_payload["code"] == "MAX_RETRIES_EXCEEDED"
                    assert "Maximum retry" in error_payload["message"]


class TestPublishEventTimestamp:
    """The event timestamp must stay parseable by the history endpoint."""

    def test_timestamp_is_a_single_iso8601_value(self):
        """The timestamp carries exactly one UTC offset."""
        import json

        from custom_domain.tasks.provisioning import publish_event

        with patch("custom_domain.services.events.redis") as mock_redis:
            client = mock_redis.from_url.return_value
            publish_event("domain-1", "step_started", {"step": "nginx_http"})

        sent = json.loads(client.publish.call_args[0][1])
        timestamp = datetime.fromisoformat(sent["payload"]["timestamp"])
        assert timestamp.utcoffset() is not None
