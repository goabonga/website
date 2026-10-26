# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the traffic statistics feature."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from analytics.auth import jwt_validator
from analytics.models import Event, Session
from behave import given, then
from sqlalchemy import select


def run(context, coroutine):
    """Run a coroutine on the scenario event loop."""
    return context.loop.run_until_complete(coroutine)


def _cell(row, name):
    value = row[name].strip()
    return value or None


@given('I am authenticated with the scopes "{scopes}"')
def step_authenticated(context, scopes):
    async def fake_validate(token):
        return {
            "sub": "00000000-0000-0000-0000-000000000001",
            "email": "admin@example.com",
            "scope": scopes,
        }

    patcher = patch.object(jwt_validator, "validate_token_with_introspection", fake_validate)
    patcher.start()
    context.add_cleanup(patcher.stop)
    context.request_headers["Authorization"] = "Bearer test-token"


@given("the following sessions exist")
def step_sessions(context):
    now = datetime.now(UTC)

    async def seed():
        async with context.session_maker() as db:
            for row in context.table:
                seen = now - timedelta(days=int(row["days_ago"]))
                db.add(
                    Session(
                        session_id=row["session_id"],
                        country=_cell(row, "country"),
                        device_type=_cell(row, "device_type"),
                        browser=_cell(row, "browser"),
                        referrer=_cell(row, "referrer"),
                        ip_address=_cell(row, "ip_address"),
                        first_seen=seen,
                        last_seen=seen,
                    )
                )
            await db.commit()

    run(context, seed())


@given("the following events exist")
def step_events(context):
    now = datetime.now(UTC)

    async def seed():
        async with context.session_maker() as db:
            for row in context.table:
                session = (
                    await db.execute(select(Session).where(Session.session_id == row["session_id"]))
                ).scalar_one()
                db.add(
                    Event(
                        session_id=session.id,
                        event_type=row["event_type"],
                        page_url=_cell(row, "page_url"),
                        timestamp=now - timedelta(days=int(row["days_ago"])),
                    )
                )
            await db.commit()

    run(context, seed())


def _entry(context, key, value):
    entries = context.response.json()
    matches = [entry for entry in entries if entry[key] == value]
    assert matches, f"No entry with {key}={value!r} in {entries}"
    return matches[0]


@then("the latest daily entry should have {sessions:d} session and {pageviews:d} pageviews")
def step_latest_daily(context, sessions, pageviews):
    first = context.response.json()[-1]
    assert (first["sessions"], first["pageviews"]) == (sessions, pageviews), first


@then('the entry "{value}" of "{key}" should have {sessions:d} sessions and {percentage:f} percent')
def step_entry_share(context, value, key, sessions, percentage):
    entry = _entry(context, key, value)
    assert entry["sessions"] == sessions, entry
    assert entry["percentage"] == percentage, entry


@then('the page "{url}" should have {views:d} page views and {unique:d} unique sessions')
def step_page(context, url, views, unique):
    entry = _entry(context, "page_url", url)
    assert (entry["pageviews"], entry["unique_sessions"]) == (views, unique), entry


@then('the event type "{event_type}" should have {count:d} events and {unique:d} unique sessions')
def step_event_type(context, event_type, count, unique):
    entry = _entry(context, "event_type", event_type)
    assert (entry["count"], entry["unique_sessions"]) == (count, unique), entry


@then("the response JSON list should have {count:d} item")
@then("the response JSON list should have {count:d} items")
def step_list_length(context, count):
    items = context.response.json()
    assert isinstance(items, list), f"Expected a list, got {items!r}"
    assert len(items) == count, f"Expected {count} items, got {len(items)}: {items}"
