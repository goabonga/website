# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Knowledge SaaS API - Main application.

This application has two parts:
1. Public API (main app) - Customer-facing REST API with docs at /docs
2. Internal routes (mounted sub-app) - health checks (and later web UI, webhooks)
   with docs at /internal/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from knowledge import __version__
from knowledge.config import get_settings
from knowledge.internal import internal_app
from knowledge.logging import get_logger, setup_logging

settings = get_settings()

# Configure structured logging
setup_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info(f"Starting {settings.app_name} v{__version__}")
    yield
    logger.info(f"Shutting down {settings.app_name}")


# =============================================================================
# MAIN APPLICATION (Public API)
# =============================================================================

app = FastAPI(
    title=f"{settings.app_name} API",
    description="""
Vector storage and semantic search platform for AI agents and applications.

## Internal Routes

For internal routes (health checks), see [/internal/docs](/internal/docs)
    """,
    version=__version__,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
    openapi_tags=[],
    lifespan=lifespan,
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

# =============================================================================
# MOUNT INTERNAL SUB-APPLICATION
# =============================================================================
# Internal routes include: health checks (and later webhooks, auth and web UI)
# These have their own OpenAPI documentation at /internal/docs

app.mount("", internal_app)
