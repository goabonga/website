# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the Alembic migration chain: a single head, schema only."""

import re
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

APP_DIR = Path(__file__).resolve().parents[1]
VERSIONS = APP_DIR / "alembic" / "versions"

# The head of the chain is the one of the databases deployed before the seed data left the
# migrations: such a database must stay valid.
HEAD = "060"


@pytest.fixture(scope="module")
def script() -> ScriptDirectory:
    config = Config(str(APP_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(APP_DIR / "alembic"))
    return ScriptDirectory.from_config(config)


class TestChain:
    def test_single_head_keeps_the_deployed_revision(self, script):
        assert script.get_heads() == [HEAD]

    def test_chain_is_linear_from_a_single_base(self, script):
        assert script.get_bases() == ["001"]
        walked = [revision.revision for revision in script.walk_revisions()]
        assert len(walked) == len(set(walked)) == len(list(VERSIONS.glob("[0-9]*.py")))

    def test_every_revision_has_a_downgrade(self, script):
        for revision in script.walk_revisions():
            assert callable(getattr(revision.module, "downgrade", None)), revision.revision

    def test_schema_revisions_keep_their_ids(self, script):
        ids = {revision.revision for revision in script.walk_revisions()}
        for kept in ("016", "017", "018", "025", "045", "049", "057", "059", "060"):
            assert kept in ids

    def test_seeding_revisions_are_gone(self, script):
        ids = {revision.revision for revision in script.walk_revisions()}
        for removed in ("019", "026", "041", "046", "047", "056", "058"):
            assert removed not in ids


class TestNoSeedData:
    """The migrations change the schema only: no row, no deployment value."""

    SEEDING = re.compile(
        r"INSERT\s+INTO\s+(scopes|role_scopes|roles|oauth2_clients|tenants)\b", re.IGNORECASE
    )

    @pytest.mark.parametrize("path", sorted(VERSIONS.glob("*.py")), ids=lambda p: p.name)
    def test_no_row_is_seeded(self, path):
        assert not self.SEEDING.search(path.read_text()), path.name

    @pytest.mark.parametrize("path", sorted(VERSIONS.glob("*.py")), ids=lambda p: p.name)
    def test_no_deployment_value(self, path):
        text = path.read_text().lower()
        # The copyright line carries the author's address, which is not a deployment value.
        text = text.replace("goabonga@pm.me", "")
        assert "goabonga" not in text
