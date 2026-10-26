# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the Alembic migrations."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

APP_DIR = Path(__file__).resolve().parents[1]


def _config() -> Config:
    return Config(str(APP_DIR / "alembic.ini"))


class TestMigrationChain:
    """Tests for the revision history."""

    def test_single_head(self):
        """The history should be linear with a single head."""
        script = ScriptDirectory.from_config(_config())
        assert script.get_heads() == ["006"]

    def test_revisions_are_chained(self):
        """Every revision except the first should have a parent."""
        script = ScriptDirectory.from_config(_config())
        chain = [rev.revision for rev in script.walk_revisions()]
        assert chain == ["006", "005", "004", "003", "002", "001"]


class TestOfflineUpgrade:
    """Tests for rendering the migrations as SQL."""

    def test_upgrade_renders_all_tables(self, capsys):
        """Upgrading to head offline should create every model table."""
        command.upgrade(_config(), "head", sql=True)
        sql = capsys.readouterr().out

        for table in (
            "saas_apps",
            "billing_products",
            "billing_prices",
            "customers",
            "subscriptions",
            "usage_events",
        ):
            assert f"CREATE TABLE {table}" in sql

    def test_customer_soft_delete_column_is_added(self, capsys):
        """Revision 003 should add the deleted_at column to customers."""
        command.upgrade(_config(), "head", sql=True)
        sql = capsys.readouterr().out

        assert "deleted_at" in sql


class TestScopingRevision:
    """Tests for revision 005 (plan slug, per-SaaS idempotency, URL allow-list)."""

    def _sql(self, capsys) -> str:
        command.upgrade(_config(), "head", sql=True)
        return capsys.readouterr().out

    def test_product_slug_is_added_backfilled_and_unique(self, capsys):
        sql = self._sql(capsys)

        assert "ALTER TABLE billing_products ADD COLUMN slug" in sql
        assert "UPDATE billing_products" in sql
        assert "uq_product_saas_slug UNIQUE (saas_app_id, slug)" in sql

    def test_usage_idempotency_becomes_per_saas(self, capsys):
        sql = self._sql(capsys)

        assert "ALTER TABLE usage_events ADD COLUMN saas_app_id" in sql
        assert "DROP CONSTRAINT usage_events_idempotency_key_key" in sql
        assert "uq_usage_saas_idempotency UNIQUE (saas_app_id, idempotency_key)" in sql

    def test_checkout_url_allowlist_column_is_added(self, capsys):
        assert "ADD COLUMN checkout_url_allowlist JSONB" in self._sql(capsys)

    def test_no_catalog_data_is_seeded(self, capsys):
        """Tenants and plans are deployment data, never inserted by a migration."""
        sql = self._sql(capsys)

        assert "INSERT INTO saas_apps" not in sql
        assert "INSERT INTO billing_products" not in sql
        assert "prod_" not in sql
