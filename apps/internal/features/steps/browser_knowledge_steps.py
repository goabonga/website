# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the browser scenarios of the knowledge base."""

from unittest.mock import AsyncMock, MagicMock

from behave import given, then, when
from internal.models.knowledge import KnowledgeEntry


@given("the embedding service is available")
def step_embedding_available(context):
    service = MagicMock()
    service.generate = AsyncMock(return_value=[0.1, 0.2, 0.3])
    context.mock_get_embedding_service.return_value = service
    context.embedding_service = service


@given('{count:d} knowledge entries about "{topic}" exist')
def step_many_entries(context, count, topic):
    async def _create():
        async with context.session_maker() as session:
            for index in range(count):
                session.add(
                    KnowledgeEntry(
                        question=f"{topic} question {index:03d}",
                        answer=f"{topic} answer {index:03d}",
                        namespace_id=getattr(context, "namespace_id", None),
                        metadata_={},
                    )
                )
            await session.commit()

    context.loop.run_until_complete(_create())


@given('the generation task fails with the message "{message}"')
def step_generation_fails(context, message):
    result = MagicMock()
    result.state = "FAILURE"
    result.result = message
    context.mock_celery_async_result.return_value = result


@when("I open the entry I created")
def step_open_entry(context):
    context.page.goto(f"{context.base_url}/knowledge/{context.entry_id}")


@when("I open the edit form of the entry I created")
def step_open_entry_edit(context):
    context.page.goto(f"{context.base_url}/knowledge/{context.entry_id}/edit")


@when("I open the validation of the entry I created")
def step_open_entry_validation(context):
    context.page.goto(f"{context.base_url}/knowledge/{context.entry_id}/validation")


@then("the validation of the entry should have been requested")
def step_validation_requested(context):
    context.mock_validation_task_delay.assert_called()


@then("the generation of knowledge entries should have been requested")
def step_generation_requested(context):
    context.mock_generation_task_delay.assert_called_once()


@then("the generation of knowledge entries should not have been requested")
def step_generation_not_requested(context):
    context.mock_generation_task_delay.assert_not_called()
