# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for analytics feature scenarios."""

from datetime import UTC, datetime

from behave import given

# --- Dashboard mock setup ---


@given("the analytics overview returns data")
def step_analytics_overview(context):
    context.mock_analytics.get_overview.return_value = {
        "total_sessions": 100,
        "unique_visitors": 80,
        "total_pageviews": 500,
        "total_events": 50,
    }
    context.mock_analytics.get_daily_stats.return_value = []
    context.mock_analytics.get_country_stats.return_value = []
    context.mock_analytics.get_device_stats.return_value = []
    context.mock_analytics.get_browser_stats.return_value = []
    context.mock_analytics.get_referrer_stats.return_value = []
    context.mock_analytics.get_page_stats.return_value = []
    context.mock_analytics.get_event_stats.return_value = []
    context.mock_analytics.get_ip_stats.return_value = []


# --- Campaigns mock setup ---


@given("the campaigns list returns data")
def step_campaigns_list(context):
    context.mock_analytics.get_campaigns.return_value = [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "name": "Test Campaign",
            "tracking_key": "test-campaign",
            "is_active": True,
            "click_count": 42,
            "unique_click_count": 30,
            "pixel_count": 5,
            "total_opens": 1000,
            "created_at": datetime(2024, 1, 1, tzinfo=UTC),
        }
    ]


@given('a campaign exists with id "{campaign_id}"')
def step_campaign_exists(context, campaign_id):
    context.mock_analytics.get_campaign_detail.return_value = {
        "id": campaign_id,
        "name": "Test Campaign",
        "is_active": True,
        "tracking_key": "test-campaign",
        "description": "A test campaign",
        "created_at": datetime(2024, 1, 1, tzinfo=UTC),
        "updated_at": datetime(2024, 1, 15, tzinfo=UTC),
        "destination_url": "https://example.com",
        "click_count": 42,
        "unique_click_count": 30,
        "clicks_by_day": [],
        "clicks_by_country": [],
    }
    context.mock_analytics.get_campaign_pixels.return_value = []


@given("a campaign does not exist")
def step_campaign_not_exists(context):
    context.mock_analytics.get_campaign_detail.return_value = None


@given("deleting a campaign succeeds")
def step_delete_campaign_success(context):
    context.mock_analytics.delete_campaign.return_value = True


@given("deleting a campaign fails")
def step_delete_campaign_failure(context):
    context.mock_analytics.delete_campaign.return_value = False


@given("bulk deleting campaigns succeeds")
def step_bulk_delete_success(context):
    context.mock_analytics.delete_campaigns_bulk.return_value = (2, 0)


# --- IP Stats mock setup ---


@given("the IP stats returns data")
def step_ip_stats(context):
    context.mock_analytics.get_ip_stats.return_value = [
        {
            "ip_address": "192.168.1.1",
            "sessions": 50,
            "pageviews": 120,
            "countries": ["US"],
            "first_seen": datetime(2024, 1, 1, tzinfo=UTC),
            "last_seen": datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
        }
    ]


@given('IP detail exists for "{ip_address}"')
def step_ip_detail_exists(context, ip_address):
    context.mock_analytics.get_ip_detail.return_value = {
        "ip_address": ip_address,
        "first_seen": datetime(2024, 1, 1, tzinfo=UTC),
        "last_seen": datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
        "total_sessions": 50,
        "total_pageviews": 120,
        "total_events": 30,
        "countries": ["US"],
        "cities": ["New York"],
        "browsers": ["Chrome"],
        "device_types": ["Desktop"],
        "operating_systems": ["Windows"],
        "referrers": ["https://google.com"],
        "pages": [{"page_url": "/home", "pageviews": 50}],
        "events": [],
        "sessions_by_day": [],
    }


@given("IP detail does not exist")
def step_ip_detail_not_exists(context):
    context.mock_analytics.get_ip_detail.return_value = None


# --- Reset mock setup ---


@given("resetting analytics succeeds")
def step_reset_success(context):
    context.mock_analytics.reset_all_analytics.return_value = {
        "sessions_deleted": 10,
        "events_deleted": 50,
        "campaigns_deleted": 2,
    }


@given("resetting analytics fails")
def step_reset_failure(context):
    context.mock_analytics.reset_all_analytics.return_value = None
