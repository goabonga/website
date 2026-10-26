# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for certificate signing and revocation in the Step-CA client.

``subprocess.run`` is replaced by a fake ``step`` binary that signs nothing but writes a
real certificate where the client expects it.
"""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from certs import self_signed_pem
from cryptography import x509
from vpn_portal.core import stepca
from vpn_portal.core.stepca import CertificateBundle, StepCAClient, StepCAError


@pytest.fixture
def root_ca(tmp_path):
    path = tmp_path / "root_ca.crt"
    path.write_text(self_signed_pem("Root"))
    return path


@pytest.fixture
def client(root_ca):
    return StepCAClient(
        ca_url="https://ca.test:8443",
        root_ca_path=str(root_ca),
        provisioner="vpn-portal",
        provisioner_password="s3cret",
    )


class FakeStep:
    """Records the command line and behaves like ``step ca sign`` / ``step ca revoke``."""

    def __init__(self, returncode: int = 0, stderr: str = "") -> None:
        self.returncode = returncode
        self.stderr = stderr
        self.calls: list[list[str]] = []
        self.csr: x509.CertificateSigningRequest | None = None
        self.password: str | None = None
        self.paths: list[str] = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        assert kwargs["timeout"] == 30
        self.password = Path(cmd[cmd.index("--provisioner-password-file") + 1]).read_text()
        self.paths = [cmd[cmd.index("--provisioner-password-file") + 1]]
        if self.returncode == 0 and cmd[2] == "sign":
            csr_path, cert_path = cmd[-2], cmd[-1]
            self.csr = x509.load_pem_x509_csr(Path(csr_path).read_bytes())
            Path(cert_path).write_text(self_signed_pem(self.csr.subject.rfc4514_string()))
            self.paths += [csr_path, cert_path]
        return subprocess.CompletedProcess(cmd, self.returncode, stdout="", stderr=self.stderr)


@pytest.fixture
def fake_step():
    step = FakeStep()
    with patch.object(stepca.subprocess, "run", step):
        yield step


class TestGenerateCertificate:
    async def test_returns_a_bundle(self, client, fake_step, root_ca):
        bundle = await client.generate_certificate("vpn-user-1")

        assert isinstance(bundle, CertificateBundle)
        assert bundle.common_name == "vpn-user-1"
        assert bundle.certificate_pem.startswith("-----BEGIN CERTIFICATE-----")
        assert bundle.private_key_pem.startswith("-----BEGIN RSA PRIVATE KEY-----")
        assert bundle.ca_certificate_pem == root_ca.read_text()
        assert bundle.not_after > bundle.not_before
        assert bundle.serial_number == format(
            x509.load_pem_x509_certificate(bundle.certificate_pem.encode()).serial_number, "x"
        )

    async def test_signing_command(self, client, fake_step, root_ca):
        await client.generate_certificate("vpn-user-1")

        cmd = fake_step.calls[0]
        assert cmd[:4] == ["/usr/bin/step", "ca", "sign", "--force"]
        assert cmd[cmd.index("--ca-url") + 1] == "https://ca.test:8443"
        assert cmd[cmd.index("--root") + 1] == str(root_ca)
        assert cmd[cmd.index("--provisioner") + 1] == "vpn-portal"
        assert fake_step.password == "s3cret"

    async def test_csr_carries_the_common_name(self, client, fake_step):
        await client.generate_certificate("vpn-user-1")

        assert fake_step.csr.subject.rfc4514_string() == "CN=vpn-user-1"
        with pytest.raises(x509.ExtensionNotFound):
            fake_step.csr.extensions.get_extension_for_class(x509.SubjectAlternativeName)

    async def test_csr_carries_the_email_san(self, client, fake_step):
        await client.generate_certificate("vpn-user-1", san_email="user@example.com")

        san = fake_step.csr.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        assert san.value.get_values_for_type(x509.RFC822Name) == ["user@example.com"]

    @pytest.mark.parametrize(
        ("requested", "expected"), [(None, "10m"), (5, "5m"), (15, "15m"), (60, "15m")]
    )
    async def test_duration_is_defaulted_and_capped(
        self, client, fake_step, monkeypatch, requested, expected
    ):
        monkeypatch.setattr(stepca.settings, "cert_default_duration_minutes", 10)
        monkeypatch.setattr(stepca.settings, "cert_max_duration_minutes", 15)

        await client.generate_certificate("cn", duration_minutes=requested)

        cmd = fake_step.calls[0]
        assert cmd[cmd.index("--not-after") + 1] == expected

    async def test_temporary_files_are_removed(self, client, fake_step):
        await client.generate_certificate("cn")

        assert len(fake_step.paths) == 3
        assert not any(Path(path).exists() for path in fake_step.paths)

    async def test_failure_raises_and_cleans_up(self, client):
        step = FakeStep(returncode=1, stderr="provisioner not found")
        with (
            patch.object(stepca.subprocess, "run", step),
            pytest.raises(StepCAError, match="provisioner not found"),
        ):
            await client.generate_certificate("cn")

        assert not Path(step.paths[0]).exists()

    async def test_missing_password_raises(self, root_ca, tmp_path, monkeypatch):
        monkeypatch.setattr(stepca.settings, "stepca_provisioner_password", "")
        client = StepCAClient(
            root_ca_path=str(root_ca), provisioner_password_file=str(tmp_path / "absent")
        )

        with pytest.raises(StepCAError, match="No provisioner password"):
            await client.generate_certificate("cn")


class TestRevokeCertificate:
    async def test_revocation_command(self, client, fake_step, root_ca):
        await client.revoke_certificate("abc123")

        cmd = fake_step.calls[0]
        assert cmd[:4] == ["/usr/bin/step", "ca", "revoke", "--force"]
        assert cmd[-1] == "abc123"
        assert cmd[cmd.index("--root") + 1] == str(root_ca)
        assert fake_step.password == "s3cret"

    async def test_password_file_is_removed(self, client, fake_step):
        await client.revoke_certificate("abc123")

        assert not Path(fake_step.paths[0]).exists()

    async def test_failure_raises(self, client):
        step = FakeStep(returncode=1, stderr="not found")
        with (
            patch.object(stepca.subprocess, "run", step),
            pytest.raises(StepCAError, match="revocation failed: not found"),
        ):
            await client.revoke_certificate("abc123")

        assert not Path(step.paths[0]).exists()
