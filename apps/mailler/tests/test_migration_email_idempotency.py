# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the 008 migration, run on SQLite."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError

MIGRATION = (
    Path(__file__).parent.parent / "alembic" / "versions" / "008_add_email_idempotency_key.py"
)


@pytest.fixture(scope="module")
def migration():
    spec = importlib.util.spec_from_file_location("migration_008", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def engine(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path}/idempotency.db")
    with engine.begin() as connection:
        connection.execute(
            sa.text("CREATE TABLE emails (id INTEGER PRIMARY KEY, client_id VARCHAR(255))")
        )
    yield engine
    engine.dispose()


def _run(engine, function):
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        function()


def _insert(engine, client, key):
    with engine.begin() as connection:
        connection.execute(
            sa.text("INSERT INTO emails (client_id, idempotency_key) VALUES (:c, :k)"),
            {"c": client, "k": key},
        )


class TestIdempotencyMigration:
    def test_upgrade_adds_the_column(self, migration, engine):
        _run(engine, migration.upgrade)
        columns = {c["name"]: c for c in sa.inspect(engine).get_columns("emails")}
        assert columns["idempotency_key"]["nullable"] is True

    def test_a_key_is_unique_per_client(self, migration, engine):
        _run(engine, migration.upgrade)
        _insert(engine, "app-one", "key-1")
        _insert(engine, "app-two", "key-1")
        with pytest.raises(IntegrityError):
            _insert(engine, "app-one", "key-1")

    def test_emails_without_a_key_are_not_constrained(self, migration, engine):
        _run(engine, migration.upgrade)
        _insert(engine, "app-one", None)
        _insert(engine, "app-one", None)

    def test_upgrade_can_run_twice(self, migration, engine):
        _run(engine, migration.upgrade)
        _run(engine, migration.upgrade)
        constraints = sa.inspect(engine).get_unique_constraints("emails")
        assert [c["name"] for c in constraints] == ["uq_emails_client_idempotency"]

    def test_downgrade_removes_them(self, migration, engine):
        _run(engine, migration.upgrade)
        _run(engine, migration.downgrade)
        inspector = sa.inspect(engine)
        assert {c["name"] for c in inspector.get_columns("emails")} == {"id", "client_id"}
        assert inspector.get_unique_constraints("emails") == []
