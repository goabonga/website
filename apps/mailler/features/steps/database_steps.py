# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions to seed and inspect the in-process database."""

import re
from datetime import UTC, datetime, timedelta

from behave import given, then
from mailler.database import get_sync_db
from mailler.models import Email, EmailStatus, ProviderStats
from sqlalchemy import func, select


def _offset(text):
    """Parse an offset such as ``10m``, ``-2h`` or ``+3d`` into a timedelta."""
    match = re.fullmatch(r"([+-]?)(\d+)([mhd])", text.strip())
    assert match, f"Invalid offset: {text}"
    sign, amount, unit = match.groups()
    unit_name = {"m": "minutes", "h": "hours", "d": "days"}[unit]
    delta = timedelta(**{unit_name: int(amount)})
    return -delta if sign == "-" else delta


def seed_email(context, to_email="seeded@example.com", **fields):
    """Insert an email row and return its identifier as a string."""
    values = {
        "to_email": to_email,
        "subject": "Seeded subject",
        "html_content": "<p>Seeded</p>",
        "provider": "brevo",
        "status": EmailStatus.PENDING.value,
        "metadata_": {},
        **fields,
    }
    with get_sync_db() as db:
        email = Email(**values)
        db.add(email)
        db.commit()
        return str(email.id)


def load_email(to_email=None, email_id=None):
    """Return a detached copy of the matching email, or None."""
    with get_sync_db() as db:
        if email_id is not None:
            from uuid import UUID

            email = db.get(Email, UUID(email_id))
        else:
            email = db.execute(select(Email).where(Email.to_email == to_email)).scalars().first()
        if email is not None:
            db.expunge(email)
        return email


@given('a pending email to "{to_email}" via "{provider}" stored as "{alias}"')
def step_seed_pending(context, to_email, provider, alias):
    context.created_ids[alias] = seed_email(context, to_email, provider=provider)


@given('the stored email "{alias}" has already failed {count:d} times')
def step_seed_retry_count(context, alias, count):
    from uuid import UUID

    with get_sync_db() as db:
        db.get(Email, UUID(context.created_ids[alias])).retry_count = count
        db.commit()


@then('the email to "{to_email}" should be stored with status "{status}"')
def step_email_status(context, to_email, status):
    email = load_email(to_email=to_email)
    assert email is not None, f"No email stored for {to_email}"
    assert email.status == status, f"Expected {status}, got {email.status}"


@then('the stored email "{alias}" should have status "{status}"')
def step_alias_status(context, alias, status):
    email = load_email(email_id=context.created_ids[alias])
    assert email is not None and email.status == status, getattr(email, "status", None)


@then('the stored email "{alias}" should have provider message id "{message_id}"')
def step_alias_message_id(context, alias, message_id):
    email = load_email(email_id=context.created_ids[alias])
    assert email.provider_message_id == message_id, email.provider_message_id


@then('the stored email "{alias}" should have error "{message}"')
def step_alias_error(context, alias, message):
    email = load_email(email_id=context.created_ids[alias])
    assert message in (email.error_message or ""), email.error_message


@then('the email to "{to_email}" should have sender "{sender}"')
def step_email_sender(context, to_email, sender):
    email = load_email(to_email=to_email)
    assert email.from_email == sender, email.from_email


@then('the email to "{to_email}" should belong to client "{client}"')
def step_email_client(context, to_email, client):
    email = load_email(to_email=to_email)
    assert email.client_id == client, email.client_id


@then('the email to "{to_email}" should use provider "{provider}"')
def step_email_provider(context, to_email, provider):
    email = load_email(to_email=to_email)
    assert email.provider == provider, email.provider


@then('the email to "{to_email}" should have metadata "{key}" equal to "{value}"')
def step_email_metadata(context, to_email, key, value):
    email = load_email(to_email=to_email)
    assert str(email.metadata_.get(key)) == value, email.metadata_


@then("no email should be stored")
def step_no_email(context):
    with get_sync_db() as db:
        assert db.execute(select(func.count()).select_from(Email)).scalar_one() == 0


@then('the "{provider}" statistics should count {count:d} "{counter}" email')
def step_provider_stats(context, provider, count, counter):
    with get_sync_db() as db:
        stats = db.execute(
            select(ProviderStats).where(ProviderStats.provider == provider)
        ).scalar_one_or_none()
        assert stats is not None, f"No statistics for {provider}"
        assert getattr(stats, f"{counter}_count") == count, getattr(stats, f"{counter}_count")


def _seed_table(context, client_id=None):
    """Seed emails from a table.

    Optional columns: subject, provider, status, client_id, alias, ``age`` (how
    long ago the email was created, e.g. ``10m``) and ``scheduled_in`` (offset
    of the scheduled time, e.g. ``-5m`` or ``+2h``).
    """
    now = datetime.now(UTC)
    for row in context.table:
        fields = {
            key: row[key]
            for key in ("subject", "provider", "status", "client_id")
            if key in row.headings
        }
        if client_id is not None:
            fields["client_id"] = client_id
        if "age" in row.headings:
            fields["created_at"] = now - _offset(row["age"])
        if "scheduled_in" in row.headings:
            fields["scheduled_at"] = now + _offset(row["scheduled_in"])
        alias = row["alias"] if "alias" in row.headings else None
        email_id = seed_email(context, row["to_email"], **fields)
        if alias:
            context.created_ids[alias] = email_id


@given("the following emails are stored")
def step_seed_emails(context):
    _seed_table(context)


@given('the following emails are stored for client "{client}"')
def step_seed_client_emails(context, client):
    _seed_table(context, client)


@then('the email to "{to_email}" should be scheduled')
def step_email_scheduled(context, to_email):
    email = load_email(to_email=to_email)
    assert email is not None and email.scheduled_at is not None, "Email is not scheduled"


@then('the email to "{to_email}" should no longer be stored')
def step_email_gone(context, to_email):
    assert load_email(to_email=to_email) is None, f"{to_email} is still stored"


@then('the email to "{to_email}" should still be stored')
def step_email_still_stored(context, to_email):
    assert load_email(to_email=to_email) is not None, f"{to_email} was removed"


@then('the email to "{to_email}" should have subject "{subject}"')
def step_email_subject(context, to_email, subject):
    email = load_email(to_email=to_email)
    assert email is not None and email.subject == subject, getattr(email, "subject", None)


@then('no email should be stored for "{to_email}"')
def step_no_email_for(context, to_email):
    assert load_email(to_email=to_email) is None, f"An email to {to_email} exists"
