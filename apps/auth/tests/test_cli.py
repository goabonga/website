# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.cli — the `auth` command line."""

import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from auth import cli
from auth.services.bootstrap import BootstrapError
from auth.services.catalog import CatalogError, SyncReport


@pytest.fixture
def session():
    return AsyncMock()


@pytest.fixture(autouse=True)
def fake_database(session):
    @asynccontextmanager
    async def factory():
        yield session

    with (
        patch.object(cli, "async_session_factory", factory),
        patch.object(cli, "close_database", AsyncMock()),
    ):
        yield


@pytest.fixture
def catalog_file(tmp_path):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps({"scopes": [{"name": "notes:read"}]}))
    return str(path)


def run(*argv):
    return cli.main(list(argv))


class TestParser:
    def test_a_command_is_required(self):
        with pytest.raises(SystemExit):
            run()

    def test_catalog_needs_its_subcommand(self):
        with pytest.raises(SystemExit):
            run("catalog")

    def test_sync_options(self):
        args = cli.build_parser().parse_args(
            ["catalog", "sync", "--file", "f", "--dry-run", "--json"]
        )
        assert (args.file, args.dry_run, args.as_json) == ("f", True, True)


class TestCatalogSync:
    def test_commits_the_changes(self, session, catalog_file, capsys):
        report = SyncReport(created=["scope notes:read"])
        with patch.object(cli, "sync_catalog", AsyncMock(return_value=report)):
            assert run("catalog", "sync", "--file", catalog_file) == 0
        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()
        out = capsys.readouterr().out
        assert "created scope notes:read" in out
        assert "catalog: changed 1 item(s)" in out

    def test_dry_run_rolls_back(self, session, catalog_file, capsys):
        report = SyncReport(created=["scope notes:read"])
        with patch.object(cli, "sync_catalog", AsyncMock(return_value=report)):
            assert run("catalog", "sync", "--file", catalog_file, "--dry-run") == 0
        session.commit.assert_not_awaited()
        session.rollback.assert_awaited_once()
        out = capsys.readouterr().out
        assert "would create scope notes:read" in out
        assert "catalog: would change 1 item(s)" in out

    def test_nothing_to_change(self, catalog_file, capsys):
        with patch.object(cli, "sync_catalog", AsyncMock(return_value=SyncReport())):
            assert run("catalog", "sync", "--file", catalog_file) == 0
        assert "catalog: nothing to change" in capsys.readouterr().out

    def test_json_report(self, catalog_file, capsys):
        report = SyncReport(updated=["role r (description)"])
        with patch.object(cli, "sync_catalog", AsyncMock(return_value=report)):
            assert run("catalog", "sync", "--file", catalog_file, "--json") == 0
        document = json.loads(capsys.readouterr().out)
        assert document["changed"] is True and document["dry_run"] is False
        assert document["updated"] == ["role r (description)"]

    def test_file_comes_from_the_settings(self, catalog_file):
        with (
            patch.object(cli.settings, "catalog_file", catalog_file),
            patch.object(cli, "sync_catalog", AsyncMock(return_value=SyncReport())) as sync,
        ):
            assert run("catalog", "sync") == 0
        sync.assert_awaited_once()

    def test_no_file_at_all(self, capsys):
        with patch.object(cli.settings, "catalog_file", ""):
            assert run("catalog", "sync") == 2
        assert "no catalog file" in capsys.readouterr().err

    def test_invalid_catalog_exits_with_2_before_touching_the_database(
        self, session, tmp_path, capsys
    ):
        path = tmp_path / "bad.json"
        path.write_text("[]")
        assert run("catalog", "sync", "--file", str(path)) == 2
        assert "auth: invalid catalog" in capsys.readouterr().err
        session.commit.assert_not_awaited()

    def test_catalog_error_while_syncing_rolls_back(self, session, catalog_file, capsys):
        with patch.object(cli, "sync_catalog", AsyncMock(side_effect=CatalogError("unknown"))):
            assert run("catalog", "sync", "--file", catalog_file) == 2
        session.rollback.assert_awaited()
        session.commit.assert_not_awaited()

    def test_other_failures_exit_with_1(self, catalog_file, capsys):
        with patch.object(cli, "sync_catalog", AsyncMock(side_effect=RuntimeError("down"))):
            assert run("catalog", "sync", "--file", catalog_file) == 1
        assert "RuntimeError: down" in capsys.readouterr().err


class TestBootstrap:
    def test_commits_the_changes(self, session, capsys):
        report = SyncReport(created=["platform tenant main"])
        with patch.object(cli, "bootstrap", AsyncMock(return_value=report)):
            assert run("bootstrap") == 0
        session.commit.assert_awaited_once()
        out = capsys.readouterr().out
        assert "created platform tenant main" in out
        assert "bootstrap: changed 1 item(s)" in out

    def test_dry_run_rolls_back(self, session, capsys):
        report = SyncReport(created=["platform tenant main"])
        with patch.object(cli, "bootstrap", AsyncMock(return_value=report)):
            assert run("bootstrap", "--dry-run") == 0
        session.commit.assert_not_awaited()
        session.rollback.assert_awaited_once()
        assert "would create platform tenant main" in capsys.readouterr().out

    def test_json_report(self, capsys):
        with patch.object(cli, "bootstrap", AsyncMock(return_value=SyncReport())):
            assert run("bootstrap", "--json") == 0
        assert json.loads(capsys.readouterr().out)["changed"] is False

    def test_the_options_come_from_the_settings(self):
        with (
            patch.object(cli, "bootstrap", AsyncMock(return_value=SyncReport())) as boot,
            patch.object(cli.settings, "platform_tenant_slug", "main-site"),
        ):
            assert run("bootstrap") == 0
        assert boot.await_args.args[1].slug == "main-site"

    def test_invalid_settings_exit_with_2_before_touching_the_database(self, session, capsys):
        with patch.object(cli.settings, "platform_tenant_slug", "Not A Slug"):
            assert run("bootstrap") == 2
        assert "not a valid slug" in capsys.readouterr().err
        session.commit.assert_not_awaited()

    def test_a_slug_conflict_exits_with_2(self, session, capsys):
        error = BootstrapError("the slug 'main' belongs to a tenant that is not the platform")
        with patch.object(cli, "bootstrap", AsyncMock(side_effect=error)):
            assert run("bootstrap") == 2
        session.rollback.assert_awaited()
        assert "not the platform" in capsys.readouterr().err
