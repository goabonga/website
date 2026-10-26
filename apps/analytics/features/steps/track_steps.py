# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the campaign link feature."""

from analytics.models import Campaign, CampaignClick
from analytics.services.collector import collector_service
from behave import given, then, when
from sqlalchemy import func, select


def run(context, coroutine):
    """Run a coroutine on the scenario event loop."""
    return context.loop.run_until_complete(coroutine)


async def _count(context, model):
    async with context.session_maker() as db:
        return (await db.execute(select(func.count()).select_from(model))).scalar_one()


async def _campaign(context, name):
    campaign_id = context.campaigns[name].id
    async with context.session_maker() as db:
        return await db.get(Campaign, campaign_id)


@given('a redirecting campaign "{name}" with destination "{destination}"')
def step_campaign_with_destination(context, name, destination):
    async def create():
        async with context.session_maker() as db:
            return await collector_service.create_campaign(
                db=db, name=name, destination_url=destination
            )

    context.campaigns = getattr(context, "campaigns", {})
    context.campaigns[name] = run(context, create())
    context.tracking_key = context.campaigns[name].tracking_key


@given('the campaign "{name}" is inactive')
def step_campaign_inactive(context, name):
    async def deactivate():
        async with context.session_maker() as db:
            campaign = await db.get(Campaign, context.campaigns[name].id)
            campaign.is_active = False
            await db.commit()

    run(context, deactivate())


@when("I send a GET request to the campaign link")
def step_get_link(context):
    context.execute_steps(f'When I send a GET request to "/t/{context.tracking_key}"')


@when('I send a GET request to the campaign link with query "{query}"')
def step_get_link_with_query(context, query):
    context.execute_steps(f'When I send a GET request to "/t/{context.tracking_key}?{query}"')


@then("the response should be a redirect")
def step_is_redirect(context):
    assert context.response.status_code == 302, context.response.status_code
    assert "location" in context.response.headers


@then('the redirect location should start with "{prefix}"')
def step_location_prefix(context, prefix):
    location = context.response.headers.get("location", "")
    assert location.startswith(prefix), f"Expected '{prefix}' at the start of '{location}'"


@then('the redirect location should contain "{text}"')
def step_location_contains(context, text):
    location = context.response.headers.get("location", "")
    assert text in location, f"Expected '{text}' in '{location}'"


@then('the campaign "{name}" should have {count:d} click')
@then('the campaign "{name}" should have {count:d} clicks')
def step_campaign_clicks(context, name, count):
    campaign = run(context, _campaign(context, name))
    assert campaign.click_count == count, campaign.click_count


@then("the database should contain {count:d} campaign click")
@then("the database should contain {count:d} campaign clicks")
def step_count_clicks(context, count):
    actual = run(context, _count(context, CampaignClick))
    assert actual == count, f"Expected {count} campaign clicks, got {actual}"


@then(
    'the last click should have user agent "{user_agent}", referrer "{referrer}" '
    'and IP address "{ip_address}"'
)
def step_last_click(context, user_agent, referrer, ip_address):
    async def last_click():
        async with context.session_maker() as db:
            return (
                (await db.execute(select(CampaignClick).order_by(CampaignClick.clicked_at.desc())))
                .scalars()
                .first()
            )

    click = run(context, last_click())
    assert (click.user_agent, click.referrer, click.ip_address) == (
        user_agent,
        referrer,
        ip_address,
    )
