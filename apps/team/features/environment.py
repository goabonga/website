# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave hooks: every scenario gets its own in-process client and a clean logging setup."""

import logging

from fastapi.testclient import TestClient


def before_scenario(context, scenario) -> None:
    context.response = None
    context.environ = {}
    context.settings = None
    context.streams = None
    context._client = None
    root = logging.getLogger()
    context._root_state = (list(root.handlers), root.level)


def after_scenario(context, scenario) -> None:
    root = logging.getLogger()
    root.handlers[:] = context._root_state[0]
    root.setLevel(context._root_state[1])
    if context._client is not None:
        context._client.close()


def get_client(context) -> TestClient:
    """Return the client of the scenario, bound to the ASGI application (no network)."""
    if context._client is None:
        from team.main import app

        context._client = TestClient(app)
    return context._client


def before_all(context) -> None:
    context.get_client = lambda: get_client(context)
