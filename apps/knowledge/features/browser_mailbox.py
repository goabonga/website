# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The mailler service for the browser scenarios.

The email tasks of the application run synchronously, as Celery would run them in a worker,
and send through this fake, which records the emails the way a mailbox would hold them.
"""

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch

from knowledge import tasks
from knowledge.services.mailler import SendResult

#: The tasks that send an email.
EMAIL_TASKS = (
    "send_email_task",
    "send_workspace_deletion_email",
    "send_workspace_deletion_scheduled_email",
    "send_workspace_deleted_email",
    "send_workspace_invitation_email",
    "send_workspace_deletion_reminder_email",
)


class Mailbox:
    """Records every email sent through the mailler service."""

    def __init__(self):
        self.sent: list[SimpleNamespace] = []

    def send_template(self, template_slug, to, variables, idempotency_key=None):
        self.sent.append(SimpleNamespace(template=template_slug, to=to, variables=variables))
        return SendResult(id=f"email-{len(self.sent)}", status="queued")

    def to(self, address):
        return [mail for mail in self.sent if mail.to == address]


def deliver_in_process(mailbox: Mailbox, scenario: ExitStack) -> None:
    """Send the emails of the tasks right away, through ``mailbox``, for the scenario."""
    scenario.enter_context(patch.object(tasks, "get_mailler_client", lambda: mailbox))
    for name in EMAIL_TASKS:
        task = getattr(tasks, name)
        scenario.enter_context(
            patch.object(
                task,
                "delay",
                lambda *args, task=task, **kwargs: task.apply(args=args, kwargs=kwargs),
            )
        )
