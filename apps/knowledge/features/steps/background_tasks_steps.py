# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the background tasks feature.

Tasks are plain Python callables and run in the test process. The broker and
the database are never contacted: the mailler service is the fake of the email
feature (an httpx mock transport), and the async SQLAlchemy engine used by the periodic tasks is replaced
by a fake session that serves the objects of the scenario.
"""

import contextlib
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from behave import given, then, when

from knowledge import tasks
from knowledge.celery import celery_app
from knowledge.config import get_settings
from knowledge.models import Organization
from knowledge.models.workspace_deletion_request import (
    DeletionRequestStatus,
    WorkspaceDeletionRequest,
)


def _patch(context, target, value, attribute=False):
    patcher = patch.object(*target, value) if attribute else patch(target, value)
    patcher.start()
    context.add_cleanup(patcher.stop)


@then('the Celery application should use the queue "{queue}"')
def step_queue(context, queue):
    assert celery_app.conf.task_default_queue == queue


@then('the Celery application should register the task "{name}"')
def step_registered(context, name):
    celery_app.loader.import_default_modules()
    assert name in celery_app.tasks


@then('the beat schedule should run "{task}" every {seconds:d} seconds')
def step_beat(context, task, seconds):
    entries = [e for e in celery_app.conf.beat_schedule.values() if e["task"] == task]
    assert entries and entries[0]["schedule"] == float(seconds), entries


# --- emails ---------------------------------------------------------------
# The "mailler service that ..." steps are those of the email feature.


def _use_mailler(context):
    """Make the tasks use the mailler service of the scenario."""
    _patch(context, "knowledge.tasks.get_mailler_client", lambda: context.mailler)


@when('the task sends the "{template}" email to "{to}"')
def step_send_task(context, template, to):
    _use_mailler(context)
    variables = {row["variable"]: row["value"] for row in context.table}
    context.task_result = tasks.send_email_task.run(to, template, variables)


@then("the task should succeed")
def step_task_ok(context):
    assert context.task_result["success"] is True, context.task_result


@then('the task should fail with "{text}"')
def step_task_failed(context, text):
    assert context.task_result["success"] is False and text in context.task_result["error"]


@then('mailler should have been asked to send the template "{slug}" to "{to}"')
def step_received(context, slug, to):
    body = json.loads(context.mailler_requests[-1].content)
    assert body["template_slug"] == slug and body["to_email"] == to, body


@then('the mailler request should carry the variable "{name}" set to "{value}"')
def step_variable(context, name, value):
    body = json.loads(context.mailler_requests[-1].content)
    assert body["variables"][name] == value, body["variables"]


@when('the workspace deletion email task runs for "{workspace}" with the link "{url}"')
def step_deletion_email(context, workspace, url):
    _use_mailler(context)
    context.task_result = tasks.send_workspace_deletion_email.run(
        "owner@example.test", workspace, url, 2026
    )


class _Retry(Exception):
    pass


@when('the task is run by a worker for "{template}" to "{to}"')
def step_run_by_worker(context, template, to):
    """Run the task body with the request context a worker gives it."""
    _use_mailler(context)
    context.retry = None
    task = tasks.send_email_task

    def retry(**kwargs):
        context.retry = kwargs
        return _Retry()

    task.push_request(id="task-1", retries=0)
    try:
        with patch.object(task, "retry", retry), contextlib.suppress(_Retry):
            task.run(to, template, {"workspace_name": "Acme"})
    finally:
        task.pop_request()


@then("the task should be retried with a delay of {seconds:d} seconds")
def step_retried(context, seconds):
    assert context.retry is not None, "the task was not retried"
    assert context.retry["countdown"] == seconds, context.retry


# --- periodic tasks -------------------------------------------------------


class _FakeSession:
    def __init__(self, requests, organization):
        self.requests = requests
        self.organization = organization
        self.deleted = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def execute(self, statement):
        result = MagicMock()
        result.scalars.return_value.all.return_value = self.requests
        result.scalar_one_or_none.return_value = self.organization
        return result

    async def delete(self, obj):
        self.deleted.append(obj)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _scheduled(context, name, when):
    organization = Organization(id=uuid4(), name=name, slug=name.lower())
    request = WorkspaceDeletionRequest(
        id=uuid4(),
        organization_id=organization.id,
        organization=organization,
        requested_by=uuid4(),
        email="owner@example.test",
        token="token",
        status=DeletionRequestStatus.SCHEDULED,
        expires_at=datetime.now(UTC) + timedelta(days=1),
        scheduled_deletion_at=when,
        cancel_token="cancel-token",
    )
    context.organization = organization
    context.deletion_request = request
    session = _FakeSession([request], organization)
    context.db_session = session
    engine = MagicMock()
    engine.dispose = AsyncMock()
    _patch(context, "sqlalchemy.ext.asyncio.create_async_engine", lambda url: engine)
    _patch(context, "sqlalchemy.ext.asyncio.async_sessionmaker", lambda *a, **k: lambda: session)


@given('a workspace "{name}" scheduled for deletion yesterday')
def step_due(context, name):
    _scheduled(context, name, datetime.now(UTC) - timedelta(days=1))


@given('a workspace "{name}" scheduled for deletion in {days:d} days')
def step_future_days(context, name, days):
    _scheduled(context, name, datetime.now(UTC) + timedelta(days=days))


@given('a workspace "{name}" scheduled for deletion in {hours:d} hours')
def step_future_hours(context, name, hours):
    _scheduled(context, name, datetime.now(UTC) + timedelta(hours=hours))


@when("the scheduled deletions task runs")
def step_run_deletions(context):
    context.task_result = tasks.process_scheduled_deletions()


@then('the workspace "{name}" should have been deleted')
def step_deleted(context, name):
    assert [o.name for o in context.db_session.deleted] == [name]


@then("the deletion request should be completed")
def step_completed(context):
    assert context.deletion_request.status == DeletionRequestStatus.CONFIRMED


@then("the task should report {count:d} deleted workspace")
def step_deleted_count(context, count):
    assert context.task_result["deleted"] == count, context.task_result


@when("the deletion reminders task runs")
def step_run_reminders(context):
    context.reminders = []
    _patch(
        context,
        "knowledge.tasks.send_workspace_deletion_reminder_email.delay",
        lambda **kwargs: context.reminders.append(kwargs),
    )
    _patch(context, (get_settings(), "app_base_url"), "https://app.example.test", attribute=True)
    context.task_result = tasks.send_deletion_reminders()


@then('a reminder email should be queued for "{name}" with a cancellation link')
def step_reminder_queued(context, name):
    assert len(context.reminders) == 1, context.reminders
    reminder = context.reminders[0]
    assert reminder["workspace_name"] == name
    assert (
        reminder["cancel_url"]
        == "https://app.example.test/organizations/delete/cancel/cancel-token"
    )


@then("the reminder should be marked as sent")
def step_reminder_marked(context):
    assert context.deletion_request.reminder_sent_at is not None


@then("no reminder email should be queued")
def step_no_reminder(context):
    assert context.reminders == []
