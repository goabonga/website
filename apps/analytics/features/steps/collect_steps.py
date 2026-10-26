# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the event collection feature."""

from analytics.config import settings
from analytics.models import Event, Session
from behave import given, then, when
from sqlalchemy import select


def run(context, coroutine):
    """Run a coroutine on the scenario event loop."""
    return context.loop.run_until_complete(coroutine)


async def _first(context, model):
    async with context.session_maker() as db:
        return (await db.execute(select(model))).scalars().first()


def _session_cookie(context):
    header = context.response.headers.get("set-cookie", "")
    return header if header.startswith(f"{settings.session_cookie_name}=") else None


@given('the request header "{name}" is "{value}"')
def step_request_header(context, name, value):
    context.request_headers[name] = value


@given("IP anonymization is enabled")
def step_anonymize_ip(context):
    previous = settings.anonymize_ip
    settings.anonymize_ip = True
    context.add_cleanup(setattr, settings, "anonymize_ip", previous)


@given("a first visit has been collected")
def step_first_visit(context):
    send_first = {"events": [{"event_type": "pageview"}]}
    from httpx import ASGITransport, AsyncClient

    async def visit():
        async with AsyncClient(
            transport=ASGITransport(app=context.app), base_url="http://test"
        ) as c:
            return await c.post("/collect", json=send_first)

    context.first_visit = run(context, visit())
    assert context.first_visit.status_code == 200, context.first_visit.text


@when("the visitor comes back with its session cookie")
def step_returning_visitor(context):
    session_id = context.first_visit.json()["session_id"]
    context.request_headers["Cookie"] = f"{settings.session_cookie_name}={session_id}"


@then('the response should set the session cookie "{name}"')
def step_sets_cookie(context, name):
    assert name == settings.session_cookie_name
    assert _session_cookie(context), context.response.headers.get("set-cookie")


@then("the session cookie should be HttpOnly")
def step_cookie_httponly(context):
    assert "httponly" in context.response.headers["set-cookie"].lower()


@then("the response should not set a session cookie")
def step_no_cookie(context):
    assert "set-cookie" not in context.response.headers


@then('the stored event should have type "{event_type}" and page URL "{url}"')
def step_event_type_url(context, event_type, url):
    event = run(context, _first(context, Event))
    assert (event.event_type, event.page_url) == (event_type, url), event


@then('the stored event should have data key "{key}" equal to "{value}"')
def step_event_data(context, key, value):
    event = run(context, _first(context, Event))
    assert event.event_data[key] == value, event.event_data


@then('the stored session should have device type "{device_type}" and browser "{browser}"')
def step_session_device(context, device_type, browser):
    session = run(context, _first(context, Session))
    assert (session.device_type, session.browser) == (device_type, browser), session.user_agent


@then('the stored session should have IP address "{ip_address}"')
def step_session_ip(context, ip_address):
    session = run(context, _first(context, Session))
    assert session.ip_address == ip_address, session.ip_address


@then('the stored session should have UTM source "{source}" and campaign "{campaign}"')
def step_session_utm(context, source, campaign):
    session = run(context, _first(context, Session))
    assert (session.utm_source, session.utm_campaign) == (source, campaign)
