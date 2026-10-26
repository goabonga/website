# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for GET /api/v1/vpn/ca."""

from unittest.mock import AsyncMock, patch

from conftest import authenticated_as
from vpn_portal.auth.models import User
from vpn_portal.core.stepca import StepCAError

PEM = "-----BEGIN CERTIFICATE-----\nMIIroot\n-----END CERTIFICATE-----"
FINGERPRINT = "ab" * 32


async def test_returns_the_root_certificate(auth_client):
    with patch(
        "vpn_portal.api.routes.vpn.stepca_client.get_root_certificate",
        AsyncMock(return_value=(PEM, FINGERPRINT)),
    ):
        response = await auth_client.get("/api/v1/vpn/ca")

    assert response.status_code == 200
    assert response.json() == {"ca_certificate": PEM, "fingerprint": FINGERPRINT}


async def test_step_ca_failure_is_502(auth_client):
    with patch(
        "vpn_portal.api.routes.vpn.stepca_client.get_root_certificate",
        AsyncMock(side_effect=StepCAError("refused")),
    ):
        response = await auth_client.get("/api/v1/vpn/ca")

    assert response.status_code == 502
    assert "certificate authority" in response.json()["detail"]
    assert "refused" not in response.json()["detail"]


async def test_requires_a_token(client):
    response = await client.get("/api/v1/vpn/ca")

    assert response.status_code == 401


async def test_requires_the_connect_scope(client):
    user = User(id="00000000-0000-0000-0000-000000000001", scopes=["openid"])
    with authenticated_as(user):
        response = await client.get(
            "/api/v1/vpn/ca", headers={"Authorization": "Bearer header.payload.signature"}
        )

    assert response.status_code == 403


async def test_route_is_documented(client):
    schema = (await client.get("/openapi.json")).json()

    assert "get" in schema["paths"]["/api/v1/vpn/ca"]
