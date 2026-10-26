# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for Celery tasks: emails sent through mailler, deletion processing."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge import email_templates
from knowledge.services.mailler import MaillerError, SendResult
from knowledge.tasks import (
    _send_template,
    send_email_task,
    send_workspace_deleted_email,
    send_workspace_deletion_email,
    send_workspace_deletion_reminder_email,
    send_workspace_deletion_scheduled_email,
    send_workspace_invitation_email,
)


class FakeRetry(Exception):
    """Raised by the fake task in place of Celery's Retry exception."""


class FakeTask:
    """Lightweight stand-in for the bound ``self`` of a Celery task."""

    name = "knowledge.tasks.send_email"

    def __init__(self, retries=0, task_id="task-1"):
        self.request = MagicMock(retries=retries, id=task_id)
        self.retry_kwargs = None

    def retry(self, **kwargs):
        self.retry_kwargs = kwargs
        return FakeRetry("retry")


def _settings(max_retries=3, delay=60):
    settings = MagicMock()
    settings.mailler_max_retries = max_retries
    settings.mailler_retry_delay = delay
    return settings


@pytest.fixture
def mailler():
    """The mailler client used by the tasks."""
    client = MagicMock()
    client.send_template.return_value = SendResult(id="mail-1", status="queued")
    with (
        patch("knowledge.tasks.get_mailler_client", return_value=client),
        patch("knowledge.tasks.get_settings", return_value=_settings()),
    ):
        yield client


# ============================================================
# _send_template
# ============================================================


class TestSendTemplate:
    def test_success(self, mailler):
        result = _send_template(FakeTask(), "ann@example.test", "workspace_deleted", {"a": 1})

        assert result == {"success": True, "email_id": "mail-1", "missing_variables": []}
        mailler.send_template.assert_called_once_with(
            "workspace_deleted",
            "ann@example.test",
            {"a": 1},
            idempotency_key="knowledge.tasks.send_email:task-1",
        )

    def test_missing_variables_are_returned(self, mailler):
        mailler.send_template.return_value = SendResult(
            id="mail-1", status="queued", missing_variables=["role"]
        )
        result = _send_template(FakeTask(), "ann@example.test", "workspace_invitation", {})
        assert result["missing_variables"] == ["role"]

    def test_the_retries_of_a_task_share_its_idempotency_key(self, mailler):
        _send_template(FakeTask(retries=0), "a@example.test", "t", {})
        _send_template(FakeTask(retries=2), "a@example.test", "t", {})
        keys = [call.kwargs["idempotency_key"] for call in mailler.send_template.call_args_list]
        assert keys[0] == keys[1]

    def test_no_key_when_the_task_has_no_id(self, mailler):
        _send_template(FakeTask(task_id=None), "a@example.test", "t", {})
        assert mailler.send_template.call_args.kwargs["idempotency_key"] is None

    def test_failure_that_can_pass_retries_with_a_growing_delay(self, mailler):
        error = MaillerError("down", status_code=503, retryable=True)
        mailler.send_template.side_effect = error
        task = FakeTask(retries=2)

        with pytest.raises(FakeRetry):
            _send_template(task, "a@example.test", "t", {})

        assert task.retry_kwargs == {"exc": error, "countdown": 240, "max_retries": 3}

    def test_retries_stop_at_the_configured_maximum(self, mailler):
        mailler.send_template.side_effect = MaillerError("down", 503, retryable=True)
        result = _send_template(FakeTask(retries=3), "a@example.test", "t", {})
        assert result == {"success": False, "error": "down", "status_code": 503}

    @pytest.mark.parametrize("status", [403, 404, 422])
    def test_failure_that_will_not_pass_is_not_retried(self, mailler, status):
        mailler.send_template.side_effect = MaillerError("refused", status, retryable=False)
        task = FakeTask()

        result = _send_template(task, "a@example.test", "t", {})

        assert result == {"success": False, "error": "refused", "status_code": status}
        assert task.retry_kwargs is None

    def test_failure_without_status(self, mailler):
        mailler.send_template.side_effect = MaillerError("not configured")
        result = _send_template(FakeTask(), "a@example.test", "t", {})
        assert result["status_code"] is None


# ============================================================
# send_email_task and the tasks of each email
# ============================================================


class TestSendEmailTask:
    @patch("knowledge.tasks._send_template")
    def test_generic_task(self, mock_send):
        mock_send.return_value = {"success": True}
        result = send_email_task.run("ann@example.test", "workspace_deleted", {"x": 1})
        assert result == {"success": True}
        assert mock_send.call_args.args[1:] == ("ann@example.test", "workspace_deleted", {"x": 1})


class TestEmailTasks:
    """Each task sends its template with the variables the template uses."""

    @patch("knowledge.tasks._send_template")
    def test_workspace_deletion_email(self, mock_send):
        send_workspace_deletion_email.run(
            "u@example.test", "My Workspace", "https://x/confirm", 2026
        )
        _task, to, slug, variables = mock_send.call_args.args
        assert (to, slug) == ("u@example.test", email_templates.WORKSPACE_DELETION)
        assert variables == {
            "workspace_name": "My Workspace",
            "confirmation_url": "https://x/confirm",
            "user_email": "u@example.test",
            "year": 2026,
        }

    @patch("knowledge.tasks._send_template")
    def test_workspace_deletion_scheduled_email(self, mock_send):
        send_workspace_deletion_scheduled_email.run(
            "u@example.test", "My Workspace", "Jan 15", 2026
        )
        _task, to, slug, variables = mock_send.call_args.args
        assert slug == email_templates.WORKSPACE_DELETION_SCHEDULED
        assert variables["deletion_date"] == "Jan 15"

    @patch("knowledge.tasks._send_template")
    def test_workspace_deleted_email(self, mock_send):
        send_workspace_deleted_email.run(
            "u@example.test", "My Workspace", "https://x/support", 2026
        )
        _task, to, slug, variables = mock_send.call_args.args
        assert slug == email_templates.WORKSPACE_DELETED
        assert variables["support_url"] == "https://x/support"

    @patch("knowledge.tasks._send_template")
    def test_workspace_deletion_reminder_email(self, mock_send):
        send_workspace_deletion_reminder_email.run(
            "u@example.test", "My Workspace", "Jan 15", "https://x/cancel", 2026
        )
        _task, to, slug, variables = mock_send.call_args.args
        assert slug == email_templates.WORKSPACE_DELETION_REMINDER
        assert variables["cancel_url"] == "https://x/cancel"

    @patch("knowledge.tasks._send_template")
    def test_workspace_invitation_email(self, mock_send):
        send_workspace_invitation_email.run(
            "i@example.test", "My Workspace", "admin@example.test", "member", "https://x/i", 2026
        )
        _task, to, slug, variables = mock_send.call_args.args
        assert slug == email_templates.WORKSPACE_INVITATION
        assert variables == {
            "workspace_name": "My Workspace",
            "inviter_name": "admin@example.test",
            "role": "member",
            "invitation_url": "https://x/i",
            "user_email": "i@example.test",
            "year": 2026,
        }

    def test_the_variables_are_the_ones_the_shipped_templates_use(self):
        """Every placeholder of a template is provided by its task (checked on the sources)."""
        import re

        placeholder = re.compile(r"\{\{\s*(\w+)\s*\}\}")
        provided = {
            email_templates.WORKSPACE_DELETION: {
                "workspace_name",
                "confirmation_url",
                "user_email",
                "year",
            },
            email_templates.WORKSPACE_DELETION_SCHEDULED: {
                "workspace_name",
                "deletion_date",
                "user_email",
                "year",
            },
            email_templates.WORKSPACE_DELETED: {
                "workspace_name",
                "support_url",
                "user_email",
                "year",
            },
            email_templates.WORKSPACE_DELETION_REMINDER: {
                "workspace_name",
                "deletion_date",
                "cancel_url",
                "user_email",
                "year",
            },
            email_templates.WORKSPACE_INVITATION: {
                "workspace_name",
                "inviter_name",
                "role",
                "invitation_url",
                "user_email",
                "year",
            },
        }
        for slug, names in provided.items():
            source = (email_templates.TEMPLATES_DIR / f"{slug}.mjml").read_text()
            subject = (email_templates.TEMPLATES_DIR / f"{slug}.json").read_text()
            used = set(placeholder.findall(source)) | set(placeholder.findall(subject))
            assert used == names, slug


# ============================================================
# send_deletion_reminders task
# (Local imports: patch at source modules, not knowledge.tasks)
# ============================================================


def _mock_async_session(mock_session):
    """Create a mock async_sessionmaker that yields mock_session via async-with."""
    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock(return_value=mock_session_ctx)
    return mock_factory


class TestSendDeletionReminders:
    """Tests for send_deletion_reminders (lines 356-465).

    This function does local imports of create_async_engine, async_sessionmaker,
    and get_settings, so patches must target the source modules.
    """

    @patch("knowledge.tasks.send_workspace_deletion_reminder_email")
    @patch("knowledge.config.get_settings")
    def test_no_pending_reminders(self, mock_get_settings, mock_send_reminder):
        from knowledge.tasks import send_deletion_reminders

        settings = MagicMock()
        settings.database_url = "postgresql+asyncpg://localhost/test"
        settings.app_base_url = "https://example.com"
        mock_get_settings.return_value = settings

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_factory = _mock_async_session(mock_session)
        mock_engine = AsyncMock()
        mock_engine.dispose = AsyncMock()

        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
            patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=mock_factory),
        ):
            result = send_deletion_reminders()

        assert result["sent"] == 0
        assert result["errors"] == 0

    @patch("knowledge.tasks.send_workspace_deletion_reminder_email")
    @patch("knowledge.config.get_settings")
    def test_sends_reminders_for_ready_requests(self, mock_get_settings, mock_send_reminder):
        from datetime import UTC, datetime, timedelta

        from knowledge.tasks import send_deletion_reminders

        settings = MagicMock()
        settings.database_url = "postgresql+asyncpg://localhost/test"
        settings.app_base_url = "https://example.com"
        mock_get_settings.return_value = settings

        deletion_req = MagicMock()
        deletion_req.id = "req-1"
        deletion_req.needs_reminder = True
        deletion_req.organization = MagicMock()
        deletion_req.organization.name = "Test Org"
        deletion_req.organization_id = "org-1"
        deletion_req.email = "user@example.com"
        deletion_req.cancel_token = "cancel-token-123"
        deletion_req.scheduled_deletion_at = datetime.now(UTC) + timedelta(hours=12)
        deletion_req.mark_reminder_sent = MagicMock()

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [deletion_req]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = _mock_async_session(mock_session)
        mock_engine = AsyncMock()
        mock_engine.dispose = AsyncMock()

        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
            patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=mock_factory),
        ):
            result = send_deletion_reminders()

        assert result["sent"] == 1
        assert result["errors"] == 0
        mock_send_reminder.delay.assert_called_once()
        deletion_req.mark_reminder_sent.assert_called_once()

    @patch("knowledge.tasks.send_workspace_deletion_reminder_email")
    @patch("knowledge.config.get_settings")
    def test_skips_request_not_needing_reminder(self, mock_get_settings, mock_send_reminder):
        from knowledge.tasks import send_deletion_reminders

        settings = MagicMock()
        settings.database_url = "postgresql+asyncpg://localhost/test"
        settings.app_base_url = "https://example.com"
        mock_get_settings.return_value = settings

        deletion_req = MagicMock()
        deletion_req.needs_reminder = False

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [deletion_req]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_factory = _mock_async_session(mock_session)
        mock_engine = AsyncMock()
        mock_engine.dispose = AsyncMock()

        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
            patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=mock_factory),
        ):
            result = send_deletion_reminders()

        assert result["sent"] == 0
        mock_send_reminder.delay.assert_not_called()

    @patch("knowledge.tasks.send_workspace_deletion_reminder_email")
    @patch("knowledge.config.get_settings")
    def test_skips_request_without_organization(self, mock_get_settings, mock_send_reminder):
        from knowledge.tasks import send_deletion_reminders

        settings = MagicMock()
        settings.database_url = "postgresql+asyncpg://localhost/test"
        settings.app_base_url = "https://example.com"
        mock_get_settings.return_value = settings

        deletion_req = MagicMock()
        deletion_req.needs_reminder = True
        deletion_req.organization = None
        deletion_req.id = "req-2"

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [deletion_req]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_factory = _mock_async_session(mock_session)
        mock_engine = AsyncMock()
        mock_engine.dispose = AsyncMock()

        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
            patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=mock_factory),
        ):
            result = send_deletion_reminders()

        assert result["sent"] == 0
        mock_send_reminder.delay.assert_not_called()

    @patch("knowledge.tasks.send_workspace_deletion_reminder_email")
    @patch("knowledge.config.get_settings")
    def test_skips_request_without_scheduled_deletion_at(
        self, mock_get_settings, mock_send_reminder
    ):
        from knowledge.tasks import send_deletion_reminders

        settings = MagicMock()
        settings.database_url = "postgresql+asyncpg://localhost/test"
        settings.app_base_url = "https://example.com"
        mock_get_settings.return_value = settings

        deletion_req = MagicMock()
        deletion_req.needs_reminder = True
        deletion_req.organization = MagicMock()
        deletion_req.organization.name = "Test Org"
        deletion_req.scheduled_deletion_at = None

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [deletion_req]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_factory = _mock_async_session(mock_session)
        mock_engine = AsyncMock()
        mock_engine.dispose = AsyncMock()

        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
            patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=mock_factory),
        ):
            result = send_deletion_reminders()

        assert result["sent"] == 0
        mock_send_reminder.delay.assert_not_called()

    @patch("knowledge.tasks.send_workspace_deletion_reminder_email")
    @patch("knowledge.config.get_settings")
    def test_exception_during_reminder_increments_error_count(
        self, mock_get_settings, mock_send_reminder
    ):
        from datetime import UTC, datetime, timedelta

        from knowledge.tasks import send_deletion_reminders

        settings = MagicMock()
        settings.database_url = "postgresql+asyncpg://localhost/test"
        settings.app_base_url = "https://example.com"
        mock_get_settings.return_value = settings

        deletion_req = MagicMock()
        deletion_req.id = "req-err"
        deletion_req.needs_reminder = True
        deletion_req.organization = MagicMock()
        deletion_req.organization.name = "Test Org"
        deletion_req.organization_id = "org-1"
        deletion_req.email = "user@example.com"
        deletion_req.cancel_token = "cancel-token"
        deletion_req.scheduled_deletion_at = datetime.now(UTC) + timedelta(hours=12)
        deletion_req.mark_reminder_sent = MagicMock(side_effect=RuntimeError("DB commit error"))

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [deletion_req]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        mock_factory = _mock_async_session(mock_session)
        mock_engine = AsyncMock()
        mock_engine.dispose = AsyncMock()

        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
            patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=mock_factory),
        ):
            result = send_deletion_reminders()

        assert result["errors"] == 1
        assert result["sent"] == 0


# ============================================================
# process_scheduled_deletions task
# ============================================================


class TestProcessScheduledDeletions:
    """Tests for process_scheduled_deletions (lines 468-571).

    Same local-import pattern as send_deletion_reminders.
    """

    @patch("knowledge.config.get_settings")
    def test_no_pending_deletions(self, mock_get_settings):
        from knowledge.tasks import process_scheduled_deletions

        settings = MagicMock()
        settings.database_url = "postgresql+asyncpg://localhost/test"
        mock_get_settings.return_value = settings

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_factory = _mock_async_session(mock_session)
        mock_engine = AsyncMock()
        mock_engine.dispose = AsyncMock()

        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
            patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=mock_factory),
        ):
            result = process_scheduled_deletions()

        assert result["deleted"] == 0
        assert result["errors"] == 0

    @patch("knowledge.config.get_settings")
    def test_deletes_organization(self, mock_get_settings):
        from knowledge.tasks import process_scheduled_deletions

        settings = MagicMock()
        settings.database_url = "postgresql+asyncpg://localhost/test"
        mock_get_settings.return_value = settings

        deletion_req = MagicMock()
        deletion_req.id = "del-1"
        deletion_req.organization_id = "org-1"
        deletion_req.execute_scheduled = MagicMock()

        mock_org = MagicMock()
        mock_org.id = "org-1"
        mock_org.name = "Test Org"

        mock_scalars_del = MagicMock()
        mock_scalars_del.all.return_value = [deletion_req]
        mock_result_del = MagicMock()
        mock_result_del.scalars.return_value = mock_scalars_del

        mock_result_org = MagicMock()
        mock_result_org.scalar_one_or_none.return_value = mock_org

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[mock_result_del, mock_result_org])
        mock_session.delete = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_factory = _mock_async_session(mock_session)
        mock_engine = AsyncMock()
        mock_engine.dispose = AsyncMock()

        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
            patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=mock_factory),
        ):
            result = process_scheduled_deletions()

        assert result["deleted"] == 1
        assert result["errors"] == 0
        mock_session.delete.assert_awaited_once_with(mock_org)
        deletion_req.execute_scheduled.assert_called_once()

    @patch("knowledge.config.get_settings")
    def test_organization_already_deleted(self, mock_get_settings):
        from knowledge.tasks import process_scheduled_deletions

        settings = MagicMock()
        settings.database_url = "postgresql+asyncpg://localhost/test"
        mock_get_settings.return_value = settings

        deletion_req = MagicMock()
        deletion_req.id = "del-2"
        deletion_req.organization_id = "org-gone"
        deletion_req.execute_scheduled = MagicMock()

        mock_scalars_del = MagicMock()
        mock_scalars_del.all.return_value = [deletion_req]
        mock_result_del = MagicMock()
        mock_result_del.scalars.return_value = mock_scalars_del

        mock_result_org = MagicMock()
        mock_result_org.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[mock_result_del, mock_result_org])
        mock_session.commit = AsyncMock()

        mock_factory = _mock_async_session(mock_session)
        mock_engine = AsyncMock()
        mock_engine.dispose = AsyncMock()

        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
            patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=mock_factory),
        ):
            result = process_scheduled_deletions()

        assert result["deleted"] == 0
        deletion_req.execute_scheduled.assert_called_once()

    @patch("knowledge.config.get_settings")
    def test_exception_during_deletion_increments_error(self, mock_get_settings):
        from knowledge.tasks import process_scheduled_deletions

        settings = MagicMock()
        settings.database_url = "postgresql+asyncpg://localhost/test"
        mock_get_settings.return_value = settings

        deletion_req = MagicMock()
        deletion_req.id = "del-err"
        deletion_req.organization_id = "org-err"

        mock_scalars_del = MagicMock()
        mock_scalars_del.all.return_value = [deletion_req]
        mock_result_del = MagicMock()
        mock_result_del.scalars.return_value = mock_scalars_del

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[mock_result_del, RuntimeError("DB error")])
        mock_session.rollback = AsyncMock()

        mock_factory = _mock_async_session(mock_session)
        mock_engine = AsyncMock()
        mock_engine.dispose = AsyncMock()

        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
            patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=mock_factory),
        ):
            result = process_scheduled_deletions()

        assert result["errors"] == 1
        assert result["deleted"] == 0
