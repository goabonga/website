# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for vpn.feature.

Step-CA is replaced by a mock on the shared certificate service and the database by the
in-memory session installed in ``environment.py``.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from behave import given, then
from certs import self_signed_pem
from vpn_portal.core.stepca import CertificateBundle, StepCAError
from vpn_portal.db.models import VPNCertificate
from vpn_portal.services.certificate import certificate_service


def _bundle(common_name, duration_minutes):
    now = datetime.now(UTC)
    return CertificateBundle(
        certificate_pem="-----BEGIN CERTIFICATE-----\nCLIENT\n-----END CERTIFICATE-----",
        private_key_pem="-----BEGIN RSA PRIVATE KEY-----\nKEY\n-----END RSA PRIVATE KEY-----",
        ca_certificate_pem=self_signed_pem(),
        serial_number=uuid.uuid4().hex[:12],
        common_name=common_name,
        not_before=now,
        not_after=now + timedelta(minutes=duration_minutes or 10),
    )


def _install_stepca(context):
    if hasattr(context, "stepca"):
        return context.stepca
    context.stepca = AsyncMock()
    patcher = patch.object(certificate_service, "stepca", context.stepca)
    patcher.start()
    context.add_cleanup(patcher.stop)
    ta_patcher = patch("vpn_portal.core.ovpn.load_ta_key", return_value="# fake ta key")
    ta_patcher.start()
    context.add_cleanup(ta_patcher.stop)
    return context.stepca


@given("the certificate authority will sign certificates")
def step_ca_signs(context):
    stepca = _install_stepca(context)
    stepca.generate_certificate.side_effect = lambda **kw: _bundle(
        kw["common_name"], kw["duration_minutes"]
    )


@given("the certificate authority will fail")
def step_ca_fails(context):
    stepca = _install_stepca(context)
    stepca.generate_certificate.side_effect = StepCAError("Step-CA unavailable")
    stepca.revoke_certificate.side_effect = StepCAError("Step-CA unavailable")


@given("the certificate authority will accept revocations")
def step_ca_revokes(context):
    _install_stepca(context)


@given("the user has an active certificate")
def step_active_certificate(context):
    now = datetime.now(UTC)
    context.certificate = VPNCertificate(
        id=uuid.uuid4(),
        user_id=context.user.id,
        username=context.user.name,
        serial_number=uuid.uuid4().hex[:12],
        common_name=f"vpn-{context.user.id}-1",
        not_before=now - timedelta(minutes=1),
        not_after=now + timedelta(minutes=10),
        scopes=["vpn:connect"],
        assigned_routes=["10.8.0.0/24"],
    )
    context.db.add(context.certificate)
    context.run(context.db.commit())


@given("the user has no active certificate")
def step_no_certificate(context):
    assert context.db.rows("vpn_certificates") == []


@then("one certificate should be recorded")
def step_one_recorded(context):
    assert len(context.db.rows("vpn_certificates")) == 1


@then("no certificate should be recorded")
def step_none_recorded(context):
    assert context.db.rows("vpn_certificates") == []


@then('the recorded certificate should have the device name "{name}"')
def step_device_name(context, name):
    assert context.db.rows("vpn_certificates")[0].device_name == name


@then("the certificate authority should have been asked for {minutes:d} minutes")
def step_asked_duration(context, minutes):
    assert context.stepca.generate_certificate.await_args.kwargs["duration_minutes"] == minutes


@then('the assigned routes should be "{routes}"')
def step_routes(context, routes):
    assert context.response.json()["assigned_routes"] == routes.split(",")


@then("the certificate authority should have revoked the certificate")
def step_ca_revoked(context):
    context.stepca.revoke_certificate.assert_awaited_once_with(context.certificate.serial_number)
