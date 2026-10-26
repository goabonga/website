# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""VPN endpoints for client applications."""

import logging

from fastapi import APIRouter, HTTPException, status

from vpn_portal.api.deps import GetDB, RequireVPNConnect
from vpn_portal.api.schemas import (
    RootCAResponse,
    VPNConnectRequest,
    VPNConnectResponse,
    VPNDisconnectResponse,
    VPNStatusResponse,
)
from vpn_portal.config import settings
from vpn_portal.core.stepca import StepCAError, stepca_client
from vpn_portal.services.certificate import certificate_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/connect", response_model=VPNConnectResponse)
async def vpn_connect(
    db: GetDB,
    auth: RequireVPNConnect,
    request: VPNConnectRequest | None = None,
) -> VPNConnectResponse:
    """Generate VPN bundle (certificate, key, config).

    Requires scope: vpn:connect

    Returns a complete VPN bundle with:
    - Short-lived client certificate (10-15 min)
    - Private key
    - CA certificate
    - OpenVPN configuration
    - Assigned routes based on user scopes
    """
    request = request or VPNConnectRequest()

    # Convert TTL from seconds to minutes
    duration_minutes = None
    if request.certificate_ttl:
        duration_minutes = request.certificate_ttl // 60

    try:
        cert_record, ovpn_config, bundle = await certificate_service.issue_certificate(
            db=db,
            user_id=auth.user_id,
            username=auth.user.name or auth.user.email or auth.user_id,
            scopes=auth.scopes,
            device_name=request.device_name,
            duration_minutes=duration_minutes,
        )

        logger.info(
            "VPN bundle issued: user=%s, serial=%s, expires=%s",
            auth.user_id,
            cert_record.serial_number,
            cert_record.not_after.isoformat(),
        )

        return VPNConnectResponse(
            certificate=bundle.certificate_pem,
            private_key=bundle.private_key_pem,
            ca_certificate=bundle.ca_certificate_pem,
            ovpn_config=ovpn_config,
            expires_at=cert_record.not_after,
            vpn_server=settings.openvpn_server,
            vpn_port=settings.openvpn_port,
            assigned_routes=cert_record.assigned_routes,
        )

    except Exception as e:
        logger.error("Failed to issue certificate: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate VPN bundle",
        )


@router.post("/disconnect", response_model=VPNDisconnectResponse)
async def vpn_disconnect(
    db: GetDB,
    auth: RequireVPNConnect,
) -> VPNDisconnectResponse:
    """Disconnect and revoke current certificate.

    Requires scope: vpn:connect
    """
    # Find user's active certificate
    cert = await certificate_service.get_user_active_certificate(
        db=db,
        user_id=auth.user_id,
    )

    if not cert:
        return VPNDisconnectResponse(
            status="not_connected",
            revoked_at=None,
        )

    # Revoke certificate
    revoked_cert = await certificate_service.revoke_certificate(
        db=db,
        serial_number=cert.serial_number,
        reason="user_requested",
    )

    logger.info(
        "User disconnected: user=%s, serial=%s",
        auth.user_id,
        cert.serial_number,
    )

    return VPNDisconnectResponse(
        status="disconnected",
        revoked_at=revoked_cert.revoked_at if revoked_cert else None,
    )


@router.get("/status", response_model=VPNStatusResponse)
async def vpn_status(
    db: GetDB,
    auth: RequireVPNConnect,
) -> VPNStatusResponse:
    """Get current VPN connection status.

    Requires scope: vpn:connect
    """
    cert = await certificate_service.get_user_active_certificate(
        db=db,
        user_id=auth.user_id,
    )

    if not cert:
        return VPNStatusResponse(
            connected=False,
            certificate_serial=None,
            common_name=None,
            expires_at=None,
            assigned_routes=None,
        )

    return VPNStatusResponse(
        connected=True,
        certificate_serial=cert.serial_number,
        common_name=cert.common_name,
        expires_at=cert.not_after,
        assigned_routes=cert.assigned_routes,
    )


@router.get("/ca", response_model=RootCAResponse)
async def get_root_ca(
    auth: RequireVPNConnect,
) -> RootCAResponse:
    """Get the root CA certificate from the Step-CA server.

    Requires scope: vpn:connect

    Returns the root CA certificate in PEM format along with its
    SHA-256 fingerprint. Clients need this certificate to trust
    VPN certificates issued by the CA.
    """
    try:
        ca_pem, fingerprint = await stepca_client.get_root_certificate()

        logger.info("Root CA served to user=%s", auth.user_id)

        return RootCAResponse(
            ca_certificate=ca_pem,
            fingerprint=fingerprint,
        )

    except StepCAError as e:
        logger.error("Failed to fetch root CA: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch root CA from certificate authority",
        )
