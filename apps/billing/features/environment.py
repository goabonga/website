# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment hooks for the in-process BDD scenarios.

Everything runs inside the test process: the FastAPI application is called
through an ASGI transport, so no server, PostgreSQL, Redis or network is
needed.

Token validation is faked: every bearer token used by the scenarios maps to
a set of claims registered in ``context.token_claims``.

The database is an in-memory SQLite engine that replaces the PostgreSQL one
(PostgreSQL ``JSONB`` columns are rendered as plain ``JSON``).

The Stripe service is replaced by a mock that returns unique identifiers.
"""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
from billing.auth.models import User
from billing.config import settings
from billing.database import get_db
from billing.main import app
from billing.models import Base
from httpx import ASGITransport
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    """Render PostgreSQL JSONB columns as plain JSON on SQLite."""
    return "JSON"


DEFAULT_TOKEN = "bdd.mock.token"


def _create_test_user(scopes=None, client_id="bdd-test-client"):
    """Create a test user with billing:* wildcard scope by default."""
    return User(
        id=uuid4(),
        email="bdd-test@example.com",
        name="BDD Test User",
        scopes=scopes or ["billing:*"],
        is_machine_client=False,
        client_id=client_id,
    )


def _create_jwt_claims(user):
    """Create JWT claims dict from a User instance."""
    return {
        "sub": str(user.id),
        "email": user.email,
        "name": user.name,
        "scope": " ".join(user.scopes) if user.scopes else "",
        "client_id": user.client_id,
    }


def register_token(context, token, scopes, client_id="bdd-test-client"):
    """Make the fake token validation accept ``token`` with the given scopes and OAuth client."""
    context.token_claims[token] = _create_jwt_claims(_create_test_user(scopes, client_id))


_counter = 0


def _unique_id(prefix):
    """Generate a unique mock Stripe ID."""
    global _counter
    _counter += 1
    return f"{prefix}_{_counter}"


def _build_stripe_mock():
    """Build a comprehensive Stripe service mock with unique IDs per call."""
    mock = MagicMock()

    # Customer - unique ID per call (DB has unique constraint on saas+stripe_id)
    mock.create_customer.side_effect = lambda **kw: MagicMock(id=_unique_id("cus_bdd"))
    mock.update_customer.return_value = MagicMock(id="cus_bdd_updated")
    mock.create_customer_portal_session.return_value = MagicMock(
        url="https://billing.stripe.com/session/bdd_test"
    )

    # Product - unique ID per call
    mock.create_product.side_effect = lambda **kw: MagicMock(id=_unique_id("prod_bdd"))
    mock.update_product.return_value = MagicMock(id="prod_bdd_updated")

    # Price - unique ID per call
    mock.create_price.side_effect = lambda **kw: MagicMock(id=_unique_id("price_bdd"))
    mock.update_price.return_value = MagicMock(id="price_bdd_updated")

    # Subscription - unique IDs, with real Python values (not MagicMock)
    mock.create_subscription.side_effect = lambda **kw: MagicMock(
        id=_unique_id("sub_bdd"),
        status="active",
        current_period_start=1704067200,
        current_period_end=1706745600,
        items=MagicMock(data=[MagicMock(id=_unique_id("si_bdd"))]),
    )
    mock.update_subscription.return_value = MagicMock(id="sub_bdd_updated")
    mock.cancel_subscription.return_value = MagicMock(
        id="sub_bdd_canceled",
        status="canceled",
        cancel_at_period_end=True,
        canceled_at="2026-01-15T00:00:00Z",
    )

    # Checkout
    mock.create_checkout_session.return_value = MagicMock(
        id="cs_bdd_test",
        url="https://checkout.stripe.com/bdd_test",
    )

    # Get subscription (for sync) - supports both attribute and bracket notation
    def _make_stripe_subscription(*a, **kw):
        item_mock = MagicMock()
        item_data = {
            "id": _unique_id("si_bdd"),
            "current_period_start": 1704067200,
            "current_period_end": 1706745600,
        }
        item_mock.__getitem__ = lambda self, key: item_data[key]
        items_mock = MagicMock()
        items_mock.data = [item_mock]
        sub_mock = MagicMock()
        sub_mock.status = "active"
        sub_mock.cancel_at_period_end = False
        sub_mock.canceled_at = None
        sub_mock.__getitem__ = lambda self, key: items_mock if key == "items" else None
        return sub_mock

    mock.get_subscription.side_effect = _make_stripe_subscription

    # Upgrade subscription - returns (stripe_sub, invoice) tuple
    mock.upgrade_subscription.side_effect = lambda **kw: (
        MagicMock(
            status="active",
            items=MagicMock(data=[MagicMock(id=_unique_id("si_bdd"))]),
        ),
        MagicMock(id="inv_bdd_upgrade", amount_due=500),
    )

    # Invoice preview (for subscription upgrades)
    mock.preview_subscription_upgrade.return_value = MagicMock(
        lines=MagicMock(data=[]),
        subtotal=0,
        total=0,
        currency="usd",
    )

    # Webhook event verification
    mock.verify_webhook_signature.return_value = None

    return mock


async def _create_schema(engine):
    """Create every table on the in-memory SQLite engine."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _cleanup_db(engine):
    """Empty all tables between scenarios for isolation."""
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(text(f"DELETE FROM {table.name}"))


async def _create_async_client(headers=None):
    """Create an httpx AsyncClient using ASGI transport."""
    return httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers=headers or {},
    )


# -- Behave hooks -------------------------------------------------------------


def before_all(context):
    """Set up the event loop, the fakes and the HTTP clients."""
    context.loop = asyncio.new_event_loop()
    asyncio.set_event_loop(context.loop)

    # Fake token validation: the claims come from the token registry.
    context.token_claims = {}
    register_token(context, DEFAULT_TOKEN, ["billing:*"])

    async def _validate(token):
        if token not in context.token_claims:
            raise ValueError("unknown token")
        return context.token_claims[token]

    mock_jwks = patch("billing.auth.dependencies.jwks_manager").start()
    mock_introspection = patch("billing.auth.dependencies.introspection_client").start()
    mock_jwks.is_configured = True
    mock_introspection.validate_token_with_introspection = AsyncMock(side_effect=_validate)
    mock_introspection.validate_opaque_token = AsyncMock(side_effect=_validate)
    context.register_token = lambda token, scopes, client_id="bdd-test-client": register_token(
        context, token, scopes, client_id
    )

    # In-memory SQLite database replacing PostgreSQL.
    context.engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    context.session_factory = async_sessionmaker(
        context.engine, class_=AsyncSession, expire_on_commit=False
    )
    context.loop.run_until_complete(_create_schema(context.engine))

    async def _override_get_db():
        async with context.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    # Modules that open their own sessions use the factory directly.
    for name, module in list(sys.modules.items()):
        if name.startswith("billing.") and hasattr(module, "async_session_factory"):
            patch.object(module, "async_session_factory", context.session_factory).start()

    # Mocked Stripe service, patched wherever it was imported.
    context.stripe_mock = _build_stripe_mock()
    for name, module in list(sys.modules.items()):
        if name.startswith("billing.") and hasattr(module, "get_stripe_service"):
            patch.object(module, "get_stripe_service", return_value=context.stripe_mock).start()

    context.anon_client = context.loop.run_until_complete(_create_async_client())
    context.client = context.loop.run_until_complete(
        _create_async_client(headers={"Authorization": f"Bearer {DEFAULT_TOKEN}"})
    )

    # Signing secret used by the webhook route (verification itself is patched).
    patch.object(settings, "stripe_webhook_secret", "whsec_bdd_test").start()

    # Machine client of the webhooks service (billing:webhooks scope only).
    register_token(context, "webhook.service.token", ["billing:webhooks"])
    context.webhook_client = context.loop.run_until_complete(
        _create_async_client(headers={"Authorization": "Bearer webhook.service.token"})
    )


def before_scenario(context, scenario):
    """Reset per-scenario state."""
    context.response = None
    context.created_ids = {}  # Track created entity IDs for cross-step reference


def after_scenario(context, scenario):
    """Clean up database after each scenario."""
    context.loop.run_until_complete(_cleanup_db(context.engine))


def after_all(context):
    """Tear down clients, patches and event loop."""
    context.loop.run_until_complete(context.anon_client.aclose())
    context.loop.run_until_complete(context.client.aclose())
    context.loop.run_until_complete(context.webhook_client.aclose())
    patch.stopall()
    app.dependency_overrides.clear()
    context.loop.run_until_complete(context.engine.dispose())
    context.loop.close()
