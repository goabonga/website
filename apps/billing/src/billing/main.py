# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Billing API - Multi-SaaS Stripe Billing Platform."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from billing import __version__
from billing.auth import introspection_client, jwks_manager, token_exchange_client
from billing.config import get_settings
from billing.routes import health
from billing.routes.platform import saas

settings = get_settings()

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_swagger_oauth2_config() -> dict:
    """Configure Swagger UI OAuth2 login."""
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info(f"Starting {settings.app_name} v{__version__}")
    yield
    # Cleanup
    logger.info("Shutting down %s", settings.app_name)
    try:
        await jwks_manager.close()
    except Exception as e:
        logger.warning("Error closing jwks_manager: %s", e)
    try:
        await token_exchange_client.close()
    except Exception as e:
        logger.warning("Error closing token_exchange_client: %s", e)
    try:
        await introspection_client.close()
    except Exception as e:
        logger.warning("Error closing introspection_client: %s", e)


# Swagger OAuth2 configuration
swagger_config = get_swagger_oauth2_config()

app = FastAPI(
    title=settings.app_name,
    description="""
Multi-SaaS Stripe Billing Platform.

## Features

- **Multi-SaaS support**: Manage billing for multiple SaaS applications
- **Stripe integration**: Products, prices, customers, subscriptions
- **OAuth2 authentication**: PKCE-based authentication with scope validation

## Authentication

This API uses OAuth2 with PKCE for authentication. The Swagger UI requests
only `openid`, `profile`, and `email` scopes. The server validates that
the user has the required `billing:*` scopes via token exchange.

## Required Scopes

- `billing:platform:read` - Read products, prices, customers, subscriptions
- `billing:platform:write` - Manage products, prices, customers, subscriptions
- `billing:usage:write` - Report usage metrics
- `billing:checkout:write` - Create checkout sessions
- `billing:webhooks` - Process webhooks
    """,
    version=__version__,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
    lifespan=lifespan,
    **swagger_config,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_credentials,
    allow_methods=settings.cors_methods,
    allow_headers=settings.cors_headers,
)

# Include API routers
app.include_router(health.router)

# Platform routes (admin operations - internal VPN only)
app.include_router(saas.router)
