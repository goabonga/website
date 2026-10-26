# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment for the internal application.

Scenarios run fully in-process, without any external infrastructure:

- the FastAPI application is driven through an ASGI transport;
- the OAuth2 token validation is mocked;
"""

import asyncio
import contextlib
import os
import uuid
from unittest.mock import PropertyMock, patch

# Set required env vars BEFORE any internal import
os.environ.setdefault("OAUTH2_ISSUER", "https://auth.test.local")
os.environ.setdefault("OAUTH2_CLIENT_ID", "test-client")
os.environ.setdefault("OAUTH2_CLIENT_SECRET", "test-secret")
os.environ.setdefault("OAUTH2_FRONTEND_CLIENT_ID", "test-frontend")
os.environ.setdefault("APP_BASE_URL", "http://test")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("APP_NAME", "Internal Test")

from internal.main import app

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


def before_all(context):
    """Set up test infrastructure."""
    context.loop = asyncio.new_event_loop()
    context.app = app
    context._patchers = []

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


def after_scenario(context, scenario):
    """Clean up after each scenario."""

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

    if hasattr(context, "loop") and not context.loop.is_closed():
        context.loop.close()

    app.dependency_overrides.clear()


# The @browser scenarios (features/browser) drive a real Chromium: wrap the hooks above
import browser_support  # noqa: E402

browser_support.install(globals())
