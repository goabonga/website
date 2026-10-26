# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment: scenarios drive the ASGI application in-process."""

from apt_server.main import app
from fastapi.testclient import TestClient


def before_scenario(context, scenario):
    context.client = TestClient(app)
    context.response = None


def after_scenario(context, scenario):
    context.client.close()
