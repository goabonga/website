# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the data migrations: the GOABONGA team, its agents, their tools and their skills."""

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest
import team.services.tools  # noqa: F401 - registers the tools
from team.schemas.skill import SkillCreate
from team.services.tool_service import ToolService

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
TEAM_ID = "11111111-1111-1111-1111-111111111111"


def load(filename: str):
    spec = importlib.util.spec_from_file_location(filename[:-3], VERSIONS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeBind:
    """Records the statements and answers the lookups of the skills migration."""

    def __init__(self, roles=(), team=True):
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


def run(module, direction: str, bind: FakeBind):
    with patch("alembic.op.get_bind", return_value=bind):
        getattr(module, direction)()


@pytest.fixture(scope="module")
def seed_team():
    return load("0008_seed_goabonga_team.py")


@pytest.fixture(scope="module")
def seed_skills():
    return load("0012_seed_goabonga_skills.py")


class TestRevisionChain:
    def test_seed_revisions_follow_the_schema(self):
        expected = [
            ("0008", "0007"),
            ("0009", "0008"),
            ("0010", "0009"),
            ("0011", "0010"),
            ("0012", "0011"),
        ]
        files = sorted(p.name for p in VERSIONS.glob("00??_*.py"))[7:]
        assert len(files) == len(expected)
        for filename, (revision, down) in zip(files, expected, strict=True):
            module = load(filename)
            assert (module.revision, module.down_revision) == (revision, down)


class TestSeedTeam:
    def test_creates_the_team_and_its_agents(self, seed_team):
        bind = FakeBind()
        run(seed_team, "upgrade", bind)

        teams = bind.inserts("teams")
        assert len(teams) == 1
        assert teams[0]["slug"] == "goabonga"
        assert json.loads(teams[0]["config"]) == {
            "orchestration": {"enabled": True, "schedule_minutes": 15}
        }
        agents = bind.inserts("agents")
        assert len(agents) == len(seed_team.AGENTS) == 19
        assert all(a["team_id"] == teams[0]["id"] for a in agents)

    def test_roles_are_unique_and_include_the_orchestrator(self, seed_team):
        roles = [a["role"] for a in seed_team.AGENTS]
        assert len(set(roles)) == len(roles)
        assert "ceo" in roles

    def test_providers_and_models(self, seed_team):
        for agent in seed_team.AGENTS:
            assert agent["provider"] in {"openai", "anthropic"}
            assert agent["model"].startswith(("gpt-", "claude-"))

    def test_every_seeded_tool_is_registered(self, seed_team):
        for agent in seed_team.AGENTS:
            for tool in agent["config"]["tools"]:
                assert tool in ToolService._registry, (agent["role"], tool)

    def test_downgrade_deletes_the_agents_then_the_team(self, seed_team):
        bind = FakeBind()
        run(seed_team, "downgrade", bind)
        deletes = [s for s, _ in bind.statements if s.startswith("DELETE")]
        assert deletes == [
            "DELETE FROM agents WHERE team_id = :team_id",
            "DELETE FROM teams WHERE id = :id",
        ]

    def test_downgrade_without_team_does_nothing(self, seed_team):
        bind = FakeBind(team=False)
        run(seed_team, "downgrade", bind)
        assert [s for s, _ in bind.statements if s.startswith("DELETE")] == []


class TestToolMigrations:
    def test_save_memory_is_added_and_removed(self):
        module = load("0009_add_save_memory_tool.py")
        statements: list[str] = []
        with patch("alembic.op.execute", side_effect=lambda s: statements.append(str(s))):
            module.upgrade()
            module.downgrade()
        assert "save_memory" in statements[0] and "||" in statements[0]
        assert "save_memory" in statements[1] and "- 'save_memory'" in statements[1]
        assert "save_memory" in ToolService._registry

    @pytest.mark.parametrize(
        ("filename", "pairs"),
        [("0010_add_github_crud_tools.py", 10), ("0011_add_memory_crud_tools.py", 2)],
    )
    def test_new_tools_are_registered_and_follow_their_origin(self, filename, pairs):
        module = load(filename)
        assert len(module._TOOL_PAIRS) == pairs
        for existing, new in module._TOOL_PAIRS:
            assert existing in ToolService._registry
            assert new in ToolService._registry

    @pytest.mark.parametrize(
        "filename", ["0010_add_github_crud_tools.py", "0011_add_memory_crud_tools.py"]
    )
    def test_one_statement_per_pair_in_both_directions(self, filename):
        module = load(filename)
        statements: list = []
        with patch("alembic.op.execute", side_effect=statements.append):
            module.upgrade()
            assert len(statements) == len(module._TOOL_PAIRS)
            module.downgrade()
            assert len(statements) == 2 * len(module._TOOL_PAIRS)


class TestSeedSkills:
    def test_every_role_gets_its_skills(self, seed_team, seed_skills):
        roles = [a["role"] for a in seed_team.AGENTS]
        bind = FakeBind(roles=roles)
        run(seed_skills, "upgrade", bind)

        expected = sum(len(skills) for skills in seed_skills.AGENT_SKILLS.values())
        assert len(bind.inserts("skills")) == expected
        assert set(seed_skills.AGENT_SKILLS) == set(roles)

    def test_skills_are_valid_agent_skills(self, seed_skills):
        for role, skills in seed_skills.AGENT_SKILLS.items():
            names = [s["name"] for s in skills]
            assert len(set(names)) == len(names), role
            for skill in skills:
                SkillCreate(
                    name=skill["name"],
                    description=skill["description"],
                    content=skill["content"],
                    allowed_tools=skill.get("allowed_tools", []),
                )

    def test_missing_team_or_agent_is_skipped(self, seed_skills):
        no_team = FakeBind(team=False)
        run(seed_skills, "upgrade", no_team)
        assert no_team.inserts("skills") == []

        only_cto = FakeBind(roles=["cto"])
        run(seed_skills, "upgrade", only_cto)
        assert len(only_cto.inserts("skills")) == len(seed_skills.AGENT_SKILLS["cto"])

    def test_downgrade_deletes_the_skills_of_the_team(self, seed_skills):
        bind = FakeBind()
        run(seed_skills, "downgrade", bind)
        assert bind.statements[-1][0] == "DELETE FROM skills WHERE team_id = :team_id"
        assert bind.statements[-1][1] == {"team_id": TEAM_ID}
