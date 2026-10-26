# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the storage feature."""

import json

from analytics.database import get_async_database_url
from analytics.models import Event, Session
from behave import given, then, when
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError


def run(context, coroutine):
    """Run a coroutine on the scenario event loop."""
    return context.loop.run_until_complete(coroutine)


async def _add(context, instance):
    async with context.session_maker() as db:
        db.add(instance)
        await db.commit()


async def _count(context, model):
    async with context.session_maker() as db:
        return (await db.execute(select(func.count()).select_from(model))).scalar_one()


async def _get_session(context, session_id):
    async with context.session_maker() as db:
        return (
            await db.execute(select(Session).where(Session.session_id == session_id))
        ).scalar_one()


@given('a stored session "{session_id}"')
def step_stored_session(context, session_id):
    run(context, _add(context, Session(session_id=session_id)))


@when('I try to store another session "{session_id}"')
def step_store_duplicate(context, session_id):
    context.integrity_error = None
    try:
        run(context, _add(context, Session(session_id=session_id)))
    except IntegrityError as exc:
        context.integrity_error = exc


@given('the session "{session_id}" has an event "{event_type}"')
def step_session_event(context, session_id, event_type):
    session = run(context, _get_session(context, session_id))
    run(context, _add(context, Event(session_id=session.id, event_type=event_type)))


@given('the session "{session_id}" has an event "{event_type}" with data {data}')
def step_session_event_with_data(context, session_id, event_type, data):
    session = run(context, _get_session(context, session_id))
    event = Event(session_id=session.id, event_type=event_type, event_data=json.loads(data))
    run(context, _add(context, event))


@when('I delete the session "{session_id}"')
def step_delete_session(context, session_id):
    async def delete():
        async with context.session_maker() as db:
            session = (
                await db.execute(select(Session).where(Session.session_id == session_id))
            ).scalar_one()
            await db.delete(session)
            await db.commit()

    run(context, delete())


@then("the database should contain {count:d} session")
@then("the database should contain {count:d} sessions")
def step_count_sessions(context, count):
    actual = run(context, _count(context, Session))
    assert actual == count, f"Expected {count} sessions, got {actual}"


@then("the database should contain {count:d} event")
@then("the database should contain {count:d} events")
def step_count_events(context, count):
    actual = run(context, _count(context, Event))
    assert actual == count, f"Expected {count} events, got {actual}"


@then('the stored session "{session_id}" should have first and last seen timestamps')
def step_session_timestamps(context, session_id):
    session = run(context, _get_session(context, session_id))
    assert session.first_seen is not None
    assert session.last_seen is not None


@then("the database should reject the duplicate session")
def step_rejected(context):
    assert context.integrity_error is not None, "Duplicate session was accepted"


@then('the session "{session_id}" should have {count:d} events')
def step_session_event_count(context, session_id, count):
    async def count_events():
        session = await _get_session(context, session_id)
        async with context.session_maker() as db:
            return (
                await db.execute(
                    select(func.count()).select_from(Event).where(Event.session_id == session.id)
                )
            ).scalar_one()

    actual = run(context, count_events())
    assert actual == count, f"Expected {count} events, got {actual}"


@then('the first event of session "{session_id}" should have data key "{key}" equal to "{value}"')
def step_event_data(context, session_id, key, value):
    async def first_event():
        session = await _get_session(context, session_id)
        async with context.session_maker() as db:
            return (
                (await db.execute(select(Event).where(Event.session_id == session.id)))
                .scalars()
                .first()
            )

    event = run(context, first_event())
    assert event.event_data[key] == value, f"Got {event.event_data!r}"


@then('the database URL "{url}" should become "{async_url}"')
def step_url(context, url, async_url):
    assert get_async_database_url(url) == async_url
