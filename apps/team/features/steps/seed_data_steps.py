# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the seed data: the data migrations run against a recording connection."""

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import team
import team.services.tools  # noqa: F401 - registers the tools
from behave import given, step, then, when
from team.models import Agent, Team
from team.schemas.skill import SkillCreate
from team.services import ToolService

VERSIONS = Path(team.__file__).resolve().parents[2] / "alembic" / "versions"
TEAM_ID = "11111111-1111-1111-1111-111111111111"


class FakeResult:
    def __init__(self, row) -> None:
        self.row = row

    def fetchone(self):
        return self.row


class FakeBind:
    """Records the statements of a migration and answers its lookups."""

    def __init__(self, roles=(), team: bool = True) -> None:
        self.roles = set(roles)
        self.team = team
        self.statements: list[tuple[str, dict]] = []

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.statements.append((sql, params or {}))
        if sql.startswith("SELECT id FROM teams"):
            return FakeResult((TEAM_ID,) if self.team else None)
        if sql.startswith("SELECT id FROM agents"):
            role = params["role"]
            return FakeResult((f"agent-{role}",) if role in self.roles else None)
        return FakeResult(None)

    def inserts(self, table: str) -> list[dict]:
        return [p for s, p in self.statements if s.startswith(f"INSERT INTO {table}")]


def _load(filename: str):
    spec = importlib.util.spec_from_file_location(filename[:-3], VERSIONS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(context, filename: str, direction: str, bind: FakeBind) -> None:
    context.migration = _load(filename)
    context.bind = bind
    with patch("alembic.op.get_bind", return_value=bind):
        getattr(context.migration, direction)()


@step('the seed migration "{filename}" is applied')
def step_apply(context, filename: str) -> None:
    _run(context, filename, "upgrade", FakeBind())


@when('the seed migration "{filename}" is applied for every role')
def step_apply_all_roles(context, filename: str) -> None:
    roles = [a["role"] for a in _load("0008_seed_goabonga_team.py").AGENTS]
    _run(context, filename, "upgrade", FakeBind(roles=roles))


@when('the seed migration "{filename}" is applied without a team')
def step_apply_no_team(context, filename: str) -> None:
    _run(context, filename, "upgrade", FakeBind(team=False))


@when('the seed migration "{filename}" is reverted')
def step_revert(context, filename: str) -> None:
    _run(context, filename, "downgrade", FakeBind())


@then(
    'the seed inserted the team "{slug}" with the orchestration enabled every {minutes:d} minutes'
)
def step_team(context, slug: str, minutes: int) -> None:
    teams = context.bind.inserts("teams")
    assert len(teams) == 1 and teams[0]["slug"] == slug
    assert json.loads(teams[0]["config"]) == {
        "orchestration": {"enabled": True, "schedule_minutes": minutes}
    }


@then("the seed inserted {count:d} agents with different roles")
def step_agents(context, count: int) -> None:
    agents = context.bind.inserts("agents")
    assert len(agents) == count and len({a["role"] for a in agents}) == count


@then('the seeded agents include the roles "{roles}"')
def step_roles(context, roles: str) -> None:
    present = {a["role"] for a in context.bind.inserts("agents")}
    assert {r.strip() for r in roles.split(",")} <= present


@then('the seeded agents use the providers "{providers}"')
def step_providers(context, providers: str) -> None:
    used = {a["provider"] for a in context.bind.inserts("agents")}
    assert used == {p.strip() for p in providers.split(",")}


@then("every tool of the seeded agents is registered")
def step_tools_registered(context) -> None:
    for agent in context.bind.inserts("agents"):
        for tool in json.loads(agent["config"])["tools"]:
            assert tool in ToolService._registry, (agent["role"], tool)


@then('every tool pair of "{filename}" is registered')
def step_pairs(context, filename: str) -> None:
    for existing, new in _load(filename)._TOOL_PAIRS:
        assert existing in ToolService._registry and new in ToolService._registry


@given("the seeded team and agents are loaded in the database")
def step_load_seed(context) -> None:
    team_row = context.bind.inserts("teams")[0]
    agent_rows = context.bind.inserts("agents")

    async def load() -> None:
        async with context.session_factory() as session:
            session.add(
                Team(
                    id=UUID(team_row["id"]),
                    name=team_row["name"],
                    slug=team_row["slug"],
                    description=team_row["description"],
                    config=json.loads(team_row["config"]),
                )
            )
            for row in agent_rows:
                session.add(
                    Agent(
                        team_id=UUID(row["team_id"]),
                        name=row["name"],
                        role=row["role"],
                        description=row["description"],
                        system_prompt=row["system_prompt"],
                        model=row["model"],
                        provider=row["provider"],
                        config=json.loads(row["config"]),
                    )
                )
            await session.commit()

    context.run(load)


@then("the seed inserted skills for all {roles:d} roles with {low:d} or {high:d} skills each")
def step_skills(context, roles: int, low: int, high: int) -> None:
    per_agent: dict[str, int] = {}
    for row in context.bind.inserts("skills"):
        per_agent[row["agent_id"]] = per_agent.get(row["agent_id"], 0) + 1
    assert len(per_agent) == roles
    assert all(low <= count <= high for count in per_agent.values()), per_agent


@then("every seeded skill is a valid agent skill")
def step_skills_valid(context) -> None:
    for row in context.bind.inserts("skills"):
        SkillCreate(
            name=row["name"],
            description=row["description"],
            content=row["content"],
            allowed_tools=json.loads(row["allowed_tools"]),
        )


@then("the seed inserted no skill")
def step_no_skill(context) -> None:
    assert context.bind.inserts("skills") == []


@then("the seed deleted the agents and then the team")
def step_deleted(context) -> None:
    deletes = [s for s, _ in context.bind.statements if s.startswith("DELETE")]
    assert deletes == [
        "DELETE FROM agents WHERE team_id = :team_id",
        "DELETE FROM teams WHERE id = :id",
    ]
