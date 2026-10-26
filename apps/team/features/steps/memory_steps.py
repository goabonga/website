# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the memory feature: a fake embedding model and the memory service."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

from behave import given, step, then
from sqlalchemy import select
from team.models import MemoryEntry
from team.services import MemoryService
from team.services.embeddings import EMBEDDING_DIMENSIONS, generate_embedding


@given("embeddings are computed by a fake model")
def step_fake_embeddings(context) -> None:
    """The fake embedding of a text is [length of the text, 0.0, 0.0]."""
    context.embedded = []

    async def embed(text: str) -> list[float]:
        context.embedded.append(text)
        return [float(len(text)), 0.0, 0.0]

    patcher = patch("team.routes.team.memory.generate_embedding", AsyncMock(side_effect=embed))
    patcher.start()
    context.add_cleanup(patcher.stop)


@then('the embedding model received "{text}"')
def step_received(context, text: str) -> None:
    assert text in context.embedded, context.embedded


@then("the embedding model received {count:d} texts")
def step_received_count(context, count: int) -> None:
    assert len(context.embedded) == count, context.embedded


@then("the stored embedding of the entry starts with {value:f}")
def step_stored_embedding(context, value: float) -> None:
    entry_id = UUID(
        context.vars["entry_id"] if "entry_id" in context.vars else context.response.json()["id"]
    )

    async def load():
        async with context.session_factory() as session:
            result = await session.execute(select(MemoryEntry).where(MemoryEntry.id == entry_id))
            return result.scalar_one().embedding

    assert context.run(load)[0] == value


@given("no OpenAI API key is configured")
def step_no_key(context) -> None:
    patcher = patch("team.services.embeddings.settings", SimpleNamespace(openai_api_key=""))
    patcher.start()
    context.add_cleanup(patcher.stop)


@step('an embedding is generated for "{text}"')
def step_generate(context, text: str) -> None:
    context.embedding = context.run(generate_embedding, text)


@then("the embedding has {dimensions:d} dimensions and only zeros")
def step_zero_vector(context, dimensions: int) -> None:
    assert dimensions == EMBEDDING_DIMENSIONS
    assert len(context.embedding) == dimensions and set(context.embedding) == {0.0}


@step("the memory service lists the recent entries of the team")
def step_service_team(context) -> None:
    async def recent() -> int:
        async with context.session_factory() as session:
            entries = await MemoryService(session).get_recent_entries(UUID(context.vars["team_id"]))
            return len(entries)

    context.service_result = context.run(recent)


@step("the memory service lists the entries of the agent")
def step_service_agent(context) -> None:
    async def of_agent() -> int:
        async with context.session_factory() as session:
            entries = await MemoryService(session).get_agent_memory(UUID(context.vars["agent_id"]))
            return len(entries)

    context.service_result = context.run(of_agent)


@then("the service returned {count:d} entries")
def step_service_count(context, count: int) -> None:
    assert context.service_result == count, context.service_result
