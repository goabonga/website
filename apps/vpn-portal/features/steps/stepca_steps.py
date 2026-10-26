# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for stepca.feature."""

import datetime
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from behave import given, then, when
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from vpn_portal.core.stepca import StepCAClient, StepCAError

PEM = "-----BEGIN CERTIFICATE-----\nMIIrootCA\n-----END CERTIFICATE-----"


def _self_signed_pem() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test Root CA")])
    now = datetime.datetime.now(datetime.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    return certificate.public_bytes(serialization.Encoding.PEM).decode()


@given("the Step-CA server will return the root CA")
def step_stepca_returns_root(context):
    patcher = patch(
        "vpn_portal.api.routes.vpn.stepca_client.get_root_certificate",
        AsyncMock(return_value=(PEM, "ab" * 32)),
    )
    patcher.start()
    context.add_cleanup(patcher.stop)


@given("the Step-CA server will fail to return the root CA")
def step_stepca_fails(context):
    patcher = patch(
        "vpn_portal.api.routes.vpn.stepca_client.get_root_certificate",
        AsyncMock(side_effect=StepCAError("Connection refused")),
    )
    patcher.start()
    context.add_cleanup(patcher.stop)


def _workdir(context):
    directory = tempfile.TemporaryDirectory()
    context.add_cleanup(directory.cleanup)
    return Path(directory.name)


@given("a local root CA certificate")
def step_local_root(context):
    path = _workdir(context) / "root_ca.crt"
    path.write_text(_self_signed_pem())
    context.root_ca_path = path


@given("no local root CA certificate")
def step_no_local_root(context):
    context.root_ca_path = _workdir(context) / "absent.crt"


@when("the client computes the root fingerprint")
def step_compute_fingerprint(context):
    client = StepCAClient(ca_url="https://ca.test:8443", root_ca_path=str(context.root_ca_path))
    context.fingerprint = None
    context.error = None
    try:
        context.fingerprint = client._get_root_fingerprint()
    except StepCAError as exc:
        context.error = exc


@then("the fingerprint should be {length:d} hexadecimal characters")
def step_check_fingerprint(context, length):
    assert len(context.fingerprint) == length
    int(context.fingerprint, 16)


@then("the client should report that the CA certificate is not found")
def step_check_not_found(context):
    assert context.error is not None and "CA certificate not found" in str(context.error)
