# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for mailler feature scenarios."""

from behave import given

# --- Dashboard mock setup ---


@given("the mailler stats returns data")
def step_mailler_stats(context):
    context.mock_mailler_mailler.get_stats.return_value = {
        "total": {
            "sent": 100,
            "delivered": 95,
            "bounced": 3,
            "failed": 2,
        },
        "by_date": [
            {
                "date": "2024-01-14",
                "sent": 50,
                "delivered": 48,
                "bounced": 1,
                "failed": 1,
            },
            {
                "date": "2024-01-15",
                "sent": 50,
                "delivered": 47,
                "bounced": 2,
                "failed": 1,
            },
        ],
        "by_provider": {
            "ses": {
                "sent": 80,
                "delivered": 76,
                "bounced": 2,
                "failed": 2,
            },
            "smtp": {
                "sent": 20,
                "delivered": 19,
                "bounced": 1,
                "failed": 0,
            },
        },
    }
    context.mock_mailler_mailler.get_providers.return_value = [
        "ses",
        "smtp",
    ]


# --- Emails list mock setup ---


@given("the mailler emails list returns data")
def step_mailler_emails_list(context):
    context.mock_mailler_mailler.get_emails.return_value = {
        "items": [
            {
                "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "to_email": "user@example.com",
                "subject": "Test Email",
                "status": "delivered",
                "provider": "ses",
                "created_at": "2024-01-15T12:00:00Z",
                "sent_at": "2024-01-15T12:00:03Z",
                "scheduled_at": None,
            }
        ],
        "total": 1,
        "page": 1,
        "page_size": 20,
        "pages": 1,
    }
    context.mock_mailler_mailler.get_providers.return_value = [
        "ses",
        "smtp",
    ]


# --- Email detail mock setup ---


@given('an email exists with id "{email_id}"')
def step_email_exists(context, email_id):
    context.mock_mailler_mailler.get_email.return_value = {
        "id": email_id,
        "to_email": "user@example.com",
        "to_name": "Test User",
        "from_email": "noreply@example.com",
        "from_name": "Example App",
        "reply_to": "support@example.com",
        "subject": "Test Email",
        "status": "delivered",
        "provider": "ses",
        "provider_message_id": "ses-msg-001",
        "retry_count": 0,
        "task_id": "celery-task-abc-123",
        "html_content": "<p>Hello</p>",
        "text_content": "Hello",
        "created_at": "2024-01-15T12:00:00Z",
        "scheduled_at": None,
        "queued_at": "2024-01-15T12:00:01Z",
        "sent_at": "2024-01-15T12:00:03Z",
        "delivered_at": "2024-01-15T12:00:05Z",
        "bounced_at": None,
        "failed_at": None,
        "error_message": None,
        "client_id": "client-001",
        "user_id": "user-001",
        "metadata": {"template": "welcome", "campaign": "onboarding"},
    }


@given("an email does not exist")
def step_email_not_exists(context):
    context.mock_mailler_mailler.get_email.return_value = None
