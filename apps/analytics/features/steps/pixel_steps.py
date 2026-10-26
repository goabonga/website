# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the pixel feature."""

from analytics.models import Campaign, Pixel, PixelOpen
from analytics.services.collector import collector_service
from behave import given, then, when
from sqlalchemy import func, select


def run(context, coroutine):
    """Run a coroutine on the scenario event loop."""
    return context.loop.run_until_complete(coroutine)


async def _count(context, model):
    async with context.session_maker() as db:
        return (await db.execute(select(func.count()).select_from(model))).scalar_one()


async def _pixel(context):
    async with context.session_maker() as db:
        return (
            await db.execute(select(Pixel).where(Pixel.pixel_key == context.pixel_key))
        ).scalar_one()


@given('a campaign "{name}"')
def step_campaign(context, name):
    async def create():
        async with context.session_maker() as db:
            return await collector_service.create_campaign(db=db, name=name)

    campaign = run(context, create())
    context.campaigns = getattr(context, "campaigns", {})
    context.campaigns[name] = campaign


@then("the campaigns should have different tracking keys")
def step_distinct_keys(context):
    keys = [campaign.tracking_key for campaign in context.campaigns.values()]
    assert len(keys) == len(set(keys)) >= 2, keys


@given('a pixel for the campaign "{name}" and recipient "{email}"')
def step_pixel(context, name, email):
    campaign_id = context.campaigns[name].id

    async def create():
        async with context.session_maker() as db:
            return await collector_service.create_pixel(
                db=db, campaign_id=campaign_id, recipient_email=email
            )

    context.pixel_key = run(context, create()).pixel_key


@when("I send a GET request to the pixel URL")
def step_get_pixel(context):
    context.execute_steps(f'When I send a GET request to "/p/{context.pixel_key}.gif"')


@when("I send a GET request to the pixel URL without extension")
def step_get_pixel_no_extension(context):
    context.execute_steps(f'When I send a GET request to "/p/{context.pixel_key}"')


@when('I delete the campaign "{name}"')
def step_delete_campaign(context, name):
    campaign_id = context.campaigns[name].id

    async def delete():
        async with context.session_maker() as db:
            campaign = await db.get(Campaign, campaign_id)
            await db.delete(campaign)
            await db.commit()

    run(context, delete())


@then("the pixel should have been opened {count:d} time")
@then("the pixel should have been opened {count:d} times")
def step_open_count(context, count):
    pixel = run(context, _pixel(context))
    assert pixel.open_count == count, pixel.open_count


@then("the pixel first and last opened timestamps should be set")
def step_open_timestamps(context):
    pixel = run(context, _pixel(context))
    assert pixel.first_opened_at is not None
    assert pixel.last_opened_at is not None


@then("the database should contain {count:d} pixel open")
@then("the database should contain {count:d} pixel opens")
def step_count_opens(context, count):
    actual = run(context, _count(context, PixelOpen))
    assert actual == count, f"Expected {count} pixel opens, got {actual}"


@then("the database should contain {count:d} pixel")
@then("the database should contain {count:d} pixels")
def step_count_pixels(context, count):
    actual = run(context, _count(context, Pixel))
    assert actual == count, f"Expected {count} pixels, got {actual}"


@then("the database should contain {count:d} campaign")
@then("the database should contain {count:d} campaigns")
def step_count_campaigns(context, count):
    actual = run(context, _count(context, Campaign))
    assert actual == count, f"Expected {count} campaigns, got {actual}"


@then('the last pixel open should have user agent "{user_agent}" and IP address "{ip_address}"')
def step_last_open(context, user_agent, ip_address):
    async def last_open():
        async with context.session_maker() as db:
            return (
                (await db.execute(select(PixelOpen).order_by(PixelOpen.opened_at.desc())))
                .scalars()
                .first()
            )

    pixel_open = run(context, last_open())
    assert (pixel_open.user_agent, pixel_open.ip_address) == (user_agent, ip_address)
