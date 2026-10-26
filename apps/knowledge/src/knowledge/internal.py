# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Internal sub-application.

This module defines the internal routes that are mounted on the main API app.
It has its own OpenAPI documentation at /internal/docs.

Internal routes include health checks, webhook receivers, authentication pages and
the web pages (landing page, dashboard, pricing, legal pages, MCP downloads,
collections, documents, search, workspace settings and members).
"""

from fastapi import FastAPI

from knowledge import __version__
from knowledge.config import get_settings
from knowledge.routes import auth as auth_routes
from knowledge.routes import billing_webhooks, custom_domain_webhooks, github_webhooks, health
from knowledge.routes.web import (
    collections_router,
    documents_router,
    downloads_router,
    home_router,
    organizations_router,
    search_router,
)

settings = get_settings()

# Internal sub-application
internal_app = FastAPI(
    title=f"{settings.app_name} - Internal",
    description="""
## Internal Application

This documentation covers internal routes only.

**For the public customer API, see [/docs](/docs)**

### Route Categories

- **Health** - Health check endpoints
- **Webhooks** - Billing, GitHub and other webhook receivers
- **Auth** - OAuth2 authentication callbacks and account pages
- **Web** - HTML pages for the web application
    """.strip(),
    version=__version__,
    docs_url="/internal/docs",
    redoc_url="/internal/redoc",
    openapi_url="/internal/openapi.json",
    openapi_tags=[
        {"name": "Health", "description": "Health check endpoints"},
        {"name": "Webhooks", "description": "Webhook receivers (billing, GitHub, etc.)"},
        {"name": "Auth", "description": "OAuth2 authentication routes"},
        {"name": "Web", "description": "Web UI HTML pages"},
    ],
)

# Health and webhooks
internal_app.include_router(health.router, tags=["Health"])
internal_app.include_router(billing_webhooks.router, tags=["Webhooks"])
internal_app.include_router(custom_domain_webhooks.router, tags=["Webhooks"])
internal_app.include_router(github_webhooks.router, tags=["Webhooks"])

# Authentication routes (OAuth2 callbacks and account pages)
internal_app.include_router(auth_routes.router, tags=["Auth"])

# Web UI routers (HTML pages)
internal_app.include_router(home_router, tags=["Web"])
internal_app.include_router(downloads_router, tags=["Web"])
internal_app.include_router(collections_router, prefix="/collections", tags=["Web"])
internal_app.include_router(documents_router, prefix="/documents", tags=["Web"])
internal_app.include_router(search_router, prefix="/search", tags=["Web"])
internal_app.include_router(organizations_router, prefix="/organizations", tags=["Web"])

# Backward compatibility: /tenants serves the same routes as /organizations
internal_app.include_router(organizations_router, prefix="/tenants", include_in_schema=False)
