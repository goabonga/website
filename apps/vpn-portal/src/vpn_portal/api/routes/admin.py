# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Admin API endpoints for VPN management."""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from vpn_portal.api.deps import GetDB, RequireVPNAdmin
from vpn_portal.api.schemas import (
    AdminRevokeResponse,
    AdminSessionResponse,
    AdminSessionsResponse,
)
from vpn_portal.db.models.certificate import VPNCertificate, VPNConnection
from vpn_portal.services.certificate import certificate_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/sessions", response_model=AdminSessionsResponse)
async def list_sessions(
    db: GetDB,
    _auth: RequireVPNAdmin,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
) -> AdminSessionsResponse:
    """List active VPN sessions.

    Requires scope: vpn:admin
    """
    now = datetime.now(UTC)

    # Count total active sessions
    count_query = (
        select(func.count(VPNCertificate.id))
        .where(VPNCertificate.revoked_at.is_(None))
        .where(VPNCertificate.not_after > now)
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Get active certificates with active connections
    offset = (page - 1) * per_page
    query = (
        select(VPNCertificate)
        .where(VPNCertificate.revoked_at.is_(None))
        .where(VPNCertificate.not_after > now)
        .order_by(VPNCertificate.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    result = await db.execute(query)
    certificates = result.scalars().all()

    sessions = []
    for cert in certificates:
        # Get latest connection for this certificate
        conn_query = (
            select(VPNConnection)
            .where(VPNConnection.certificate_id == cert.id)
            .order_by(VPNConnection.connected_at.desc())
            .limit(1)
        )
        conn_result = await db.execute(conn_query)
        connection = conn_result.scalar_one_or_none()

        sessions.append(
            AdminSessionResponse(
                id=str(cert.id),
                user_id=str(cert.user_id),
                username=cert.username,
                device_name=cert.device_name,
                connected_at=connection.connected_at if connection else cert.created_at,
                assigned_ip=connection.assigned_ip if connection else "N/A",
                certificate_serial=cert.serial_number,
                expires_at=cert.not_after,
                scopes=cert.scopes,
                routes=cert.assigned_routes,
            )
        )

    return AdminSessionsResponse(
        sessions=sessions,
        total=total,
        page=page,
        per_page=per_page,
    )


@router.delete("/sessions/{serial_number}", response_model=AdminRevokeResponse)
async def revoke_session(
    db: GetDB,
    _auth: RequireVPNAdmin,
    serial_number: str,
) -> AdminRevokeResponse:
    """Revoke a VPN session by certificate serial number.

    Requires scope: vpn:admin
    """
    cert = await certificate_service.revoke_certificate(
        db=db,
        serial_number=serial_number,
        reason="admin_revoked",
    )

    if not cert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate not found: {serial_number}",
        )

    logger.info(
        "Admin revoked certificate: serial=%s, user=%s",
        serial_number,
        cert.username,
    )

    return AdminRevokeResponse(
        status="revoked",
        serial_number=serial_number,
        revoked_at=cert.revoked_at,
    )
