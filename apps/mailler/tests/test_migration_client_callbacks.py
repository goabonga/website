# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the 009 migration, run on SQLite."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION = Path(__file__).parent.parent / "alembic" / "versions" / "009_add_client_callbacks.py"


@pytest.fixture(scope="module")
def migration():
    spec = importlib.util.spec_from_file_location("migration_009", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def engine(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path}/callbacks.db")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE authorized_clients (id INTEGER PRIMARY KEY, client_id VARCHAR(255))"
            )
        )
        connection.execute(sa.text("INSERT INTO authorized_clients (client_id) VALUES ('a')"))
    yield engine
    engine.dispose()


def _run(engine, function):
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        function()


class TestCallbacksMigration:
    def test_upgrade_adds_the_columns(self, migration, engine):
        _run(engine, migration.upgrade)
        columns = {c["name"]: c for c in sa.inspect(engine).get_columns("authorized_clients")}
        assert columns["callback_url"]["nullable"] is True
        assert columns["callback_secret"]["nullable"] is True

    def test_existing_clients_have_no_callback(self, migration, engine):
        _run(engine, migration.upgrade)
        with engine.begin() as connection:
            row = connection.execute(
                sa.text("SELECT callback_url, callback_secret FROM authorized_clients")
            ).one()
        assert tuple(row) == (None, None)

    def test_upgrade_can_run_twice(self, migration, engine):
        _run(engine, migration.upgrade)
        _run(engine, migration.upgrade)

    def test_downgrade_removes_the_columns(self, migration, engine):
        _run(engine, migration.upgrade)
        _run(engine, migration.downgrade)
        names = {c["name"] for c in sa.inspect(engine).get_columns("authorized_clients")}
        assert names == {"id", "client_id"}
