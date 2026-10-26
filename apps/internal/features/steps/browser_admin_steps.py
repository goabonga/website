# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the browser scenarios of the admin dashboard and the chat history."""

from behave import given, when


@given("the dashboard analytics are available")
def step_dashboard_analytics(context):
    context.mock_analytics_admin.get_overview.return_value = {
        "total_sessions": 321,
        "unique_visitors": 123,
        "total_pageviews": 456,
        "total_events": 78,
    }


@when("I open the conversation I created")
def step_open_conversation(context):
    context.page.goto(f"{context.base_url}/conversations/{context.conversation_id}")


@given('{count:d} conversations exist titled "{prefix}"')
def step_many_conversations(context, count, prefix):
    import uuid
    from datetime import UTC, datetime, timedelta

    from internal.models.conversation import Conversation

    async def _create():
        async with context.session_maker() as session:
            now = datetime.now(UTC)
            for index in range(count):
                session.add(
                    Conversation(
                        id=uuid.uuid4(),
                        session_id=f"{prefix}-{index:03d}",
                        title=f"{prefix} {index:03d}",
                        updated_at=now - timedelta(minutes=index),
                    )
                )
            await session.commit()

    context.loop.run_until_complete(_create())
