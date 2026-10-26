# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the browser scenarios of the VPN sessions."""

from datetime import UTC, datetime, timedelta

from behave import given
from internal.services.vpn_portal_client import VPNSession, VPNSessionsResponse


@given('a VPN session of the user "{username}" with the certificate "{serial}" exists')
def step_vpn_session_of(context, username, serial):
    now = datetime.now(UTC)
    session = VPNSession(
        id=f"session-{serial}",
        user_id="user-001",
        username=username,
        device_name="laptop",
        connected_at=now - timedelta(hours=2),
        assigned_ip="10.8.0.2",
        certificate_serial=serial,
        expires_at=now + timedelta(hours=22),
        scopes=["vpn:connect"],
        routes=["10.8.0.0/24"],
    )
    context.mock_vpn.get_sessions.return_value = VPNSessionsResponse(
        sessions=[session], total=1, page=1, per_page=20
    )
