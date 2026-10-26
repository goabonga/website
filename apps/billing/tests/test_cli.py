# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the ``billing-admin`` command, against an in-memory SQLite database."""

import json

import pytest
import pytest_asyncio
from billing import cli
from billing.models import Base, SaasApp, SaasClientBinding
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    """Render PostgreSQL JSONB columns as plain JSON on SQLite."""
    return "JSON"


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


async def _run(factory, *argv):
    return await cli.run(list(argv), session_factory=factory)


async def _rows(factory, model):
    async with factory() as session:
        return list((await session.execute(select(model))).scalars().all())


class TestSaasCommands:
    @pytest.mark.asyncio
    async def test_create_and_list(self, factory):
        created = await _run(
            factory,
            "saas",
            "create",
            "--name",
            "Example App",
            "--slug",
            "example-app",
            "--checkout-url",
            "https://app.example.test/",
        )

        assert created["slug"] == "example-app"
        assert created["checkout_url_allowlist"] == ["https://app.example.test"]
        listed = await _run(factory, "saas", "list")
        assert [row["slug"] for row in listed] == ["example-app"]

    @pytest.mark.asyncio
    async def test_duplicate_slug_is_an_error(self, factory):
        await _run(factory, "saas", "create", "--name", "A", "--slug", "app")

        with pytest.raises(cli.CliError, match="already exists"):
            await _run(factory, "saas", "create", "--name", "B", "--slug", "app")
        assert len(await _rows(factory, SaasApp)) == 1

    @pytest.mark.asyncio
    async def test_invalid_slug_is_refused(self, factory):
        with pytest.raises(ValueError):
            await _run(factory, "saas", "create", "--name", "A", "--slug", "Not A Slug")


class TestClientCommands:
    async def _two_saas(self, factory):
        a = await _run(factory, "saas", "create", "--name", "A", "--slug", "app-a")
        b = await _run(factory, "saas", "create", "--name", "B", "--slug", "app-b")
        return a, b

    @pytest.mark.asyncio
    async def test_bind_by_slug_and_by_identifier(self, factory):
        a, b = await self._two_saas(factory)

        by_slug = await _run(factory, "client", "bind", "--saas", "app-a", "--client-id", "c1")
        by_id = await _run(factory, "client", "bind", "--saas", b["id"], "--client-id", "c1")

        assert by_slug["saas_id"] == a["id"]
        assert by_id["saas_slug"] == "app-b"
        assert len(await _rows(factory, SaasClientBinding)) == 2

    @pytest.mark.asyncio
    async def test_bind_is_idempotent(self, factory):
        await self._two_saas(factory)

        await _run(factory, "client", "bind", "--saas", "app-a", "--client-id", "c1")
        await _run(factory, "client", "bind", "--saas", "app-a", "--client-id", "c1")

        assert len(await _rows(factory, SaasClientBinding)) == 1

    @pytest.mark.asyncio
    async def test_unbind(self, factory):
        await self._two_saas(factory)
        await _run(factory, "client", "bind", "--saas", "app-a", "--client-id", "c1")

        await _run(factory, "client", "unbind", "--saas", "app-a", "--client-id", "c1")

        assert await _rows(factory, SaasClientBinding) == []

    @pytest.mark.asyncio
    async def test_unbind_unknown_binding(self, factory):
        await self._two_saas(factory)

        with pytest.raises(cli.CliError, match="not bound"):
            await _run(factory, "client", "unbind", "--saas", "app-a", "--client-id", "nobody")

    @pytest.mark.asyncio
    async def test_unknown_saas(self, factory):
        with pytest.raises(cli.CliError, match="not found"):
            await _run(factory, "client", "bind", "--saas", "ghost", "--client-id", "c1")
        assert await _rows(factory, SaasClientBinding) == []

    @pytest.mark.asyncio
    async def test_list_filters(self, factory):
        await self._two_saas(factory)
        await _run(factory, "client", "bind", "--saas", "app-a", "--client-id", "c1")
        await _run(factory, "client", "bind", "--saas", "app-b", "--client-id", "c1")
        await _run(factory, "client", "bind", "--saas", "app-b", "--client-id", "c2")

        everything = await _run(factory, "client", "list")
        of_b = await _run(factory, "client", "list", "--saas", "app-b")
        of_c1 = await _run(factory, "client", "list", "--client-id", "c1")

        assert len(everything) == 3
        assert [row["client_id"] for row in of_b] == ["c1", "c2"]
        assert [row["saas_slug"] for row in of_c1] == ["app-a", "app-b"]


class TestMain:
    def test_main_prints_json_and_returns_zero(self, monkeypatch, capsys):
        async def fake_run(argv, session_factory=None):
            return [{"slug": "app"}]

        monkeypatch.setattr(cli, "run", fake_run)

        assert cli.main(["saas", "list"]) == 0
        assert json.loads(capsys.readouterr().out) == [{"slug": "app"}]

    def test_main_reports_errors_on_stderr(self, monkeypatch, capsys):
        async def fake_run(argv, session_factory=None):
            raise cli.CliError("SaaS app 'ghost' not found")

        monkeypatch.setattr(cli, "run", fake_run)

        assert cli.main(["client", "bind", "--saas", "ghost", "--client-id", "c"]) == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "ghost" in captured.err

    def test_a_group_and_an_action_are_required(self):
        with pytest.raises(SystemExit):
            cli.build_parser().parse_args([])
        with pytest.raises(SystemExit):
            cli.build_parser().parse_args(["client"])

    def test_entry_point_is_declared(self):
        import tomllib
        from pathlib import Path

        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        scripts = tomllib.loads(pyproject.read_text())["project"]["scripts"]

        assert scripts == {"billing-admin": "billing.cli:main"}
