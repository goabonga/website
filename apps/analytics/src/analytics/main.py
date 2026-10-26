# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""FastAPI main application for Analytics service."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from analytics import __version__
from analytics.config import settings
from analytics.logging import setup_logging
from analytics.routes.collect import router as collect_router
from analytics.routes.health import router as health_router
from analytics.routes.pixel import router as pixel_router
from analytics.routes.security_txt import router as security_txt_router
from analytics.routes.stats import router as stats_router
from analytics.routes.track import router as track_router

# Configure logging before anything else
setup_logging(settings.log_level)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info(f"Starting {settings.app_name} v{__version__}")
    yield
    # Shutdown: clean up resources
    logger.info(f"Shutting down {settings.app_name}")

    from analytics.auth.jwt import jwt_validator
    from analytics.auth.token_exchange import token_exchange_client

    await jwt_validator.close()
    await token_exchange_client.close()


def get_swagger_oauth2_config() -> dict:
    """Build Swagger UI OAuth2 configuration if OAuth2 is configured."""
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


# Swagger OAuth2 configuration
swagger_config = get_swagger_oauth2_config()

app = FastAPI(
    title=settings.app_name,
    description="""
Analytics tracking service for event collection, pixel tracking, and campaign analytics.

## Features

- **Event collection**: Track custom events via JavaScript SDK
- **Pixel tracking**: 1x1 pixel tracking for emails and pages
- **Campaign analytics**: UTM parameter tracking and attribution
- **OAuth2 authentication**: PKCE-based authentication with scope validation

## Authentication

This API uses OAuth2 with PKCE for authentication. The Swagger UI requests
only `openid`, `profile`, and `email` scopes. The server validates that
the user has the required `analytics:*` scopes via token exchange.

## Required Scopes

- `analytics:read` - Read analytics data and statistics
- `analytics:write` - Create and manage tracking events
- `analytics:delete` - Delete analytics data
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
app.include_router(health_router)
app.include_router(security_txt_router)
app.include_router(collect_router)
app.include_router(pixel_router)
app.include_router(track_router)
app.include_router(stats_router)
