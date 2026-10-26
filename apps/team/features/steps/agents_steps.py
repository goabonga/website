# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the agents feature: the database and the agent service."""

from uuid import UUID

from behave import step, then
from sqlalchemy import func, select
from team.models import Agent
from team.services import AgentService


def _count_agents(context, *conditions) -> int:
    async def count() -> int:
        async with context.session_factory() as session:
            result = await session.execute(select(func.count(Agent.id)).where(*conditions))
            return result.scalar_one()

    return context.run(count)


@then("{count:d} agents belong to the team in the database")
def step_agents_of_team(context, count: int) -> None:
    assert _count_agents(context, Agent.team_id == UUID(context.vars["team_id"])) == count


@then("{count:d} agents without a team remain in the database")
def step_agents_without_team(context, count: int) -> None:
    assert _count_agents(context, Agent.team_id.is_(None)) == count


@step("the agent service lists the active agents of the team")
def step_service_active(context) -> None:
    async def active() -> list[str]:
        async with context.session_factory() as session:
            agents = await AgentService(session).get_active_agents(UUID(context.vars["team_id"]))
            return sorted(agent.name for agent in agents)

    context.service_result = context.run(active)


@step('the agent service looks up the role "{role}" in the team')
def step_service_role(context, role: str) -> None:
    async def lookup() -> str | None:
        async with context.session_factory() as session:
            agent = await AgentService(session).get_agent_by_role(
                UUID(context.vars["team_id"]), role
            )
            return agent.name if agent else None

    context.service_result = context.run(lookup)


@then('the service returned the agents "{names}"')
def step_service_names(context, names: str) -> None:
    assert context.service_result == sorted(n.strip() for n in names.split(",")), (
        context.service_result
    )


@then("the service found no agent")
def step_service_none(context) -> None:
    assert context.service_result is None


@then('the service found the agent "{name}"')
def step_service_found(context, name: str) -> None:
    assert context.service_result == name, context.service_result
