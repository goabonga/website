# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Capture the e-mails that the application queues for Celery."""

import re
from unittest.mock import patch

from auth.services import email as email_service


class Mailbox:
    """Messages queued through ``send_email_task.delay`` during a scenario."""

    def __init__(self):
        self.messages = []

    def record(self, to, subject, body_html, body_text="", from_email=None, from_name=None):
        self.messages.append({"to": to, "subject": subject, "html": body_html, "text": body_text})

    def to(self, address):
        return [m for m in self.messages if m["to"].lower() == address.lower()]

    def last_code_for(self, address):
        """The six digit code of the latest message sent to ``address``."""
        message = self.to(address)[-1]
        return re.search(r"\b(\d{6})\b", message["text"] or message["html"]).group(1)


def capture_mail(context):
    """Replace the Celery e-mail task by a recorder and expose it as ``context.mailbox``."""
    if getattr(context, "mailbox", None) is None:
        context.mailbox = Mailbox()
        patcher = patch.object(email_service.send_email_task, "delay", context.mailbox.record)
        patcher.start()
        context.add_cleanup(patcher.stop)
    return context.mailbox
