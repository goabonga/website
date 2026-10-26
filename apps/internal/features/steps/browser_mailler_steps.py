# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the browser scenarios of the mailler statistics."""

from behave import given, then


@given("the mailler emails list has {pages:d} pages")
def step_emails_pages(context, pages):
    page_size = 20
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
        "total": pages * page_size,
        "page": 1,
        "page_size": page_size,
        "pages": pages,
    }
    context.mock_mailler_mailler.get_providers.return_value = ["ses", "smtp"]


@then('the mailler service should have been asked for the emails of the provider "{provider}"')
def step_emails_of_provider(context, provider):
    kwargs = context.mock_mailler_mailler.get_emails.await_args.kwargs
    assert kwargs.get("provider") == provider, kwargs
