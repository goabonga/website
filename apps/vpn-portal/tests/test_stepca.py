# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the Step-CA client (root certificate retrieval)."""

import datetime
from functools import partial

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from vpn_portal.core import stepca
from vpn_portal.core.stepca import StepCAClient, StepCAError


def make_root_ca() -> tuple[str, str]:
    """Return a self-signed CA certificate (PEM) and its SHA-256 fingerprint."""
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
    pem = certificate.public_bytes(serialization.Encoding.PEM).decode()
    return pem, certificate.fingerprint(hashes.SHA256()).hex()


@pytest.fixture
def root_ca(tmp_path):
    pem, fingerprint = make_root_ca()
    path = tmp_path / "root_ca.crt"
    path.write_text(pem)
    return path, pem, fingerprint


def client_for(path, **kwargs) -> StepCAClient:
    return StepCAClient(ca_url="https://ca.test:8443", root_ca_path=str(path), **kwargs)


class TestConfiguration:
    def test_defaults_come_from_settings(self, monkeypatch):
        monkeypatch.setattr(stepca.settings, "stepca_url", "https://ca.example:9000")
        monkeypatch.setattr(stepca.settings, "stepca_root_ca", "/etc/ca/root.crt")
        monkeypatch.setattr(stepca.settings, "stepca_provisioner", "portal")

        client = StepCAClient()

        assert client.ca_url == "https://ca.example:9000"
        assert client.root_ca_path == "/etc/ca/root.crt"
        assert client.provisioner == "portal"

    def test_explicit_arguments_win(self):
        client = StepCAClient(ca_url="https://x", root_ca_path="/r.crt", provisioner="p")

        assert (client.ca_url, client.root_ca_path, client.provisioner) == (
            "https://x",
            "/r.crt",
            "p",
        )

    def test_default_client_instance_exists(self):
        assert isinstance(stepca.stepca_client, StepCAClient)


class TestProvisionerPassword:
    def test_direct_password_wins(self, tmp_path):
        password_file = tmp_path / "pw"
        password_file.write_text("from-file")
        client = StepCAClient(
            provisioner_password="direct", provisioner_password_file=str(password_file)
        )

        assert client._get_provisioner_password() == "direct"

    def test_password_is_read_from_file_and_stripped(self, tmp_path, monkeypatch):
        monkeypatch.setattr(stepca.settings, "stepca_provisioner_password", "")
        password_file = tmp_path / "pw"
        password_file.write_text("  secret\n")
        client = StepCAClient(provisioner_password_file=str(password_file))

        assert client._get_provisioner_password() == "secret"

    def test_missing_password_is_an_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(stepca.settings, "stepca_provisioner_password", "")
        client = StepCAClient(provisioner_password_file=str(tmp_path / "absent"))

        with pytest.raises(StepCAError, match="No provisioner password"):
            client._get_provisioner_password()


class TestRootCertificateFile:
    def test_loads_the_certificate(self, root_ca):
        path, pem, _ = root_ca

        assert client_for(path)._load_ca_certificate() == pem

    def test_missing_file_is_an_error(self, tmp_path):
        with pytest.raises(StepCAError, match="CA certificate not found"):
            client_for(tmp_path / "absent.crt")._load_ca_certificate()

    def test_fingerprint_is_sha256_hex(self, root_ca):
        path, _, fingerprint = root_ca

        assert client_for(path)._get_root_fingerprint() == fingerprint
        assert len(fingerprint) == 64

    def test_invalid_pem_cannot_be_fingerprinted(self, tmp_path):
        path = tmp_path / "bad.crt"
        path.write_text("not a certificate")

        with pytest.raises(ValueError):
            client_for(path)._get_root_fingerprint()


class TestGetRootCertificate:
    @staticmethod
    def install_transport(monkeypatch, handler):
        """Make the client under test talk to ``handler`` instead of the network."""
        real_client = httpx.AsyncClient

        def factory(*, verify=True, **kwargs):
            return real_client(transport=httpx.MockTransport(handler), **kwargs)

        monkeypatch.setattr(stepca.httpx, "AsyncClient", partial(factory))

    async def test_returns_the_certificate_and_fingerprint(self, root_ca, monkeypatch):
        path, pem, fingerprint = root_ca
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            return httpx.Response(200, json={"ca": pem})

        self.install_transport(monkeypatch, handler)

        result = await client_for(path).get_root_certificate()

        assert result == (pem, fingerprint)
        assert seen["url"] == f"https://ca.test:8443/root/{fingerprint}"

    async def test_http_error_is_wrapped(self, root_ca, monkeypatch):
        self.install_transport(monkeypatch, lambda request: httpx.Response(404))

        with pytest.raises(StepCAError, match="HTTP 404"):
            await client_for(root_ca[0]).get_root_certificate()

    async def test_connection_error_is_wrapped(self, root_ca, monkeypatch):
        def handler(request):
            raise httpx.ConnectError("refused")

        self.install_transport(monkeypatch, handler)

        with pytest.raises(StepCAError, match="Failed to fetch root CA"):
            await client_for(root_ca[0]).get_root_certificate()

    async def test_unexpected_payload_is_wrapped(self, root_ca, monkeypatch):
        self.install_transport(monkeypatch, lambda request: httpx.Response(200, json={}))

        with pytest.raises(StepCAError, match="Failed to fetch root CA"):
            await client_for(root_ca[0]).get_root_certificate()

    async def test_missing_local_root_is_an_error(self, tmp_path):
        with pytest.raises(StepCAError, match="CA certificate not found"):
            await client_for(tmp_path / "absent.crt").get_root_certificate()
