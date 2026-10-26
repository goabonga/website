# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Custom Domain Service Client SDK.

A full-featured Python client for the Custom Domain Service API.

Usage:
    from custom_domain.client import CustomDomainClient

    # Initialize client
    client = CustomDomainClient(
        base_url="https://custom-domain.example.com",
        access_token="your-oauth2-token",
    )

    # Create a domain
    domain = client.domains.create(
        domain="app.example.com",
        owner_id="org_123",
        owner_type="organization",
    )

    # Check status
    status = client.domains.get_status(domain.id)

    # Stream events (SSE)
    for event in client.domains.stream_events(domain.id):
        print(event)
"""

from custom_domain.client.client import (
    AsyncCustomDomainClient,
    AuthenticationError,
    AuthorizationError,
    Client,
    ClientList,
    ClientsAPI,
    ConflictError,
    CustomDomainClient,
    CustomDomainError,
    Domain,
    DomainCreate,
    DomainList,
    DomainLookup,
    DomainsAPI,
    DomainStatus,
    DomainStatus_,
    NotFoundError,
    OverviewStats,
    SSEEvent,
    StatsAPI,
    Template,
    TemplateList,
    TemplatesAPI,
    ValidationError,
)

__all__ = [
    "AsyncCustomDomainClient",
    "AuthenticationError",
    "AuthorizationError",
    "Client",
    "ClientList",
    "ClientsAPI",
    "ConflictError",
    "CustomDomainClient",
    "CustomDomainError",
    "Domain",
    "DomainCreate",
    "DomainList",
    "DomainLookup",
    "DomainStatus",
    "DomainStatus_",
    "DomainsAPI",
    "NotFoundError",
    "OverviewStats",
    "SSEEvent",
    "StatsAPI",
    "Template",
    "TemplateList",
    "TemplatesAPI",
    "ValidationError",
]
