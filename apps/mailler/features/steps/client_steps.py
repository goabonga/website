# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the authorized clients registry."""

from behave import given, then
from mailler.database import get_sync_db
from mailler.models import AuthorizedClient
from sqlalchemy import select


def _default_record(client_id):
    """The record given to a client that scenarios only mention by its identity."""
    return {
        "client_id": client_id,
        "name": client_id,
        "is_active": True,
        "from_email": f"{client_id}@bdd.example",
        "from_name": "BDD sender",
        "reply_to": None,
        "allowed_senders": [],
        "allowed_providers": ["brevo", "ses"],
        "default_provider": "brevo",
    }


def register_client(client_id, replace=False, **fields):
    """Create the record of a client, or update it when ``replace`` is set."""
    with get_sync_db() as db:
        record = db.execute(
            select(AuthorizedClient).where(AuthorizedClient.client_id == client_id)
        ).scalar_one_or_none()
        if record is None:
            db.add(AuthorizedClient(**{**_default_record(client_id), **fields}))
        elif replace:
            for name, value in fields.items():
                setattr(record, name, value)
        db.commit()


def _split(cell):
    return [item.strip() for item in cell.split(",") if item.strip()]


def _senders(cell):
    """Parse ``email=Name;email=Name`` into identities."""
    senders = []
    for item in cell.split(";"):
        if item.strip():
            email, _, name = item.partition("=")
            senders.append({"email": email.strip(), "name": name.strip() or None})
    return senders


@given("the following clients are registered")
def step_register_clients(context):
    """Columns: client_id plus any of from_email, from_name, reply_to, allowed_senders,
    allowed_providers, default_provider, is_active (yes/no)."""
    for row in context.table:
        fields = {}
        for heading in row.headings:
            value = row[heading].strip()
            if heading == "client_id":
                continue
            if heading == "allowed_providers":
                fields[heading] = _split(value)
            elif heading == "allowed_senders":
                fields[heading] = _senders(value)
            elif heading == "is_active":
                fields[heading] = value.lower() in ("yes", "true")
            else:
                fields[heading] = value or None
        register_client(row["client_id"], replace=True, **fields)


@given('the client "{client_id}" is deactivated')
def step_deactivate_client(context, client_id):
    register_client(client_id, replace=True, is_active=False)


@given('the client "{client_id}" is activated')
def step_activate_client(context, client_id):
    register_client(client_id, replace=True, is_active=True)


@then('the client "{client_id}" should be {state}')
def step_client_state(context, client_id, state):
    with get_sync_db() as db:
        record = db.execute(
            select(AuthorizedClient).where(AuthorizedClient.client_id == client_id)
        ).scalar_one_or_none()
    assert record is not None, f"{client_id} is not registered"
    assert record.is_active == (state == "active"), record.is_active


@then('the email to "{to_email}" should have sender name "{name}"')
def step_email_sender_name(context, to_email, name):
    from steps.database_steps import load_email

    assert load_email(to_email=to_email).from_name == name


@then('the email to "{to_email}" should have reply-to "{reply_to}"')
def step_email_reply_to(context, to_email, reply_to):
    from steps.database_steps import load_email

    assert load_email(to_email=to_email).reply_to == reply_to
