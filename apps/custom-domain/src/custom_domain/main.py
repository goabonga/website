# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Main FastAPI application."""

import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from custom_domain import __version__
from custom_domain.auth import introspection_client, jwks_manager, token_exchange_client
from custom_domain.config import settings
from custom_domain.database import engine
from custom_domain.logging import get_logger
from custom_domain.routes import domains, events, health
from custom_domain.routes.admin import clients, stats, templates

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Starting Custom Domain Service")

    yield

    logger.info("Shutting down Custom Domain Service")
    await jwks_manager.close()
    await token_exchange_client.close()
    await introspection_client.close()
    await engine.dispose()


def get_swagger_ui_oauth2_config() -> dict:
    """Get Swagger UI OAuth2 configuration."""
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
    title="Custom Domain Service",
    description="""
Centralized service for managing custom domains with SSL provisioning.

## Authentication

This API uses OAuth2 with PKCE for authentication. The Swagger UI requests
only `openid`, `profile`, and `email` scopes. The server validates that
the user has the required `custom-domain:*` scopes via token exchange.

## Required Scopes

- `custom-domain:read` - Read domain configurations and events
- `custom-domain:write` - Create, update, and delete domains
- `custom-domain:lookup` - Internal DNS lookup
- `custom-domain:admin` - Administrative access
    """,
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
    **swagger_config,
)

# CORS middleware
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_credentials,
        allow_methods=settings.cors_methods,
        allow_headers=settings.cors_headers,
    )


# Exception handler for debugging (logs full traceback)
@app.exception_handler(Exception)
async def debug_exception_handler(request: Request, exc: Exception):
    """Log full exception traceback for debugging."""
    tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
    logger.error("Unhandled exception: %s", exc)
    logger.error("Traceback:\n%s", "".join(tb))
    # Also print to stdout for CI visibility
    print(f"[FastAPI Error] {type(exc).__name__}: {exc}")
    print(f"[FastAPI Traceback]\n{''.join(tb)}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "error": str(exc)},
    )


# Health check
app.include_router(health.router)

# Domain routes
app.include_router(domains.router, prefix="/api/v1")
app.include_router(events.router, prefix="/api/v1")

# Admin routes
app.include_router(clients.router, prefix="/api/v1")
app.include_router(stats.router, prefix="/api/v1")
app.include_router(templates.router, prefix="/api/v1")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "custom-domain",
        "version": __version__,
        "docs": "/docs" if settings.docs_enabled else None,
    }
