# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Certificate service for VPN Portal."""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vpn_portal.config import settings
from vpn_portal.core.ovpn import generate_ovpn_config
from vpn_portal.core.stepca import CertificateBundle, StepCAClient, stepca_client
from vpn_portal.db.models.certificate import VPNCertificate, VPNConnection

logger = logging.getLogger(__name__)


class CertificateService:
    """Service for managing VPN certificates."""

    def __init__(self, stepca: StepCAClient | None = None):
        """Initialize certificate service.

        Args:
            stepca: Step-CA client instance.
        """
        self.stepca = stepca or stepca_client

    def _generate_common_name(self, user_id: str) -> str:
        """Generate unique common name for certificate.

        Format: vpn-<user_id>-<timestamp>

        Args:
            user_id: User ID from OIDC token.

        Returns:
            Unique common name.
        """
        timestamp = int(datetime.now(UTC).timestamp())
        return f"vpn-{user_id}-{timestamp}"

    def _resolve_routes(self, scopes: list[str]) -> list[str]:
        """Resolve VPN routes based on user scopes.

        Args:
            scopes: User scopes from OIDC token.

        Returns:
            List of CIDR routes.
        """
        routes = set(settings.default_routes)

        for scope in scopes:
            # Check direct scope match
            if scope in settings.scope_routes:
                routes.update(settings.scope_routes[scope])

            # Check wildcard scope (e.g., "vpn:*")
            resource = scope.split(":")[0]
            wildcard = f"{resource}:*"
            if wildcard in settings.scope_routes:
                routes.update(settings.scope_routes[wildcard])

        return sorted(routes)

    async def issue_certificate(
        self,
        db: AsyncSession,
        user_id: str,
        username: str,
        scopes: list[str],
        device_name: str | None = None,
        duration_minutes: int | None = None,
    ) -> tuple[VPNCertificate, str, CertificateBundle]:
        """Issue a new VPN certificate.

        Args:
            db: Database session.
            user_id: User ID from OIDC token.
            username: Username from OIDC token.
            scopes: User scopes from OIDC token.
            device_name: Optional device name.
            duration_minutes: Certificate duration in minutes.

        Returns:
            Tuple of (VPNCertificate record, OVPN config string).
        """
        # Generate common name
        common_name = self._generate_common_name(user_id)

        # Resolve routes based on scopes
        assigned_routes = self._resolve_routes(scopes)

        logger.info(
            "Issuing certificate for user %s (%s) with routes: %s",
            username,
            user_id,
            assigned_routes,
        )

        # Generate certificate via Step-CA
        bundle = await self.stepca.generate_certificate(
            common_name=common_name,
            san_email=username if "@" in username else None,
            duration_minutes=duration_minutes,
        )

        # Create database record
        cert_record = VPNCertificate(
            id=uuid.uuid4(),
            user_id=uuid.UUID(user_id),
            username=username,
            serial_number=bundle.serial_number,
            common_name=bundle.common_name,
            not_before=bundle.not_before,
            not_after=bundle.not_after,
            device_name=device_name,
            scopes=scopes,
            assigned_routes=assigned_routes,
        )

        db.add(cert_record)
        await db.commit()
        await db.refresh(cert_record)

        # Generate OVPN config
        ovpn_config = generate_ovpn_config(
            certificate_pem=bundle.certificate_pem,
            private_key_pem=bundle.private_key_pem,
            ca_certificate_pem=bundle.ca_certificate_pem,
            expires_at=bundle.not_after.isoformat(),
        )

        return cert_record, ovpn_config, bundle

    async def revoke_certificate(
        self,
        db: AsyncSession,
        serial_number: str,
        reason: str = "user_requested",
    ) -> VPNCertificate | None:
        """Revoke a certificate.

        Args:
            db: Database session.
            serial_number: Certificate serial number.
            reason: Revocation reason.

        Returns:
            Updated certificate record or None if not found.
        """
        result = await db.execute(
            select(VPNCertificate).where(VPNCertificate.serial_number == serial_number)
        )
        cert = result.scalar_one_or_none()

        if not cert:
            return None

        # Revoke via Step-CA (passive revocation)
        try:
            await self.stepca.revoke_certificate(serial_number)
        except Exception as e:
            logger.warning(
                "Step-CA revocation failed for serial=%s: %s (proceeding with DB revocation)",
                serial_number,
                e,
            )

        cert.revoked_at = datetime.now(UTC)
        cert.revocation_reason = reason

        await db.commit()
        await db.refresh(cert)

        logger.info(
            "Revoked certificate: serial=%s, reason=%s",
            serial_number,
            reason,
        )

        return cert

    async def get_certificate_by_cn(
        self,
        db: AsyncSession,
        common_name: str,
    ) -> VPNCertificate | None:
        """Get certificate by common name.

        Args:
            db: Database session.
            common_name: Certificate common name.

        Returns:
            Certificate record or None.
        """
        result = await db.execute(
            select(VPNCertificate).where(VPNCertificate.common_name == common_name)
        )
        return result.scalar_one_or_none()

    async def get_user_active_certificate(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> VPNCertificate | None:
        """Get user's active (non-expired, non-revoked) certificate.

        Args:
            db: Database session.
            user_id: User ID.

        Returns:
            Active certificate or None.
        """
        now = datetime.now(UTC)
        result = await db.execute(
            select(VPNCertificate)
            .where(VPNCertificate.user_id == uuid.UUID(user_id))
            .where(VPNCertificate.revoked_at.is_(None))
            .where(VPNCertificate.not_after > now)
            .order_by(VPNCertificate.created_at.desc())
        )
        return result.scalars().first()

    async def record_connection(
        self,
        db: AsyncSession,
        common_name: str,
        client_ip: str,
        assigned_ip: str,
    ) -> VPNConnection | None:
        """Record a new VPN connection.

        Args:
            db: Database session.
            common_name: Certificate common name.
            client_ip: Client's real IP address.
            assigned_ip: Assigned VPN IP address.

        Returns:
            Connection record or None if certificate not found.
        """
        cert = await self.get_certificate_by_cn(db, common_name)
        if not cert:
            logger.warning("Connection attempt with unknown certificate: %s", common_name)
            return None

        connection = VPNConnection(
            id=uuid.uuid4(),
            certificate_id=cert.id,
            connected_at=datetime.now(UTC),
            assigned_ip=assigned_ip,
            client_ip=client_ip,
        )

        db.add(connection)
        await db.commit()
        await db.refresh(connection)

        logger.info(
            "Recorded connection: CN=%s, assigned_ip=%s, client_ip=%s",
            common_name,
            assigned_ip,
            client_ip,
        )

        return connection

    async def record_disconnection(
        self,
        db: AsyncSession,
        common_name: str,
        bytes_received: int = 0,
        bytes_sent: int = 0,
    ) -> VPNConnection | None:
        """Record VPN disconnection.

        Args:
            db: Database session.
            common_name: Certificate common name.
            bytes_received: Bytes received during session.
            bytes_sent: Bytes sent during session.

        Returns:
            Updated connection record or None.
        """
        cert = await self.get_certificate_by_cn(db, common_name)
        if not cert:
            return None

        # Find active connection
        result = await db.execute(
            select(VPNConnection)
            .where(VPNConnection.certificate_id == cert.id)
            .where(VPNConnection.disconnected_at.is_(None))
            .order_by(VPNConnection.connected_at.desc())
        )
        connection = result.scalars().first()

        if not connection:
            logger.warning("No active connection found for certificate: %s", common_name)
            return None

        connection.disconnected_at = datetime.now(UTC)
        connection.bytes_received = bytes_received
        connection.bytes_sent = bytes_sent

        await db.commit()
        await db.refresh(connection)

        logger.info(
            "Recorded disconnection: CN=%s, duration=%ds, rx=%d, tx=%d",
            common_name,
            connection.duration_seconds or 0,
            bytes_received,
            bytes_sent,
        )

        return connection


# Default service instance
certificate_service = CertificateService()
