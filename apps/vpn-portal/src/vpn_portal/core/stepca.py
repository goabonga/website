# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step-CA client for certificate generation."""

import asyncio
import contextlib
import logging
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from vpn_portal.config import settings

logger = logging.getLogger(__name__)


@dataclass
class CertificateBundle:
    """Generated certificate bundle."""

    certificate_pem: str
    private_key_pem: str
    ca_certificate_pem: str
    serial_number: str
    common_name: str
    not_before: datetime
    not_after: datetime


class StepCAError(Exception):
    """Step-CA operation error."""

    pass


class StepCAClient:
    """Client for interacting with Step-CA to generate short-lived certificates."""

    def __init__(
        self,
        ca_url: str | None = None,
        root_ca_path: str | None = None,
        provisioner: str | None = None,
        provisioner_password: str | None = None,
        provisioner_password_file: str | None = None,
    ):
        """Initialize Step-CA client.

        Args:
            ca_url: Step-CA server URL.
            root_ca_path: Path to root CA certificate.
            provisioner: Provisioner name.
            provisioner_password: Provisioner password (direct).
            provisioner_password_file: Path to provisioner password file.
        """
        self.ca_url = ca_url or settings.stepca_url
        self.root_ca_path = root_ca_path or settings.stepca_root_ca
        self.provisioner = provisioner or settings.stepca_provisioner
        self._provisioner_password = provisioner_password or settings.stepca_provisioner_password
        self._provisioner_password_file = (
            provisioner_password_file or settings.stepca_provisioner_password_file
        )

    def _get_provisioner_password(self) -> str:
        """Get provisioner password from direct value or file."""
        if self._provisioner_password:
            return self._provisioner_password

        if self._provisioner_password_file:
            password_path = Path(self._provisioner_password_file)
            if password_path.exists():
                return password_path.read_text().strip()

        raise StepCAError("No provisioner password configured")

    def _load_ca_certificate(self) -> str:
        """Load CA certificate from file."""
        ca_path = Path(self.root_ca_path)
        if not ca_path.exists():
            raise StepCAError(f"CA certificate not found: {self.root_ca_path}")
        return ca_path.read_text()

    def _get_root_fingerprint(self) -> str:
        """Compute SHA-256 fingerprint of the local root CA certificate.

        Returns:
            Hex-encoded SHA-256 fingerprint.

        Raises:
            StepCAError: If root CA cannot be loaded or parsed.
        """
        ca_pem = self._load_ca_certificate()
        cert = x509.load_pem_x509_certificate(ca_pem.encode())
        return cert.fingerprint(hashes.SHA256()).hex()

    async def get_root_certificate(self) -> tuple[str, str]:
        """Fetch the root CA certificate from the Step-CA server.

        Uses the local root CA for TLS verification and computes
        the fingerprint to query the Step-CA /root/<fingerprint> API.

        Returns:
            Tuple of (PEM-encoded root CA certificate, SHA-256 fingerprint).

        Raises:
            StepCAError: If the root CA cannot be fetched.
        """
        fingerprint = self._get_root_fingerprint()

        try:
            async with httpx.AsyncClient(verify=self.root_ca_path) as client:
                response = await client.get(
                    f"{self.ca_url}/root/{fingerprint}",
                    timeout=10,
                )
                response.raise_for_status()
                data = response.json()
                ca_pem = data["ca"]

                logger.info("Root CA fetched from %s", self.ca_url)
                return ca_pem, fingerprint

        except httpx.HTTPStatusError as e:
            logger.error("Step-CA root API returned %s: %s", e.response.status_code, e)
            raise StepCAError(f"Failed to fetch root CA: HTTP {e.response.status_code}")
        except (httpx.RequestError, KeyError) as e:
            logger.error("Failed to fetch root CA from %s: %s", self.ca_url, e)
            raise StepCAError(f"Failed to fetch root CA: {e}")

    async def generate_certificate(
        self,
        common_name: str,
        san_email: str | None = None,
        duration_minutes: int | None = None,
    ) -> CertificateBundle:
        """Generate a short-lived certificate using Step-CA.

        Args:
            common_name: Certificate common name (e.g., "vpn-<user_id>-<timestamp>").
            san_email: Subject Alternative Name email (optional).
            duration_minutes: Certificate duration in minutes (default from settings).

        Returns:
            CertificateBundle with certificate, key, and metadata.

        Raises:
            StepCAError: If certificate generation fails.
        """
        duration = duration_minutes or settings.cert_default_duration_minutes

        # Enforce maximum duration
        if duration > settings.cert_max_duration_minutes:
            duration = settings.cert_max_duration_minutes

        logger.info(
            "Generating certificate: CN=%s, duration=%dm",
            common_name,
            duration,
        )

        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        # Build CSR
        csr_builder = x509.CertificateSigningRequestBuilder().subject_name(
            x509.Name(
                [
                    x509.NameAttribute(NameOID.COMMON_NAME, common_name),
                ]
            )
        )

        # Add SAN if email provided
        if san_email:
            csr_builder = csr_builder.add_extension(
                x509.SubjectAlternativeName(
                    [
                        x509.RFC822Name(san_email),
                    ]
                ),
                critical=False,
            )

        # Sign CSR
        csr = csr_builder.sign(private_key, hashes.SHA256())
        csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode()

        # Write CSR to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csr", delete=False) as csr_file:
            csr_file.write(csr_pem)
            csr_path = csr_file.name

        # Write password to temp file (step CLI requires file)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pass", delete=False) as pass_file:
            pass_file.write(self._get_provisioner_password())
            pass_path = pass_file.name

        # Output certificate path
        with tempfile.NamedTemporaryFile(mode="w", suffix=".crt", delete=False) as cert_file:
            cert_path = cert_file.name

        try:
            # Run step CA sign command
            # Use full path as gunicorn may not have /usr/bin in PATH
            # --force skips interactive confirmations when running without a TTY
            cmd = [
                "/usr/bin/step",
                "ca",
                "sign",
                "--force",
                "--ca-url",
                self.ca_url,
                "--root",
                self.root_ca_path,
                "--provisioner",
                self.provisioner,
                "--provisioner-password-file",
                pass_path,
                "--not-after",
                f"{duration}m",
                csr_path,
                cert_path,
            ]

            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                ),
            )

            if result.returncode != 0:
                logger.error("step ca sign failed: %s", result.stderr)
                raise StepCAError(f"Certificate signing failed: {result.stderr}")

            # Read generated certificate
            cert_pem = Path(cert_path).read_text()

            # Parse certificate to extract metadata
            cert = x509.load_pem_x509_certificate(cert_pem.encode())
            serial_number = format(cert.serial_number, "x")
            not_before = cert.not_valid_before_utc
            not_after = cert.not_valid_after_utc

            # Export private key
            private_key_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            ).decode()

            # Load CA certificate
            ca_certificate_pem = self._load_ca_certificate()

            logger.info(
                "Certificate generated: serial=%s, expires=%s",
                serial_number,
                not_after.isoformat(),
            )

            return CertificateBundle(
                certificate_pem=cert_pem,
                private_key_pem=private_key_pem,
                ca_certificate_pem=ca_certificate_pem,
                serial_number=serial_number,
                common_name=common_name,
                not_before=not_before,
                not_after=not_after,
            )

        finally:
            # Clean up temp files
            for path in [csr_path, pass_path, cert_path]:
                with contextlib.suppress(Exception):
                    Path(path).unlink(missing_ok=True)

    async def revoke_certificate(self, serial_number: str) -> None:
        """Revoke a certificate via Step-CA (passive revocation).

        Args:
            serial_number: Certificate serial number to revoke.

        Raises:
            StepCAError: If revocation fails.
        """
        logger.info("Revoking certificate via Step-CA: serial=%s", serial_number)

        # Write password to temp file (step CLI requires file)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pass", delete=False) as pass_file:
            pass_file.write(self._get_provisioner_password())
            pass_path = pass_file.name

        try:
            cmd = [
                "/usr/bin/step",
                "ca",
                "revoke",
                "--force",
                "--ca-url",
                self.ca_url,
                "--root",
                self.root_ca_path,
                "--provisioner",
                self.provisioner,
                "--provisioner-password-file",
                pass_path,
                serial_number,
            ]

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                ),
            )

            if result.returncode != 0:
                logger.error("step ca revoke failed: %s", result.stderr)
                raise StepCAError(f"Certificate revocation failed: {result.stderr}")

            logger.info("Certificate revoked via Step-CA: serial=%s", serial_number)

        finally:
            with contextlib.suppress(Exception):
                Path(pass_path).unlink(missing_ok=True)


# Default client instance
stepca_client = StepCAClient()
