# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Knowledge SaaS API - Main application.

This application has two parts:
1. Public API (main app) - Customer-facing REST API with docs at /docs
2. Internal routes (mounted sub-app) - health checks and webhooks (and later web UI)
   with docs at /internal/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from knowledge import __version__
from knowledge.auth.jwt import get_jwt_validator
from knowledge.auth.token_exchange import get_token_exchange_client
from knowledge.config import get_settings
from knowledge.internal import internal_app
from knowledge.logging import get_logger, setup_logging
from knowledge.middleware import APITrackingMiddleware, TenantMiddleware
from knowledge.routes import (
    collaborators,
    collection_invitations,
    collections,
    documents,
    search,
)

settings = get_settings()

# Configure structured logging
setup_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info(f"Starting {settings.app_name} v{__version__}")
    yield
    # Cleanup
    logger.info(f"Shutting down {settings.app_name}")
    try:
        jwt_validator = get_jwt_validator()
        await jwt_validator.close()
    except Exception:
        pass
    try:
        token_exchange = get_token_exchange_client()
        await token_exchange.close()
    except Exception:
        pass


def get_swagger_oauth2_config() -> dict:
    """Configure Swagger UI OAuth2 login for API docs."""
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

# =============================================================================
# MAIN APPLICATION (Public API)
# =============================================================================

app = FastAPI(
    title=f"{settings.app_name} API",
    description="""
Vector storage and semantic search platform for AI agents and applications.

## Features

- **Collections**: Create and manage document collections with vector embeddings
- **Documents**: Add, list, and delete documents within collections
- **Semantic search**: Vector similarity search across collections
- **Collaborators**: Share collections with team members
- **Collection invitations**: Invite users to collaborate on collections
- **Usage tracking**: Successful API calls are recorded per tenant
- **Multi-tenant**: Subdomain and custom domain tenant resolution
- **OAuth2 authentication**: PKCE-based authentication with scope validation

## Authentication

This API uses OAuth2 with PKCE for authentication. The Swagger UI requests
only `openid`, `profile`, and `email` scopes. The server validates that
the user has the required `knowledge:*` scopes via token exchange.

## Required Scopes

- `collections:read` - Read access to collections
- `collections:write` - Create, update, delete collections
- `collections:search` - Perform semantic search
- `documents:read` - Read access to documents
- `documents:write` - Create, update, delete documents

## Internal Routes

For internal routes (health checks), see [/internal/docs](/internal/docs)
    """,
    version=__version__,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
    openapi_tags=[
        {"name": "Collections", "description": "Manage document collections"},
        {"name": "Documents", "description": "Add and manage documents within collections"},
        {"name": "Search", "description": "Semantic search across collections"},
        {"name": "Collaborators", "description": "Manage collection collaborators"},
        {
            "name": "Collection Invitations",
            "description": "Invite users to collaborate on collections",
        },
    ],
    lifespan=lifespan,
    **swagger_config,
)

# =============================================================================
# MIDDLEWARE
# =============================================================================

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_credentials,
    allow_methods=settings.cors_methods,
    allow_headers=settings.cors_headers,
)

# API tracking middleware (records API calls per tenant for quota management)
app.add_middleware(APITrackingMiddleware)

# Tenant resolution middleware (path prefix, subdomain, custom domain CNAME)
if settings.tenant_base_domain:  # pragma: no cover - requires module reload with live settings
    app.add_middleware(
        TenantMiddleware,
        base_domain=settings.tenant_base_domain,
        custom_domain_lookup=settings.tenant_custom_domain_lookup,
    )

# =============================================================================
# PUBLIC API ROUTES
# =============================================================================

app.include_router(collections.router, prefix="/api/v1", tags=["Collections"])
app.include_router(collaborators.router, prefix="/api/v1", tags=["Collaborators"])
app.include_router(
    collection_invitations.collection_router, prefix="/api/v1", tags=["Collection Invitations"]
)
app.include_router(
    collection_invitations.public_router, prefix="/api/v1", tags=["Collection Invitations"]
)
app.include_router(documents.router, prefix="/api/v1", tags=["Documents"])
app.include_router(search.router, prefix="/api/v1", tags=["Search"])

# =============================================================================
# MOUNT INTERNAL SUB-APPLICATION
# =============================================================================
# Internal routes include: health checks and webhooks (and later auth and web UI)
# These have their own OpenAPI documentation at /internal/docs

app.mount("", internal_app)
