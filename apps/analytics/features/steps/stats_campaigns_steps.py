# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the campaign statistics feature."""

from analytics.models import Pixel
from behave import given, then, when
from sqlalchemy import select


def run(context, coroutine):
    """Run a coroutine on the scenario event loop."""
    return context.loop.run_until_complete(coroutine)


def _entry(context, key, value):
    entries = context.response.json()
    matches = [entry for entry in entries if entry[key] == value]
    assert matches, f"No entry with {key}={value!r} in {entries}"
    return matches[0]


@given('the first pixel of the campaign "{name}" is opened {count:d} times')
def step_open_first_pixel(context, name, count):
    async def first_pixel_key():
        async with context.session_maker() as db:
            pixel = (
                (
                    await db.execute(
                        select(Pixel)
                        .where(Pixel.campaign_id == context.campaigns[name].id)
                        .order_by(Pixel.created_at)
                    )
                )
                .scalars()
                .first()
            )
            return pixel.pixel_key

    key = run(context, first_pixel_key())
    for _ in range(count):
        context.execute_steps(f'When I send a GET request to "/p/{key}.gif"')


@given('the campaign link of "{name}" is clicked {count:d} times')
def step_click_link(context, name, count):
    key = context.campaigns[name].tracking_key
    for _ in range(count):
        context.execute_steps(f'When I send a GET request to "/t/{key}"')


@when('I request "{path}" for the campaign "{name}"')
def step_request_for_campaign(context, path, name):
    campaign_id = context.campaigns[name].id
    context.execute_steps(
        f'When I send a GET request to "{path.replace("{id}", str(campaign_id))}"'
    )


@then(
    'the campaign list entry "{name}" should have {pixels:d} pixels, {opens:d} opens '
    "and {clicks:d} clicks"
)
def step_campaign_entry(context, name, pixels, opens, clicks):
    entry = _entry(context, "name", name)
    assert (entry["pixel_count"], entry["total_opens"], entry["click_count"]) == (
        pixels,
        opens,
        clicks,
    ), entry


@then('the campaign list should contain "{name}"')
def step_list_contains(context, name):
    assert _entry(context, "name", name)


@then('the campaign list should not contain "{name}"')
def step_list_not_contains(context, name):
    names = [entry["name"] for entry in context.response.json()]
    assert name not in names, names


@then("the campaign detail should have {days:d} day of clicks with {clicks:d} clicks")
def step_detail_days(context, days, clicks):
    by_day = context.response.json()["clicks_by_day"]
    assert len(by_day) == days, by_day
    assert by_day[0]["sessions"] == clicks, by_day


@then('the pixel list entry "{email}" should have {opens:d} opens')
def step_pixel_entry(context, email, opens):
    assert _entry(context, "recipient_email", email)["open_count"] == opens
