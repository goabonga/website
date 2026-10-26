# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""VPN endpoints for client applications."""

import logging

from fastapi import APIRouter, HTTPException, status

from vpn_portal.api.deps import RequireVPNConnect
from vpn_portal.api.schemas import RootCAResponse
from vpn_portal.core.stepca import StepCAError, stepca_client

logger = logging.getLogger(__name__)

router = APIRouter()


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
