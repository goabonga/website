# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Reachy Mini API application."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from reachy_mini_api import __version__
from reachy_mini_api.api import router as api_router
from reachy_mini_api.auth import jwks_manager
from reachy_mini_api.config import settings
from reachy_mini_api.logging import get_logger, setup_logging
from reachy_mini_api.middleware import RequestLoggingMiddleware

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler."""
    setup_logging(level=settings.log_level)
    logger.info(f"Starting {settings.app_name}")
    yield
    logger.info(f"Shutting down {settings.app_name}")
    await jwks_manager.close()


def get_swagger_ui_oauth2_config() -> dict:
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


swagger_config = get_swagger_ui_oauth2_config()


app = FastAPI(
    title=settings.app_name,
    description="""
Internal API for the Reachy Mini robot to fetch reports and data.

## Features

- **Reports**: Fetch daily briefings and quick updates
- **Notifications**: Pending notification feed
- **OAuth2 authentication**: PKCE-based authentication with scope validation

## Authentication

This API uses OAuth2 with PKCE for authentication. The Swagger UI requests
only `openid`, `profile`, and `email` scopes. Routes validate the bearer
token against the issuer JWKS and check the scopes it carries.

## Required Scopes

- `reachy:reports:read` - Read robot reports
- `reachy:notifications:read` - Read notifications
""",
    version=__version__,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
    lifespan=lifespan,
    **swagger_config,
)

# Request logging middleware (added first so that it wraps every request)
app.add_middleware(RequestLoggingMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_credentials,
    allow_methods=settings.cors_methods,
    allow_headers=settings.cors_headers,
)


class HealthResponse(BaseModel):
    """Health check response."""

    status: str


@app.get("/health", response_model=HealthResponse, include_in_schema=False)
async def health_check() -> HealthResponse:
    """Health check endpoint (hidden from Swagger)."""
    return HealthResponse(status="healthy")


app.include_router(api_router, prefix="/api")
