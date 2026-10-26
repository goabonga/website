# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the 006 migration, run on SQLite against hand-written legacy schemas.

The migration is written for PostgreSQL, but its client scoping steps only use
portable operations, so the upgrade path of a database created before the data
belonged to clients is exercised here on SQLite.
"""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError

MIGRATION = Path(__file__).parent.parent / "alembic" / "versions" / "006_add_authorized_clients.py"

LEGACY_SCHEMA = [
    "CREATE TABLE email_templates (id INTEGER PRIMARY KEY, slug VARCHAR(100) NOT NULL)",
    "CREATE UNIQUE INDEX ix_email_templates_slug ON email_templates (slug)",
    "CREATE TABLE contacts (id INTEGER PRIMARY KEY, email VARCHAR(255) NOT NULL)",
    "CREATE UNIQUE INDEX ix_contacts_email ON contacts (email)",
    "CREATE TABLE contact_groups (id INTEGER PRIMARY KEY, slug VARCHAR(100) NOT NULL)",
    "CREATE UNIQUE INDEX ix_contact_groups_slug ON contact_groups (slug)",
    "CREATE TABLE email_campaigns (id INTEGER PRIMARY KEY, name VARCHAR(255) NOT NULL)",
    "CREATE TABLE emails (id INTEGER PRIMARY KEY, client_id VARCHAR(255))",
]

SCOPED_SCHEMA = [
    "CREATE TABLE email_templates (id INTEGER PRIMARY KEY, client_id VARCHAR(255) NOT NULL,"
    " slug VARCHAR(100) NOT NULL, CONSTRAINT uq_email_templates_client_slug"
    " UNIQUE (client_id, slug))",
    "CREATE INDEX ix_email_templates_client_id ON email_templates (client_id)",
    "CREATE INDEX ix_email_templates_slug ON email_templates (slug)",
    "CREATE TABLE contacts (id INTEGER PRIMARY KEY, client_id VARCHAR(255) NOT NULL,"
    " email VARCHAR(255) NOT NULL, CONSTRAINT uq_contacts_client_email UNIQUE (client_id, email))",
    "CREATE INDEX ix_contacts_client_id ON contacts (client_id)",
    "CREATE INDEX ix_contacts_email ON contacts (email)",
    "CREATE TABLE contact_groups (id INTEGER PRIMARY KEY, client_id VARCHAR(255) NOT NULL,"
    " slug VARCHAR(100) NOT NULL, CONSTRAINT uq_contact_groups_client_slug"
    " UNIQUE (client_id, slug))",
    "CREATE INDEX ix_contact_groups_client_id ON contact_groups (client_id)",
    "CREATE INDEX ix_contact_groups_slug ON contact_groups (slug)",
    "CREATE TABLE email_campaigns (id INTEGER PRIMARY KEY, client_id VARCHAR(255) NOT NULL,"
    " name VARCHAR(255) NOT NULL)",
    "CREATE INDEX ix_email_campaigns_client_id ON email_campaigns (client_id)",
    "CREATE TABLE emails (id INTEGER PRIMARY KEY, client_id VARCHAR(255))",
]


@pytest.fixture(scope="module")
def migration():
    spec = importlib.util.spec_from_file_location("migration_006", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def engine(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path}/migration.db")
    yield engine
    engine.dispose()


def _prepare(engine, schema, rows=()):
    with engine.begin() as connection:
        for statement in [*schema, *rows]:
            connection.execute(sa.text(statement))


def _run(engine, function):
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        function()


def _inspect(engine):
    return sa.inspect(engine)


LEGACY_ROWS = [
    "INSERT INTO email_templates (slug) VALUES ('welcome')",
    "INSERT INTO contacts (email) VALUES ('a@example.com')",
    "INSERT INTO contact_groups (slug) VALUES ('vip')",
    "INSERT INTO email_campaigns (name) VALUES ('Launch')",
    "INSERT INTO emails (client_id) VALUES (NULL)",
    "INSERT INTO emails (client_id) VALUES ('someone')",
]


class TestRegistryTable:
    def test_is_created(self, migration, engine):
        _prepare(engine, [])
        _run(engine, migration.upgrade)

        columns = {c["name"] for c in _inspect(engine).get_columns("authorized_clients")}
        assert {
            "client_id",
            "is_active",
            "from_email",
            "from_name",
            "reply_to",
            "allowed_senders",
            "allowed_providers",
            "default_provider",
        } <= columns
        indexes = _inspect(engine).get_indexes("authorized_clients")
        assert [(i["name"], i["unique"]) for i in indexes] == [
            ("ix_authorized_clients_client_id", 1)
        ]

    def test_client_id_is_unique(self, migration, engine):
        _prepare(engine, [])
        _run(engine, migration.upgrade)
        with engine.begin() as connection:
            insert = "INSERT INTO authorized_clients (client_id) VALUES ('app-one')"
            connection.execute(sa.text(insert))
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(sa.text(insert))

    def test_new_clients_are_active_with_empty_lists(self, migration, engine):
        _prepare(engine, [])
        _run(engine, migration.upgrade)
        with engine.begin() as connection:
            connection.execute(sa.text("INSERT INTO authorized_clients (client_id) VALUES ('a')"))
            row = connection.execute(
                sa.text(
                    "SELECT is_active, allowed_senders, allowed_providers FROM authorized_clients"
                )
            ).one()
        assert row[0] in (1, True)
        assert (row[1], row[2]) == ("[]", "[]")

    def test_downgrade_drops_only_the_registry(self, migration, engine):
        _prepare(engine, SCOPED_SCHEMA)
        _run(engine, migration.upgrade)
        _run(engine, migration.downgrade)
        tables = _inspect(engine).get_table_names()
        assert "authorized_clients" not in tables
        assert "contacts" in tables


class TestUpgradeOfAnUnscopedDatabase:
    def test_existing_rows_go_to_the_legacy_client(self, migration, engine):
        _prepare(engine, LEGACY_SCHEMA, LEGACY_ROWS)
        with patch.object(migration.settings, "legacy_client_id", "legacy-app"):
            _run(engine, migration.upgrade)

        with engine.begin() as connection:
            for table in ("email_templates", "contacts", "contact_groups", "email_campaigns"):
                owners = connection.execute(
                    sa.text(f"SELECT DISTINCT client_id FROM {table}")
                ).all()
                assert owners == [("legacy-app",)], table
            emails = connection.execute(sa.text("SELECT client_id FROM emails ORDER BY id")).all()
        # unowned emails are attributed too, the owned ones are left alone
        assert emails == [("legacy-app",), ("someone",)]

    def test_client_is_required_afterwards(self, migration, engine):
        _prepare(engine, LEGACY_SCHEMA)
        _run(engine, migration.upgrade)
        inspector = _inspect(engine)
        for table in ("email_templates", "contacts", "contact_groups", "email_campaigns"):
            column = next(c for c in inspector.get_columns(table) if c["name"] == "client_id")
            assert column["nullable"] is False, table
            assert "ix_" + table + "_client_id" in {i["name"] for i in inspector.get_indexes(table)}

    def test_uniqueness_becomes_per_client(self, migration, engine):
        _prepare(engine, LEGACY_SCHEMA)
        _run(engine, migration.upgrade)

        inspector = _inspect(engine)
        for table, old_index in (
            ("email_templates", "ix_email_templates_slug"),
            ("contacts", "ix_contacts_email"),
            ("contact_groups", "ix_contact_groups_slug"),
        ):
            index = next(i for i in inspector.get_indexes(table) if i["name"] == old_index)
            assert not index["unique"], table

        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO email_templates (client_id, slug) VALUES ('one', 'welcome'),"
                    " ('two', 'welcome')"
                )
            )
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                sa.text("INSERT INTO email_templates (client_id, slug) VALUES ('one', 'welcome')")
            )
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO contacts (client_id, email) VALUES ('one', 'a@x'), ('two', 'a@x')"
                )
            )
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO contact_groups (client_id, slug) VALUES ('one', 'g'), ('one', 'g')"
                )
            )

    def test_rows_without_a_legacy_client_stop_the_migration(self, migration, engine):
        _prepare(engine, LEGACY_SCHEMA, LEGACY_ROWS)
        with (
            patch.object(migration.settings, "legacy_client_id", ""),
            pytest.raises(RuntimeError, match="LEGACY_CLIENT_ID"),
        ):
            _run(engine, migration.upgrade)

    def test_empty_tables_do_not_need_a_legacy_client(self, migration, engine):
        _prepare(engine, LEGACY_SCHEMA)
        with patch.object(migration.settings, "legacy_client_id", ""):
            _run(engine, migration.upgrade)
        assert "authorized_clients" in _inspect(engine).get_table_names()


class TestUpgradeOfAScopedDatabase:
    def test_nothing_changes_and_it_can_run_twice(self, migration, engine):
        _prepare(engine, SCOPED_SCHEMA)
        before = {
            table: (
                sorted(c["name"] for c in _inspect(engine).get_columns(table)),
                sorted(i["name"] for i in _inspect(engine).get_indexes(table)),
                sorted(u["name"] for u in _inspect(engine).get_unique_constraints(table)),
            )
            for table in ("email_templates", "contacts", "contact_groups", "email_campaigns")
        }

        _run(engine, migration.upgrade)
        _run(engine, migration.upgrade)

        for table, snapshot in before.items():
            assert (
                sorted(c["name"] for c in _inspect(engine).get_columns(table)),
                sorted(i["name"] for i in _inspect(engine).get_indexes(table)),
                sorted(u["name"] for u in _inspect(engine).get_unique_constraints(table)),
            ) == snapshot, table

    def test_tables_that_do_not_exist_yet_are_skipped(self, migration, engine):
        _prepare(engine, [])
        _run(engine, migration.upgrade)
        assert _inspect(engine).get_table_names() == ["authorized_clients"]
