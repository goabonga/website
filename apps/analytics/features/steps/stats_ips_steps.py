# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the per-IP statistics feature."""

from behave import then


def _ip_entry(context, ip_address):
    entries = context.response.json()
    matches = [entry for entry in entries if entry["ip_address"] == ip_address]
    assert matches, f"No entry for {ip_address} in {entries}"
    return matches[0]


def _names(text):
    return {name.strip() for name in text.split(",")}


@then(
    'the first IP entry should be "{ip_address}" with {sessions:d} sessions and {views:d} page views'
)
def step_first_ip(context, ip_address, sessions, views):
    first = context.response.json()[0]
    assert first["ip_address"] == ip_address, first
    assert (first["sessions"], first["pageviews"]) == (sessions, views), first


@then('the IP entry "{ip_address}" should list the countries "{countries}"')
def step_ip_countries(context, ip_address, countries):
    assert set(_ip_entry(context, ip_address)["countries"]) == _names(countries)


@then('the IP entry "{ip_address}" should list the browsers "{browsers}"')
def step_ip_browsers(context, ip_address, browsers):
    assert set(_ip_entry(context, ip_address)["browsers"]) == _names(browsers)


@then('the IP detail should list the device types "{device_types}"')
def step_detail_devices(context, device_types):
    assert set(context.response.json()["device_types"]) == _names(device_types)


@then("the IP detail should have {count:d} days of sessions")
def step_detail_days(context, count):
    assert len(context.response.json()["sessions_by_day"]) == count


@then('the IP detail page "{url}" should have {views:d} page views')
def step_detail_page(context, url, views):
    pages = {page["page_url"]: page["pageviews"] for page in context.response.json()["pages"]}
    assert pages.get(url) == views, pages


@then('the IP detail event "{event_type}" should have a count of {count:d}')
def step_detail_event(context, event_type, count):
    events = {event["event_type"]: event["count"] for event in context.response.json()["events"]}
    assert events.get(event_type) == count, events
