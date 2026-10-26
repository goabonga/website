# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions to run the campaign tasks."""

from behave import given, when
from mailler.database import get_sync_db
from mailler.models import EmailCampaign
from mailler.tasks import scheduler
from mailler.tasks.send import send_campaign_task


@when('the campaign task runs for "{alias}"')
def step_run_campaign_task(context, alias):
    context.task_result = send_campaign_task(int(context.created_ids[alias]))


@given('the campaign "{alias}" is scheduled in the past')
def step_campaign_due(context, alias):
    """Move the scheduled time of a scheduled campaign back so it is due."""
    from datetime import UTC, datetime, timedelta

    with get_sync_db() as db:
        campaign = db.get(EmailCampaign, int(context.created_ids[alias]))
        campaign.scheduled_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()


@when("the scheduler starts the due campaigns")
def step_start_due_campaigns(context):
    context.task_result = scheduler.check_scheduled_campaigns()
