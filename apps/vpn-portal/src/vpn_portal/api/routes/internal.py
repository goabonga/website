# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Internal API endpoints for OpenVPN scripts."""

import logging

from fastapi import APIRouter

from vpn_portal.api.deps import GetDB, RequireVPNServer
from vpn_portal.api.schemas import (
    InternalConnectRequest,
    InternalDisconnectRequest,
    InternalStatusResponse,
    InternalValidateRequest,
    InternalValidateResponse,
)
from vpn_portal.services.certificate import certificate_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/validate", response_model=InternalValidateResponse)
async def validate_certificate(
    db: GetDB,
    _auth: RequireVPNServer,
    request: InternalValidateRequest,
) -> InternalValidateResponse:
    """Validate certificate for OpenVPN client-connect script.

    Called by OpenVPN when a client connects. Validates the certificate
    and returns routes to push to the client.

    Requires vpn:server scope.
    """
    cert = await certificate_service.get_certificate_by_cn(
        db=db,
        common_name=request.common_name,
    )

    if not cert:
        logger.warning(
            "Certificate validation failed: unknown CN %s from %s",
            request.common_name,
            request.client_ip,
        )
        return InternalValidateResponse(
            valid=False,
            reason="Certificate not found",
            routes=[],
        )

    if cert.is_revoked:
        logger.warning(
            "Certificate validation failed: revoked CN %s from %s",
            request.common_name,
            request.client_ip,
        )
        return InternalValidateResponse(
            valid=False,
            reason="Certificate revoked",
            routes=[],
        )

    if cert.is_expired:
        logger.warning(
            "Certificate validation failed: expired CN %s from %s",
            request.common_name,
            request.client_ip,
        )
        return InternalValidateResponse(
            valid=False,
            reason="Certificate expired",
            routes=[],
        )

    logger.info(
        "Certificate validated: CN=%s, client_ip=%s, routes=%s",
        request.common_name,
        request.client_ip,
        cert.assigned_routes,
    )

    return InternalValidateResponse(
        valid=True,
        reason=None,
        routes=cert.assigned_routes,
    )


@router.post("/connect", response_model=InternalStatusResponse)
async def record_connect(
    db: GetDB,
    _auth: RequireVPNServer,
    request: InternalConnectRequest,
) -> InternalStatusResponse:
    """Record VPN connection for OpenVPN client-connect script.

    Called by OpenVPN after successful client connection.

    Requires vpn:server scope.
    """
    connection = await certificate_service.record_connection(
        db=db,
        common_name=request.common_name,
        client_ip=request.client_ip,
        assigned_ip=request.assigned_ip,
    )

    if not connection:
        logger.warning(
            "Failed to record connection: unknown CN %s",
            request.common_name,
        )
        return InternalStatusResponse(status="certificate_not_found")

    return InternalStatusResponse(status="connected")


@router.post("/disconnect", response_model=InternalStatusResponse)
async def record_disconnect(
    db: GetDB,
    _auth: RequireVPNServer,
    request: InternalDisconnectRequest,
) -> InternalStatusResponse:
    """Record VPN disconnection for OpenVPN client-disconnect script.

    Called by OpenVPN when a client disconnects.

    Requires vpn:server scope.
    """
    connection = await certificate_service.record_disconnection(
        db=db,
        common_name=request.common_name,
        bytes_received=request.bytes_received,
        bytes_sent=request.bytes_sent,
    )

    if not connection:
        logger.warning(
            "Failed to record disconnection: no active connection for CN %s",
            request.common_name,
        )
        return InternalStatusResponse(status="connection_not_found")

    return InternalStatusResponse(status="disconnected")
