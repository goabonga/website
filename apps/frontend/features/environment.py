# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave hooks: every scenario gets its own in-process application."""

from fastapi.testclient import TestClient
from frontend.config import Settings
from frontend.main import create_app


def before_scenario(context, scenario) -> None:
    context.overrides = {}
    context.response = None
    context._client = None


def after_scenario(context, scenario) -> None:
    if context._client is not None:
        context._client.close()
        context._client = None


def get_client(context) -> TestClient:
    """Build (once per scenario) a client on an app created from the scenario settings."""
    if context._client is None:
        settings = Settings(_env_file=None, **context.overrides)
        context._client = TestClient(create_app(settings))
    return context._client


def before_all(context) -> None:
    context.get_client = lambda: get_client(context)
