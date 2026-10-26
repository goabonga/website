# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API request and response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field

# ============================================================================
# VPN Connect Schemas
# ============================================================================


class VPNConnectRequest(BaseModel):
    """Request to connect to VPN."""

    device_name: str | None = Field(
        default=None,
        description="Optional device identifier",
        max_length=255,
    )
    certificate_ttl: int | None = Field(
        default=None,
        description="Certificate TTL in seconds (max 900 = 15min)",
        ge=60,
        le=900,
    )


class VPNConnectResponse(BaseModel):
    """Response with VPN bundle."""

    certificate: str = Field(description="Client certificate in PEM format")
    private_key: str = Field(description="Client private key in PEM format")
    ca_certificate: str = Field(description="CA certificate in PEM format")
    ovpn_config: str = Field(description="Complete OpenVPN configuration")
    expires_at: datetime = Field(description="Certificate expiration timestamp")
    vpn_server: str = Field(description="VPN server hostname")
    vpn_port: int = Field(description="VPN server port")
    assigned_routes: list[str] = Field(description="Assigned VPN routes (CIDR)")


class RootCAResponse(BaseModel):
    """Root CA certificate response."""

    ca_certificate: str = Field(description="Root CA certificate in PEM format")
    fingerprint: str = Field(description="SHA-256 fingerprint of the root CA")


class VPNDisconnectResponse(BaseModel):
    """Response after disconnect/revoke."""

    status: str = Field(description="Disconnection status")
    revoked_at: datetime | None = Field(description="Revocation timestamp")


class VPNStatusResponse(BaseModel):
    """Current VPN connection status."""

    connected: bool = Field(description="Whether user has active certificate")
    certificate_serial: str | None = Field(description="Current certificate serial")
    common_name: str | None = Field(description="Certificate common name")
    expires_at: datetime | None = Field(description="Certificate expiration")
    assigned_routes: list[str] | None = Field(description="Assigned routes")
