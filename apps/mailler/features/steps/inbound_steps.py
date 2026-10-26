# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the inbound email scenarios.

The IMAP mailbox and the webhook target are replaced by in-memory doubles;
parsing, storage, attachments and the API run for real.
"""

import tempfile
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from unittest.mock import MagicMock, patch

from behave import given, then, when
from mailler.database import get_sync_db
from mailler.models import InboundAttachment, InboundEmail
from mailler.tasks import inbound
from sqlalchemy import select
from steps.settings_steps import set_setting


def _build_message(sender, subject, attachment=None):
    message = EmailMessage()
    message["From"] = sender
    message["To"] = "inbox@example.com"
    message["Subject"] = subject
    message["Message-ID"] = f"<{subject.replace(' ', '-')}@example.com>"
    message.set_content(f"Body of {subject}")
    if attachment:
        message.add_attachment(
            attachment[1], maintype="text", subtype="plain", filename=attachment[0]
        )
    return message.as_bytes()


def _init_state(context):
    context.mailbox = []
    context.webhook_status = (200, True)
    context.delivered_payloads = []


@given("inbound processing is configured")
def step_inbound_configured(context):
    set_setting(context, "inbound_enabled", True)
    set_setting(context, "inbound_webhook_url", "https://hooks.example.test/inbound")
    set_setting(context, "inbound_attachments_dir", tempfile.mkdtemp(prefix="mailler-att-"))
    set_setting(context, "protonmail_host", "imap.bdd.example")
    set_setting(context, "inbound_imap_port", 143)
    _init_state(context)


@given("inbound processing is enabled without a mailbox")
def step_inbound_without_mailbox(context):
    set_setting(context, "inbound_enabled", True)
    set_setting(context, "inbound_webhook_url", "https://hooks.example.test/inbound")
    set_setting(context, "inbound_attachments_dir", "")
    set_setting(context, "protonmail_host", "")
    set_setting(context, "inbound_imap_port", 0)
    _init_state(context)


@given('the mailbox contains a message from "{sender}" titled "{subject}"')
def step_mailbox_message(context, sender, subject):
    context.mailbox.append(_build_message(sender, subject))


@given(
    'the mailbox contains a message from "{sender}" with subject "{subject}" '
    'and the attachment "{filename}" containing "{content}"'
)
def step_mailbox_message_with_attachment(context, sender, subject, filename, content):
    context.mailbox.append(_build_message(sender, subject, (filename, content.encode())))


@given("the webhook target answers {status:d}")
@when("the webhook target answers {status:d}")
def step_webhook_answers(context, status):
    context.webhook_status = (status, 200 <= status < 300)


@when("the inbound poll task runs")
def step_run_poll(context):
    if not hasattr(context, "mailbox"):
        _init_state(context)

    def deliver(payload):
        context.delivered_payloads.append(payload)
        return context.webhook_status

    imap = MagicMock()
    unseen = [(str(index + 1), raw) for index, raw in enumerate(context.mailbox)]
    with (
        patch.object(inbound, "connect", return_value=imap),
        patch.object(inbound, "ensure_folder_exists"),
        patch.object(inbound, "fetch_unseen_emails", return_value=unseen),
        patch.object(inbound, "move_to_folder", return_value=True) as move,
        patch.object(inbound, "deliver_webhook", side_effect=deliver),
    ):
        context.task_result = inbound.poll_inbound_emails()
        context.moved_messages = move.call_count


@when("the inbound retry task runs")
def step_run_retry(context):
    def deliver(payload):
        context.delivered_payloads.append(payload)
        return context.webhook_status

    with patch.object(inbound, "deliver_webhook", side_effect=deliver):
        context.task_result = inbound.retry_failed_inbound()


@when("the attachment cleanup task runs")
def step_run_cleanup(context):
    context.task_result = inbound.cleanup_expired_attachments()


@given("every stored attachment has expired")
@when("every stored attachment has expired")
def step_attachments_expired(context):
    with get_sync_db() as db:
        for attachment in db.execute(select(InboundAttachment)).scalars():
            attachment.expires_at = datetime.now(UTC) - timedelta(hours=1)
        db.commit()


@then('I store the download token of the attachment "{filename}" as "{alias}"')
def step_store_token(context, filename, alias):
    with get_sync_db() as db:
        attachment = db.execute(
            select(InboundAttachment).where(InboundAttachment.filename == filename)
        ).scalar_one()
        context.created_ids[alias] = str(attachment.download_token)


@then('the inbound email from "{sender}" should be stored with status "{status}"')
def step_inbound_status(context, sender, status):
    with get_sync_db() as db:
        record = db.execute(
            select(InboundEmail).where(InboundEmail.from_email == sender)
        ).scalar_one()
        assert record.status == status, record.status


@then("{count:d} message should have been moved to the processed folder")
@then("{count:d} messages should have been moved to the processed folder")
def step_moved(context, count):
    assert context.moved_messages == count, context.moved_messages


@then("{count:d} webhook delivery should have been attempted")
@then("{count:d} webhook deliveries should have been attempted")
def step_deliveries(context, count):
    assert len(context.delivered_payloads) == count, len(context.delivered_payloads)


@then('the response body should be "{content}"')
def step_response_body(context, content):
    assert context.response.text == content, context.response.text
