# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for VPN feature scenarios."""

from datetime import UTC, datetime, timedelta

from behave import given
from internal.services.vpn_portal_client import VPNSession, VPNSessionsResponse

# --- Sessions list mock setup ---


@given("VPN sessions exist")
def step_vpn_sessions_exist(context):
    now = datetime.now(UTC)
    session = VPNSession(
        id="session-001",
        user_id="user-001",
        username="testuser",
        device_name="laptop",
        connected_at=now - timedelta(hours=2),
        assigned_ip="10.8.0.2",
        certificate_serial="ABC123DEF456",
        expires_at=now + timedelta(hours=22),
        scopes=["vpn:connect"],
        routes=["10.8.0.0/24"],
    )
    response = VPNSessionsResponse(
        sessions=[session],
        total=1,
        page=1,
        per_page=20,
    )
    context.mock_vpn.get_sessions.return_value = response


@given("the VPN service is unavailable")
def step_vpn_service_unavailable(context):
    context.mock_vpn.get_sessions.return_value = None


# --- Revoke session mock setup ---


@given("revoking a VPN session succeeds")
def step_revoke_session_success(context):
    context.mock_vpn.revoke_session.return_value = True


@given("revoking a VPN session fails")
def step_revoke_session_failure(context):
    context.mock_vpn.revoke_session.return_value = False
