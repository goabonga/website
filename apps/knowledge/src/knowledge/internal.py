# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Internal sub-application.

This module defines the internal routes that are mounted on the main API app.
It has its own OpenAPI documentation at /internal/docs.

Internal routes include health checks and webhook receivers.
"""

from fastapi import FastAPI

from knowledge import __version__
from knowledge.config import get_settings
from knowledge.routes import billing_webhooks, custom_domain_webhooks, github_webhooks, health

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
    """.strip(),
    version=__version__,
    docs_url="/internal/docs",
    redoc_url="/internal/redoc",
    openapi_url="/internal/openapi.json",
    openapi_tags=[
        {"name": "Health", "description": "Health check endpoints"},
        {"name": "Webhooks", "description": "Webhook receivers (billing, GitHub, etc.)"},
    ],
)

# Health and webhooks
internal_app.include_router(health.router, tags=["Health"])
internal_app.include_router(billing_webhooks.router, tags=["Webhooks"])
internal_app.include_router(custom_domain_webhooks.router, tags=["Webhooks"])
internal_app.include_router(github_webhooks.router, tags=["Webhooks"])
