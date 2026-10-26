# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""VPN Portal - FastAPI application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from vpn_portal import __version__
from vpn_portal.api.routes import router
from vpn_portal.auth import introspection_client, jwks_manager, token_exchange_client
from vpn_portal.config import settings
from vpn_portal.logging import get_logger, setup_logging

# Setup logging before anything else
setup_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("VPN Portal starting")
    yield
    # Cleanup
    await jwks_manager.close()
    await token_exchange_client.close()
    await introspection_client.close()
    logger.info("VPN Portal shutting down")


def get_swagger_ui_oauth2_config() -> dict:
    """Get Swagger UI OAuth2 configuration.

    Configures PKCE-based OAuth2 flow for Swagger documentation.
    Only requests openid, profile, and email scopes - the server
    validates actual permissions via token exchange.
    """
    if not settings.oauth2_issuer or not settings.oauth2_swagger_client_id:
        return {}

    return {
        "swagger_ui_init_oauth": {
            "clientId": settings.oauth2_swagger_client_id,
            "usePkceWithAuthorizationCodeGrant": True,
        },
        "swagger_ui_parameters": {
            "persistAuthorization": True,
        },
    }


swagger_config = get_swagger_ui_oauth2_config()

app = FastAPI(
    title=settings.app_name,
    description="""
Zero-Trust VPN authentication and certificate issuance service.

## Features

- **Certificate issuance**: Short-lived VPN certificates via Step-CA
- **RBAC routing**: Route assignment based on user scopes
- **OpenVPN integration**: Generate ready-to-use OVPN configurations
- **Root CA distribution**: serve the Step-CA root certificate to clients

## Authentication

This API uses OAuth2 with PKCE for authentication. The Swagger UI requests
only `openid`, `profile`, and `email` scopes. The server validates that
the user has the required `vpn:*` scopes via token exchange.

## Required Scopes

- `vpn:connect` - Connect to VPN and obtain certificates
    """,
    version=__version__,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
    lifespan=lifespan,
    **swagger_config,
)

# Include API routes
app.include_router(router)
