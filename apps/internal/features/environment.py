# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment for the internal application.

Scenarios run fully in-process, without any external infrastructure:

- the FastAPI application is driven through an ASGI transport;
- the database is a throw-away SQLite file (PostgreSQL-only column types
  are mapped to JSON for the occasion);
- the OAuth2 token validation is mocked;
- every outbound service client is mocked.
"""

import asyncio
import contextlib
import os
import shutil
import tempfile
import uuid
from unittest.mock import AsyncMock, PropertyMock, patch

# Set required env vars BEFORE any internal import
os.environ.setdefault("OAUTH2_ISSUER", "https://auth.test.local")
os.environ.setdefault("OAUTH2_CLIENT_ID", "test-client")
os.environ.setdefault("OAUTH2_CLIENT_SECRET", "test-secret")
os.environ.setdefault("OAUTH2_FRONTEND_CLIENT_ID", "test-frontend")
os.environ.setdefault("APP_BASE_URL", "http://test")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("APP_NAME", "Internal Test")

from internal.database import Base, get_db
from internal.main import app
from sqlalchemy import JSON, Uuid, event
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Test user defaults
TEST_USER_ID = str(uuid.UUID("00000000-0000-0000-0000-000000000001"))
TEST_USER_EMAIL = "admin@test.local"
TEST_USER_NAME = "Test Admin"
DEFAULT_SCOPES = "*"  # super admin by default


def _build_claims(user_id: str, email: str, name: str, scopes: str) -> dict:
    """Build JWT claims dict for test user."""
    return {
        "sub": user_id,
        "email": email,
        "name": name,
        "scope": scopes,
        "iss": "https://auth.test.local",
        "aud": "test-client",
    }


def _configure_auth(context):
    """Configure auth mocks based on current context state."""
    if context.authenticated:
        claims = _build_claims(
            context.user_id, context.user_email, context.user_name, context.user_scopes
        )
        # Clear any side_effect from previous unauthenticated scenario
        context.mock_jwt_validate.side_effect = None
        context.mock_jwt_validate_introspect.side_effect = None
        context.mock_jwt_validate.return_value = claims
        context.mock_jwt_validate_introspect.return_value = claims
        context.mock_jwt_introspect_active.return_value = True

        # Token exchange returns the user's scopes
        context.mock_exchange_configured.return_value = True
        context.mock_exchange_validate.side_effect = None
        context.mock_exchange_validate.return_value = {
            "scope": context.user_scopes,
            "access_token": "exchanged-test-token",
        }
        context.mock_exchange_exchange.side_effect = None
        context.mock_exchange_exchange.return_value = {
            "scope": context.user_scopes,
            "access_token": "exchanged-test-token",
        }
    else:
        from jose import JWTError

        context.mock_jwt_validate.return_value = None
        context.mock_jwt_validate.side_effect = JWTError("Invalid token")
        context.mock_jwt_validate_introspect.return_value = None
        context.mock_jwt_validate_introspect.side_effect = JWTError("Invalid token")
        context.mock_jwt_introspect_active.return_value = False
        context.mock_exchange_configured.return_value = False


def _adapt_metadata_for_sqlite() -> None:
    """Map the PostgreSQL-only column types of the models to portable ones.

    Arrays, JSONB and pgvector columns become JSON; the PostgreSQL UUID type
    (whose SQLite name has numeric affinity) becomes the generic ``Uuid``.
    """
    from sqlalchemy.dialects.postgresql import JSONB

    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, ARRAY | JSONB) or type(column.type).__name__ == "Vector":
                column.type = JSON()
            elif isinstance(column.type, Uuid) and type(column.type) is not Uuid:
                column.type = Uuid(as_uuid=True)


def before_all(context):
    """Set up test infrastructure."""
    context.loop = asyncio.new_event_loop()
    context.app = app
    context._patchers = []

    # Database: throw-away SQLite file, one engine for the whole run
    context.db_dir = tempfile.mkdtemp(prefix="internal-behave-")
    _adapt_metadata_for_sqlite()
    # No pooling: a connection is opened and closed in the event loop that uses it, and the
    # engine is used by the scenario thread and by the thread of the server of @browser ones
    context.engine = create_async_engine(
        f"sqlite+aiosqlite:///{context.db_dir}/internal.db", echo=False, poolclass=NullPool
    )

    @event.listens_for(context.engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    context.session_maker = async_sessionmaker(
        context.engine, class_=AsyncSession, expire_on_commit=False
    )

    async def _create_tables():
        async with context.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    context.loop.run_until_complete(_create_tables())

    # Override get_db dependency to use the test session
    async def _override_get_db():
        async with context.session_maker() as session:
            try:
                yield session
            finally:
                await session.close()

    app.dependency_overrides[get_db] = _override_get_db

    # --- Auth mocking ---
    context.user_scopes = DEFAULT_SCOPES
    context.user_id = TEST_USER_ID
    context.user_email = TEST_USER_EMAIL
    context.user_name = TEST_USER_NAME
    context.authenticated = True
    context.configure_auth = _configure_auth

    # Mock JWT validator
    context._jwt_validate_patcher = patch("internal.auth.jwt.jwt_validator.validate_token")
    context._jwt_introspect_patcher = patch(
        "internal.auth.jwt.jwt_validator.validate_token_with_introspection"
    )
    context._jwt_introspect_active_patcher = patch(
        "internal.auth.jwt.jwt_validator.introspect_token"
    )
    context.mock_jwt_validate = context._jwt_validate_patcher.start()
    context.mock_jwt_validate_introspect = context._jwt_introspect_patcher.start()
    context.mock_jwt_introspect_active = context._jwt_introspect_active_patcher.start()

    # Mock token exchange (is_configured is a @property, must be patched on the class)
    from internal.services.token_exchange import TokenExchangeClient

    context._token_exchange_configured_patcher = patch.object(
        TokenExchangeClient,
        "is_configured",
        new_callable=PropertyMock,
    )
    context._token_exchange_validate_patcher = patch(
        "internal.services.token_exchange.token_exchange_client.validate_token_scopes",
    )
    context._token_exchange_exchange_patcher = patch(
        "internal.services.token_exchange.token_exchange_client.exchange_token",
    )
    context.mock_exchange_configured = context._token_exchange_configured_patcher.start()
    context.mock_exchange_validate = context._token_exchange_validate_patcher.start()
    context.mock_exchange_exchange = context._token_exchange_exchange_patcher.start()

    # --- External service client mocking ---
    # All service clients must use AsyncMock so their methods are awaitable

    p = patch("internal.routes.analytics.analytics_client", new_callable=AsyncMock)
    context.mock_analytics = p.start()
    context._patchers.append(p)

    # Analytics client used by the dashboard statistics
    p = patch("internal.routes.admin.analytics_client", new_callable=AsyncMock)
    context.mock_analytics_admin = p.start()
    context._patchers.append(p)

    # Auth client (for conversation owner info)
    p = patch("internal.routes.admin.auth_client", new_callable=AsyncMock)
    context.mock_auth_client = p.start()
    context._patchers.append(p)

    p = patch("internal.routes.billing.billing_client", new_callable=AsyncMock)
    context.mock_billing = p.start()
    context._patchers.append(p)

    p = patch("internal.routes.vpn.vpn_portal_client", new_callable=AsyncMock)
    context.mock_vpn = p.start()
    context._patchers.append(p)

    p = patch("internal.routes.team.team_client", new_callable=AsyncMock)
    context.mock_team = p.start()
    context._patchers.append(p)

    p = patch("internal.routes.mailler.mailler_client", new_callable=AsyncMock)
    context.mock_mailler_mailler = p.start()
    context._patchers.append(p)

    p = patch("internal.routes.contacts.mailler_client", new_callable=AsyncMock)
    context.mock_mailler_contacts = p.start()
    context._patchers.append(p)

    p = patch("internal.routes.contact_groups.mailler_client", new_callable=AsyncMock)
    context.mock_mailler_groups = p.start()
    context._patchers.append(p)

    p = patch("internal.routes.email_templates.mailler_client", new_callable=AsyncMock)
    context.mock_mailler_templates = p.start()
    context._patchers.append(p)

    p = patch("internal.routes.email_campaigns.mailler_client", new_callable=AsyncMock)
    context.mock_mailler_campaigns = p.start()
    context._patchers.append(p)

    # Prompt generator (local import in route function, patch at source)
    p = patch("internal.services.prompt_generator.PromptGeneratorService")
    context.mock_prompt_generator_cls = p.start()
    context._patchers.append(p)


def before_scenario(context, scenario):
    """Reset state before each scenario."""
    # Reset response
    context.response = None
    context.created_ids = []

    # Reset auth defaults
    context.user_scopes = DEFAULT_SCOPES
    context.user_id = TEST_USER_ID
    context.user_email = TEST_USER_EMAIL
    context.user_name = TEST_USER_NAME
    context.authenticated = True
    _configure_auth(context)

    # Reset all service mocks
    for p_mock in [
        context.mock_analytics,
        context.mock_analytics_admin,
        context.mock_auth_client,
        context.mock_billing,
        context.mock_vpn,
        context.mock_team,
        context.mock_mailler_mailler,
        context.mock_mailler_contacts,
        context.mock_mailler_groups,
        context.mock_mailler_templates,
        context.mock_mailler_campaigns,
        context.mock_prompt_generator_cls,
    ]:
        p_mock.reset_mock()

    # Clean database tables (children first)
    async def _clean_db():
        async with context.engine.begin() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                await conn.execute(table.delete())

    context.loop.run_until_complete(_clean_db())


def after_scenario(context, scenario):
    """Clean up after each scenario."""
    # Restore OpenAI settings if modified by prompts/knowledge steps
    if getattr(context, "_openai_key_needs_restore", False):
        from internal.config import settings as _settings

        _settings.__dict__["openai_api_key"] = ""

    # Stop any httpx patchers started by auth steps
    patcher = getattr(context, "_httpx_patcher", None)
    if patcher is not None:
        with contextlib.suppress(RuntimeError):
            patcher.stop()
        context._httpx_patcher = None


def after_all(context):
    """Tear down test infrastructure."""
    for attr in [
        "_jwt_validate_patcher",
        "_jwt_introspect_patcher",
        "_jwt_introspect_active_patcher",
        "_token_exchange_configured_patcher",
        "_token_exchange_validate_patcher",
        "_token_exchange_exchange_patcher",
    ]:
        patcher = getattr(context, attr, None)
        if patcher:
            with contextlib.suppress(RuntimeError):
                patcher.stop()

    for p in getattr(context, "_patchers", []):
        with contextlib.suppress(RuntimeError):
            p.stop()

    # Close the engine and delete the SQLite file
    if hasattr(context, "engine"):
        context.loop.run_until_complete(context.engine.dispose())
        shutil.rmtree(context.db_dir, ignore_errors=True)

    if hasattr(context, "loop") and not context.loop.is_closed():
        context.loop.close()

    app.dependency_overrides.clear()


# The @browser scenarios (features/browser) drive a real Chromium: wrap the hooks above
import browser_support  # noqa: E402

browser_support.install(globals())
