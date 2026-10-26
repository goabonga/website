# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the browser scenarios of the email campaigns."""

from behave import given, then


@then('the mailler service should have been asked to create the campaign "{name}"')
def step_campaign_created(context, name):
    campaign = context.mock_mailler_campaigns.create_campaign.await_args.args[0]
    assert campaign["name"] == name, campaign
    context.created_campaign = campaign


@then('the created campaign should be sent through the provider "{provider}"')
def step_campaign_provider(context, provider):
    assert context.created_campaign["provider"] == provider, context.created_campaign


@then("the mailler service should not have been asked to create a campaign")
def step_no_campaign_created(context):
    context.mock_mailler_campaigns.create_campaign.assert_not_awaited()


@then("the mailler service should not have been asked to delete a campaign")
def step_no_campaign_deleted(context):
    context.mock_mailler_campaigns.delete_campaign.assert_not_awaited()


@then("the mailler service should not have started the campaign")
def step_no_campaign_started(context):
    context.mock_mailler_campaigns.send_campaign.assert_not_awaited()


@given('a "{status}" campaign with {sent:d} emails sent exists via API with id {campaign_id:d}')
def step_campaign_with_status(context, status, sent, campaign_id):
    counters = {
        "sent_count": sent,
        "delivered_count": sent,
        "opened_count": sent // 2,
        "clicked_count": sent // 4,
        "bounced_count": 0,
        "complained_count": 0,
        "failed_count": 0,
    }
    context.mock_mailler_campaigns.get_campaign.return_value = {
        "id": campaign_id,
        "name": f"{status.capitalize()} Campaign",
        "status": status,
        "template_id": 1,
        "group_id": 1,
        "total_recipients": 100,
        **counters,
        "stats": {"total_recipients": 100, **counters, "progress_percent": sent},
        "created_at": "2024-01-15T12:00:00Z",
        "updated_at": "2024-01-15T12:00:00Z",
    }
    context.mock_mailler_campaigns.get_campaign_sends.return_value = {"items": [], "total": 0}
