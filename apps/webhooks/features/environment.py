# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment configuration for BDD tests (in-process, no infrastructure).

Every provider route is enabled and its internal API client is replaced by a
mock, so scenarios exercise the real ASGI application without any network.
"""

import asyncio
import importlib
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

PROVIDERS = ("brevo",)

# Enable the provider routes before the settings object is created.
for _provider in PROVIDERS:
    os.environ[f"{_provider.upper()}_ENABLED"] = "true"
    os.environ[f"{_provider.upper()}_INTERNAL_API_URL"] = "http://internal.test"

from webhooks.config import settings  # noqa: E402
from webhooks.logging import setup_logging  # noqa: E402
from webhooks.main import app  # noqa: E402


def _create_mock_client():
    """Create a mock async client standing in for the internal API."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b'{"received": true}'

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    return mock_client, mock_response


def before_all(context):
    """Create the event loop, expose the application and mock the internal APIs."""
    context.loop = asyncio.new_event_loop()
    asyncio.set_event_loop(context.loop)
    context.app = app
    context.clients = {}
    context.client_responses = {}
    context.patchers = []
    for provider in PROVIDERS:
        client, response = _create_mock_client()
        context.clients[provider] = client
        context.client_responses[provider] = response
        module = importlib.import_module(f"webhooks.routes.{provider}")
        patcher = patch.object(module, "get_internal_client", return_value=client)
        patcher.start()
        context.patchers.append(patcher)


def after_all(context):
    """Stop the patches and close the event loop."""
    for patcher in context.patchers:
        patcher.stop()
    context.loop.close()


def before_scenario(context, scenario):
    """Reset per-scenario state."""
    context.response = None
    context.setting_backup = {}
    context.custom_headers = {}
    for provider in PROVIDERS:
        context.clients[provider].post.reset_mock(side_effect=True)
        context.client_responses[provider].status_code = 200
        context.client_responses[provider].content = b'{"received": true}'


def after_scenario(context, scenario):
    """Restore overridden settings, patches and the standard streams."""
    for name, value in context.setting_backup.items():
        setattr(settings, name, value)
    patcher = getattr(context, "token_patcher", None)
    if patcher:
        patcher.stop()
        context.token_patcher = None
    saved = getattr(context, "saved_streams", None)
    if saved:
        sys.stdout, sys.stderr = saved
        context.saved_streams = None
        setup_logging()
