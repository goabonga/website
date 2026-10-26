# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment hooks.

Scenarios run in-process: requests go through httpx's ASGI transport straight
into the FastAPI application, so no server, identity provider, database or
broker is needed:

- the token validation clients are replaced by a lookup table filled by the
  authentication steps;
- the database is a temporary SQLite file shared by the asynchronous engine
  (API) and the synchronous engine (Celery tasks), emptied after each
  scenario;
- Celery tasks are never sent to a broker, ``delay`` calls are recorded in
  ``context.delayed`` and tasks are run directly by the steps;
- PostgreSQL-only column types (UUID, JSONB, ARRAY, timezone-aware datetimes)
  are swapped for portable equivalents on the SQLite test database;
- the inbound router is registered even though ``INBOUND_ENABLED`` is off by
  default.
"""

import asyncio
import shutil
import tempfile
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends
from httpx import ASGITransport
from mailler.auth import AuthContext, require_scopes
from mailler.auth.introspection import TokenRevokedError
from mailler.config import settings
from mailler.database import AsyncSessionLocal, SyncSessionLocal
from mailler.main import app
from mailler.models import Base
from mailler.routes.inbound import router as inbound_router
from mailler.services.providers import factory
from sqlalchemy import CHAR, JSON, DateTime, TypeDecorator, create_engine, delete
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import create_async_engine
from starlette.routing import NoMatchFound

# Probe routes protected by scopes, so authentication can be exercised before
# the feature routes exist and independently of them.
probe = APIRouter(prefix="/__probe")


@probe.get("/read")
async def probe_read(auth: AuthContext = Depends(require_scopes("mailler:read"))):
    return {"user_id": auth.user_id, "scopes": auth.scopes}


@probe.get("/client")
async def probe_client(auth: AuthContext = Depends(require_scopes("mailler:read"))):
    return {"client_id": auth.client_id, "is_admin": auth.is_admin}


@probe.get("/send")
async def probe_send(auth: AuthContext = Depends(require_scopes("mailler:send"))):
    return {"user_id": auth.user_id, "scopes": auth.scopes}


class PortableUuid(TypeDecorator):
    """UUID column for SQLite that, like the PostgreSQL drivers, also accepts strings."""

    impl = CHAR(32)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return (value if isinstance(value, UUID) else UUID(str(value))).hex

    def process_result_value(self, value, dialect):
        return None if value is None else UUID(value)


class PortableDateTime(TypeDecorator):
    """Timezone-aware datetime for SQLite, which stores naive UTC values."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(UTC).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        return None if value is None else value.replace(tzinfo=UTC)


def _make_metadata_portable():
    """Swap PostgreSQL-only column types for portable ones so SQLite can host them."""
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, postgresql.JSONB | postgresql.ARRAY):
                column.type = JSON()
            elif isinstance(column.type, postgresql.UUID):
                column.type = PortableUuid()
            elif isinstance(column.type, DateTime):
                column.type = PortableDateTime()


def _delayed_task(context, name):
    """Return a replacement for a Celery task whose ``delay`` only records the call."""
    task = MagicMock(name=name)

    def delay(*args, **kwargs):
        context.delayed.append((name, args, kwargs))
        return MagicMock(id=f"bdd-task-{len(context.delayed)}")

    task.delay.side_effect = delay
    return task


def _validate(context):
    """Build the token validation function backed by ``context.token_claims``."""

    async def validate(token):
        if token in context.revoked_tokens:
            raise TokenRevokedError("revoked")
        try:
            return context.token_claims[token]
        except KeyError:
            raise ValueError("unknown token") from None

    return validate


def before_all(context):
    """Create the event loop, replace token validation and build the client."""
    context.loop = asyncio.new_event_loop()
    asyncio.set_event_loop(context.loop)
    # The CORS middleware keeps a reference to the configured list, so extending
    # it in place is enough for the running application.
    settings.cors_origins.append("https://frontend.example")
    # The platform sender is empty by default, scenarios send through this one.
    settings.default_from = "sender@bdd.example"
    # Scenarios change the registry between two calls: nothing is remembered.
    settings.client_cache_ttl = 0

    context.token_claims = {}
    context.revoked_tokens = set()

    context._patchers = [
        patch("mailler.auth.dependencies.jwks_manager"),
        patch("mailler.auth.dependencies.introspection_client"),
        patch("mailler.auth.dependencies.token_exchange_client"),
    ]
    context.jwks, context.introspection, context.exchange = [p.start() for p in context._patchers]
    context.exchange.is_configured = False
    validate = _validate(context)
    context.introspection.validate_token_with_introspection = AsyncMock(side_effect=validate)
    context.introspection.validate_opaque_token = AsyncMock(side_effect=validate)

    # In-process database: a temporary SQLite file shared by the asynchronous
    # engine (API) and the synchronous engine (Celery tasks).
    context.tmpdir = tempfile.mkdtemp(prefix="mailler-bdd-")
    _make_metadata_portable()
    context.async_engine = create_async_engine(f"sqlite+aiosqlite:///{context.tmpdir}/bdd.db")
    context.sync_engine = create_engine(f"sqlite:///{context.tmpdir}/bdd.db")
    AsyncSessionLocal.configure(bind=context.async_engine)
    SyncSessionLocal.configure(bind=context.sync_engine)
    Base.metadata.create_all(context.sync_engine)

    # Celery tasks are never sent to a broker: calls are recorded instead.
    context.delayed = []
    context._patchers.append(
        patch("mailler.routes.send.send_email_task", _delayed_task(context, "send_email_task"))
    )
    context._patchers[-1].start()
    context._patchers.append(
        patch("mailler.tasks.scheduler.send_email_task", _delayed_task(context, "send_email_task"))
    )
    context._patchers[-1].start()
    for target, name in (
        ("mailler.routes.campaigns.send_campaign_task", "send_campaign_task"),
        ("mailler.tasks.scheduler.send_campaign_task", "send_campaign_task"),
        ("mailler.tasks.send.send_email_task", "send_email_task"),
        ("mailler.tasks.callbacks.deliver_status_callback", "deliver_status_callback"),
    ):
        context._patchers.append(patch(target, _delayed_task(context, name)))
        context._patchers[-1].start()

    # Inbound routes are only registered when INBOUND_ENABLED is set at start-up.
    try:
        app.url_path_for("list_inbound_emails")
    except NoMatchFound:
        app.include_router(inbound_router, prefix="/api/v1")

    app.include_router(probe)
    context.client = httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    )


def before_scenario(context, scenario):
    """Reset per-scenario state."""
    context.response = None
    context.created_ids = {}
    context.token_claims.clear()
    context.revoked_tokens.clear()
    context.jwks.is_configured = True
    context.client.headers.pop("Authorization", None)
    context.settings_backup = {}
    context.delayed.clear()
    factory._providers.clear()


def after_scenario(context, scenario):
    """Restore the settings overridden by the scenario and empty the database."""
    with context.sync_engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(delete(table))
    for name, value in context.settings_backup.items():
        setattr(settings, name, value)
    factory._providers.clear()


def after_all(context):
    """Close the client, stop the patches and close the event loop."""
    context.loop.run_until_complete(context.client.aclose())
    for patcher in context._patchers:
        patcher.stop()
    context.loop.run_until_complete(context.async_engine.dispose())
    context.sync_engine.dispose()
    shutil.rmtree(context.tmpdir, ignore_errors=True)
    context.loop.close()
