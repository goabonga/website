# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the conversations feature: direct access to the database."""

from uuid import UUID

from behave import given, then
from sqlalchemy import func, select
from team.models import Conversation, ConversationParticipant, Message


def _count(context, model, *conditions) -> int:
    async def count() -> int:
        async with context.session_factory() as session:
            result = await session.execute(select(func.count(model.id)).where(*conditions))
            return result.scalar_one()

    return context.run(count)


@given('a conversation "{slug}" belongs to the team')
def step_team_conversation(context, slug: str) -> None:
    async def insert() -> None:
        async with context.session_factory() as session:
            session.add(
                Conversation(
                    slug=slug,
                    title=slug,
                    type="task",
                    team_id=UUID(context.vars["team_id"]),
                )
            )
            await session.commit()

    context.run(insert)


@then("the conversation has {count:d} participants in the database")
def step_participants(context, count: int) -> None:
    conversation_id = UUID(context.vars["conversation_id"])
    assert (
        _count(
            context,
            ConversationParticipant,
            ConversationParticipant.conversation_id == conversation_id,
        )
        == count
    )


@then("the database has {count:d} messages")
def step_messages(context, count: int) -> None:
    assert _count(context, Message) == count
