# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for email campaigns feature scenarios."""

from behave import given

# --- List campaigns mock ---


@given("the campaigns API returns a list of campaigns")
def step_campaigns_list(context):
    context.mock_mailler_campaigns.get_campaigns.return_value = {
        "items": [
            {
                "id": 1,
                "name": "Newsletter January",
                "status": "draft",
                "template_id": 1,
                "group_id": 1,
                "total_recipients": 100,
                "sent_count": 0,
                "created_at": "2024-01-15T12:00:00Z",
                "updated_at": "2024-01-15T12:00:00Z",
            }
        ],
        "total": 1,
        "pages": 1,
    }


# --- New form mock (templates + groups + providers) ---


@given("the campaigns API returns templates and groups for the form")
def step_campaigns_form_data(context):
    context.mock_mailler_campaigns.get_templates.return_value = {
        "items": [
            {"id": 1, "name": "Welcome Template", "slug": "welcome", "status": "active"},
        ],
    }
    context.mock_mailler_campaigns.get_contact_groups.return_value = {
        "items": [
            {"id": 1, "name": "All Subscribers", "slug": "all-subscribers"},
        ],
    }
    context.mock_mailler_campaigns.get_providers.return_value = ["ses", "smtp"]


# --- Create campaign ---


@given("creating a campaign via API succeeds")
def step_create_campaign_success(context):
    context.mock_mailler_campaigns.create_campaign.return_value = {
        "id": 10,
        "name": "My Campaign",
        "status": "draft",
    }


@given("creating a campaign via API fails")
def step_create_campaign_failure(context):
    context.mock_mailler_campaigns.create_campaign.return_value = None


# --- Campaign detail ---


@given("a campaign exists via API with id {campaign_id:d}")
def step_campaign_exists_api(context, campaign_id):
    campaign_data = {
        "id": campaign_id,
        "name": "Test Campaign",
        "status": "draft",
        "template_id": 1,
        "group_id": 1,
        "total_recipients": 50,
        "sent_count": 0,
        "delivered_count": 0,
        "opened_count": 0,
        "clicked_count": 0,
        "bounced_count": 0,
        "complained_count": 0,
        "failed_count": 0,
        "stats": {
            "total_recipients": 50,
            "sent_count": 0,
            "delivered_count": 0,
            "opened_count": 0,
            "clicked_count": 0,
            "bounced_count": 0,
            "complained_count": 0,
            "failed_count": 0,
            "progress_percent": 0,
            "open_rate": 0,
            "click_rate": 0,
            "bounce_rate": 0,
            "complaint_rate": 0,
        },
        "created_at": "2024-01-15T12:00:00Z",
        "updated_at": "2024-01-15T12:00:00Z",
    }
    context.mock_mailler_campaigns.get_campaign.return_value = campaign_data
    context.mock_mailler_campaigns.get_campaign_sends.return_value = {
        "items": [],
        "total": 0,
    }


@given("a campaign does not exist via API")
def step_campaign_not_exists_api(context):
    context.mock_mailler_campaigns.get_campaign.return_value = None


# --- Draft / Sending / Paused campaign variants ---


@given("a draft campaign exists via API with id {campaign_id:d}")
def step_draft_campaign_api(context, campaign_id):
    campaign_data = {
        "id": campaign_id,
        "name": "Draft Campaign",
        "status": "draft",
        "template_id": 1,
        "group_id": 1,
        "total_recipients": 50,
        "sent_count": 0,
        "stats": {},
        "created_at": "2024-01-15T12:00:00Z",
        "updated_at": "2024-01-15T12:00:00Z",
    }
    context.mock_mailler_campaigns.get_campaign.return_value = campaign_data
    context.mock_mailler_campaigns.get_campaign_sends.return_value = {
        "items": [],
        "total": 0,
    }
    # Also set up form dependencies for edit form
    context.mock_mailler_campaigns.get_templates.return_value = {
        "items": [
            {"id": 1, "name": "Welcome Template", "slug": "welcome", "status": "active"},
        ],
    }
    context.mock_mailler_campaigns.get_contact_groups.return_value = {
        "items": [
            {"id": 1, "name": "All Subscribers", "slug": "all-subscribers"},
        ],
    }
    context.mock_mailler_campaigns.get_providers.return_value = ["ses"]


@given("a sending campaign exists via API with id {campaign_id:d}")
def step_sending_campaign_api(context, campaign_id):
    context.mock_mailler_campaigns.get_campaign.return_value = {
        "id": campaign_id,
        "name": "Sending Campaign",
        "status": "sending",
        "template_id": 1,
        "group_id": 1,
        "total_recipients": 100,
        "sent_count": 50,
        "stats": {},
        "created_at": "2024-01-15T12:00:00Z",
        "updated_at": "2024-01-15T12:00:00Z",
    }
    context.mock_mailler_campaigns.get_campaign_sends.return_value = {
        "items": [],
        "total": 0,
    }


@given("a paused campaign exists via API with id {campaign_id:d}")
def step_paused_campaign_api(context, campaign_id):
    context.mock_mailler_campaigns.get_campaign.return_value = {
        "id": campaign_id,
        "name": "Paused Campaign",
        "status": "paused",
        "template_id": 1,
        "group_id": 1,
        "total_recipients": 100,
        "sent_count": 30,
        "stats": {},
        "created_at": "2024-01-15T12:00:00Z",
        "updated_at": "2024-01-15T12:00:00Z",
    }
    context.mock_mailler_campaigns.get_campaign_sends.return_value = {
        "items": [],
        "total": 0,
    }


# --- Update campaign ---


@given("updating a campaign via API succeeds")
def step_update_campaign_success(context):
    context.mock_mailler_campaigns.update_campaign.return_value = {
        "id": 1,
        "name": "Updated Campaign",
        "status": "draft",
    }


@given("updating a campaign via API fails")
def step_update_campaign_failure(context):
    context.mock_mailler_campaigns.update_campaign.return_value = None


# --- Send / Pause / Resume ---


@given("sending a campaign via API succeeds")
def step_send_campaign_success(context):
    context.mock_mailler_campaigns.send_campaign.return_value = {
        "status": "sending",
        "total_recipients": 50,
    }


@given("pausing a campaign via API succeeds")
def step_pause_campaign_success(context):
    context.mock_mailler_campaigns.pause_campaign.return_value = {
        "status": "paused",
    }


@given("resuming a campaign via API succeeds")
def step_resume_campaign_success(context):
    context.mock_mailler_campaigns.resume_campaign.return_value = {
        "status": "sending",
    }


# --- Delete campaign ---


@given("deleting a campaign via API succeeds")
def step_delete_campaign_success(context):
    context.mock_mailler_campaigns.delete_campaign.return_value = True


# --- Bulk delete ---


@given("bulk delete campaigns via API deletes {count:d} campaigns")
def step_bulk_delete_campaigns(context, count):
    # For bulk delete, the route calls get_campaign then delete_campaign for each ID
    draft_campaign = {
        "id": 1,
        "name": "Campaign",
        "status": "draft",
    }
    context.mock_mailler_campaigns.get_campaign.return_value = draft_campaign
    context.mock_mailler_campaigns.delete_campaign.return_value = True


# --- Stats endpoint ---


@given("a campaign with stats exists via API with id {campaign_id:d}")
def step_campaign_stats_api(context, campaign_id):
    context.mock_mailler_campaigns.get_campaign.return_value = {
        "id": campaign_id,
        "name": "Stats Campaign",
        "status": "sending",
        "stats": {
            "total_recipients": 100,
            "sent_count": 80,
            "delivered_count": 75,
            "opened_count": 30,
            "clicked_count": 10,
            "bounced_count": 3,
            "complained_count": 1,
            "failed_count": 2,
            "progress_percent": 80,
            "open_rate": 40.0,
            "click_rate": 13.3,
            "bounce_rate": 4.0,
            "complaint_rate": 1.3,
        },
    }
