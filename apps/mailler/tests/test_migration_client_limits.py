# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the 007 migration, run on SQLite."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION = Path(__file__).parent.parent / "alembic" / "versions" / "007_add_client_limits.py"

BASE_SCHEMA = [
    "CREATE TABLE authorized_clients (id INTEGER PRIMARY KEY, client_id VARCHAR(255) NOT NULL)",
    "CREATE TABLE emails (id INTEGER PRIMARY KEY, client_id VARCHAR(255), created_at DATETIME)",
]


@pytest.fixture(scope="module")
def migration():
    spec = importlib.util.spec_from_file_location("migration_007", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def engine(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path}/limits.db")
    with engine.begin() as connection:
        for statement in BASE_SCHEMA:
            connection.execute(sa.text(statement))
    yield engine
    engine.dispose()


def _run(engine, function):
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        function()


class TestClientLimitsMigration:
    def test_upgrade_adds_the_limits_and_the_index(self, migration, engine):
        _run(engine, migration.upgrade)
        inspector = sa.inspect(engine)
        columns = {c["name"]: c for c in inspector.get_columns("authorized_clients")}
        assert columns["rate_limit_per_minute"]["nullable"] is True
        assert columns["daily_quota"]["nullable"] is True
        indexes = {i["name"]: i["column_names"] for i in inspector.get_indexes("emails")}
        assert indexes["ix_emails_client_id_created_at"] == ["client_id", "created_at"]

    def test_upgrade_can_run_twice(self, migration, engine):
        _run(engine, migration.upgrade)
        _run(engine, migration.upgrade)
        assert len(sa.inspect(engine).get_indexes("emails")) == 1

    def test_existing_clients_stay_unlimited(self, migration, engine):
        with engine.begin() as connection:
            connection.execute(sa.text("INSERT INTO authorized_clients (client_id) VALUES ('a')"))
        _run(engine, migration.upgrade)
        with engine.begin() as connection:
            row = connection.execute(
                sa.text("SELECT rate_limit_per_minute, daily_quota FROM authorized_clients")
            ).one()
        assert tuple(row) == (None, None)

    def test_downgrade_removes_them(self, migration, engine):
        _run(engine, migration.upgrade)
        _run(engine, migration.downgrade)
        inspector = sa.inspect(engine)
        assert {c["name"] for c in inspector.get_columns("authorized_clients")} == {
            "id",
            "client_id",
        }
        assert inspector.get_indexes("emails") == []
