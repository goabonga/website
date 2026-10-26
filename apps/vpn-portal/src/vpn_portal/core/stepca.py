# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step-CA client."""

import logging
from pathlib import Path

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes

from vpn_portal.config import settings

logger = logging.getLogger(__name__)


class StepCAError(Exception):
    """Step-CA operation error."""

    pass


class StepCAClient:
    """Client for interacting with the Step-CA certificate authority."""

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


# Default client instance
stepca_client = StepCAClient()
