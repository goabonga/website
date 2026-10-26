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


# ============================================================================
# Internal API Schemas (OpenVPN scripts)
# ============================================================================


class InternalValidateRequest(BaseModel):
    """Request to validate certificate from OpenVPN."""

    common_name: str = Field(description="Certificate common name")
    client_ip: str = Field(description="Client's real IP address")
    assigned_ip: str | None = Field(default=None, description="Assigned VPN IP")


class InternalValidateResponse(BaseModel):
    """Response for certificate validation."""

    valid: bool = Field(description="Whether certificate is valid")
    reason: str | None = Field(default=None, description="Rejection reason if invalid")
    routes: list[str] = Field(default_factory=list, description="Routes to push")


class InternalConnectRequest(BaseModel):
    """Request to record connection from OpenVPN."""

    common_name: str = Field(description="Certificate common name")
    client_ip: str = Field(description="Client's real IP address")
    assigned_ip: str = Field(description="Assigned VPN IP")


class InternalDisconnectRequest(BaseModel):
    """Request to record disconnection from OpenVPN."""

    common_name: str = Field(description="Certificate common name")
    bytes_received: int = Field(default=0, description="Bytes received")
    bytes_sent: int = Field(default=0, description="Bytes sent")


class InternalStatusResponse(BaseModel):
    """Generic status response."""

    status: str = Field(description="Operation status")


# ============================================================================
# Admin API Schemas
# ============================================================================


class AdminSessionResponse(BaseModel):
    """VPN session information for admin."""

    id: str = Field(description="Session ID")
    user_id: str = Field(description="User ID")
    username: str = Field(description="Username")
    device_name: str | None = Field(description="Device name")
    connected_at: datetime = Field(description="Connection timestamp")
    assigned_ip: str = Field(description="Assigned VPN IP")
    certificate_serial: str = Field(description="Certificate serial number")
    expires_at: datetime = Field(description="Certificate expiration")
    scopes: list[str] = Field(description="User scopes")
    routes: list[str] = Field(description="Assigned routes")


class AdminSessionsResponse(BaseModel):
    """List of active VPN sessions."""

    sessions: list[AdminSessionResponse] = Field(description="Active sessions")
    total: int = Field(description="Total number of sessions")
    page: int = Field(description="Current page")
    per_page: int = Field(description="Items per page")


class AdminRevokeResponse(BaseModel):
    """Response after admin revocation."""

    status: str = Field(description="Revocation status")
    serial_number: str = Field(description="Revoked certificate serial")
    revoked_at: datetime | None = Field(description="Revocation timestamp")
