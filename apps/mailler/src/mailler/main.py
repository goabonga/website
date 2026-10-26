# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Mailler API - Internal email sending service."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mailler import __version__
from mailler.config import settings
from mailler.logging import get_logger, setup_logging
from mailler.routes import (
    emails,
    health,
    providers,
    send,
    stats,
)

# Setup logging before anything else
setup_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Mailler API starting")
    yield
    # Cleanup
    from mailler.auth import introspection_client, jwks_manager, token_exchange_client

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
    logger.info("Mailler API shutting down")


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
    title="Mailler API",
    description="""
Internal email sending service supporting multiple providers.

## Features

- **Multi-provider support**: Brevo, SendGrid, AWS SES, Protonmail (SMTP)
- **Async processing**: All emails sent via Celery workers
- **Statistics**: Track sent, delivered, bounced, and failed emails
- **OAuth2 authentication**: PKCE-based authentication with scope validation

## Authentication

This API uses OAuth2 with PKCE for authentication. The Swagger UI requests
only `openid`, `profile`, and `email` scopes. The server validates that
the user has the required `mailler:*` scopes via token exchange.

## Required Scopes

- `mailler:send` - Send and schedule emails
- `mailler:read` - Read email details and list emails
- `mailler:stats` - View sending statistics
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

# Include routers
app.include_router(health.router)
app.include_router(send.router, prefix="/api/v1")
app.include_router(emails.router, prefix="/api/v1")
app.include_router(stats.router, prefix="/api/v1")
app.include_router(providers.router, prefix="/api/v1")
