# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the health endpoint and the application factory."""

import vpn_portal
from vpn_portal.main import app


async def test_health_reports_healthy(client):
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


async def test_health_is_hidden_from_openapi(client):
    schema = (await client.get("/openapi.json")).json()

    assert "/health" not in schema["paths"]


async def test_docs_are_served_by_default(client):
    assert (await client.get("/docs")).status_code == 200
    assert (await client.get("/redoc")).status_code == 200


async def test_unknown_route_is_404(client):
    assert (await client.get("/nope")).status_code == 404


def test_application_metadata():
    assert app.title == "VPN Portal"
    assert app.version == vpn_portal.__version__ == "0.0.0"
