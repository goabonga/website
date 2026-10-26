# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for database.feature.

No database is needed: the migrations are rendered as SQL (``upgrade --sql``) and the
session module is only imported, never connected.
"""

import importlib.util
import io
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import vpn_portal.config
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from behave import given, then, when
from vpn_portal.db import session as session_module
from vpn_portal.db.models import VPNCertificate

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


@given('the database URL "{url}"')
def step_database_url(context, url):
    context.database_url = url


@when("the async database URL is computed")
def step_compute_url(context):
    # Execute a private copy: other modules hold references to the real module's get_db.
    spec = importlib.util.spec_from_file_location("session_probe", session_module.__file__)
    module = importlib.util.module_from_spec(spec)
    with patch.object(vpn_portal.config.settings, "database_url", context.database_url):
        spec.loader.exec_module(module)
    context.async_url = module.database_url


@then('the async database URL should be "{url}"')
def step_check_url(context, url):
    assert context.async_url == url, context.async_url


def _certificate(minutes_left):
    now = datetime.now(UTC)
    return VPNCertificate(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        username="user@example.com",
        serial_number="serial-1",
        common_name="vpn-user-1",
        not_before=now - timedelta(minutes=15),
        not_after=now + timedelta(minutes=minutes_left),
        scopes=["vpn:connect"],
        assigned_routes=["10.8.0.0/24"],
    )


@given("a certificate valid for {minutes:d} more minutes")
def step_valid_certificate(context, minutes):
    context.certificate = _certificate(minutes)


@given("a certificate that expired {minutes:d} minutes ago")
def step_expired_certificate(context, minutes):
    context.certificate = _certificate(-minutes)


@given("the certificate is revoked")
def step_revoke(context):
    context.certificate.revoked_at = datetime.now(UTC)
    context.certificate.revocation_reason = "user_requested"


@then("the certificate should be valid")
def step_is_valid(context):
    assert context.certificate.is_valid


@then("the certificate should not be valid")
def step_is_not_valid(context):
    assert not context.certificate.is_valid


@then("the certificate should be revoked")
def step_is_revoked(context):
    assert context.certificate.is_revoked


@then("the certificate should be expired")
def step_is_expired(context):
    assert context.certificate.is_expired


@when("the migrations are rendered as SQL for PostgreSQL")
def step_render_sql(context):
    config = Config(str(ALEMBIC_INI))
    config.output_buffer = io.StringIO()
    command.upgrade(config, "head", sql=True)
    context.sql = config.output_buffer.getvalue()


@then('the SQL should create the table "{table}"')
def step_creates_table(context, table):
    assert f"CREATE TABLE {table} " in context.sql


@then('the SQL should create the index "{index}"')
def step_creates_index(context, index):
    assert f"CREATE INDEX {index} " in context.sql


@then("the SQL should declare the serial number unique")
def step_serial_unique(context):
    assert "UNIQUE (serial_number)" in context.sql


@then("the migration history should have exactly one head")
def step_one_head(context):
    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))
    assert len(script.get_heads()) == 1
